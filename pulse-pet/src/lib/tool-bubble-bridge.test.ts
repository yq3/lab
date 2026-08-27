import { afterEach, describe, expect, it, vi } from "vitest";
import {
  TOOL_PARAM_MAX,
  applyToolDetail,
  parseAndSanitize,
  parseToolBubblePayload,
  parseToolDetail,
  parseToolBroadcastEnabled,
  sanitizeToolParam,
  toolBubbleText,
  useToolBroadcastStore,
} from "./tool-bubble-bridge";
import { usePetStore } from "../pet/petStore";
import { changeLanguage } from "./i18n";

function resetState() {
  useToolBroadcastStore.getState().setEnabled(true);
  usePetStore.getState().resetBubbles();
}

afterEach(() => {
  resetState();
  vi.restoreAllMocks();
});

describe("parseToolDetail：首个 : 切分 + 白名单（TC-M3-14-1）", () => {
  it("tpl:param 按首个 : 切分——param 可含冒号", () => {
    expect(parseToolDetail("read:README.md")).toEqual({ tpl: "read", param: "README.md" });
    expect(parseToolDetail("bash:npm")).toEqual({ tpl: "bash", param: "npm" });
    // macOS 文件名 / grep pattern 含冒号：只切第一个
    expect(parseToolDetail("edit:12:30 final.md")).toEqual({
      tpl: "edit",
      param: "12:30 final.md",
    });
    expect(parseToolDetail("search:TODO:FIXME")).toEqual({
      tpl: "search",
      param: "TODO:FIXME",
    });
  });

  it("五模板白名单全通过；白名单外 tpl 拒绝", () => {
    for (const tpl of ["read", "edit", "bash", "search", "web"]) {
      expect(parseToolDetail(`${tpl}:x`)).toEqual({ tpl, param: "x" });
    }
    expect(parseToolDetail("rm:file.txt")).toBeNull();
    expect(parseToolDetail("exec:sh")).toBeNull();
    expect(parseToolDetail("READ:file")).toBeNull(); // 大小写敏感
  });

  it("param 空 / 纯空白 → 丢弃；无 : / 空 tpl → 丢弃", () => {
    expect(parseToolDetail("read:")).toBeNull();
    expect(parseToolDetail("read:   ")).toBeNull();
    expect(parseToolDetail("read")).toBeNull();
    expect(parseToolDetail(":param")).toBeNull();
    expect(parseToolDetail("")).toBeNull();
    expect(parseToolDetail(123)).toBeNull();
    expect(parseToolDetail(null)).toBeNull();
  });
});

describe("sanitizeToolParam：格式级再净化（TC-M3-14-2，R8）", () => {
  it("单行化 + trim + 去控制字符", () => {
    expect(sanitizeToolParam("a\nb")).toBe("a b");
    expect(sanitizeToolParam("  x  ")).toBe("x");
    expect(sanitizeToolParam("a\u0000b\u007f")).toBe("a b");
  });

  it("≤40 字符截断（按字符计数，中文不劈半截错位）", () => {
    expect(sanitizeToolParam("x".repeat(50))).toHaveLength(TOOL_PARAM_MAX);
    expect(sanitizeToolParam("文件".repeat(25))).toHaveLength(TOOL_PARAM_MAX);
    expect([...sanitizeToolParam("文件".repeat(25))].every((c) => c === "文件"[0] || c === "件")).toBe(true);
  });

  it("净化后为空 → 全链丢弃", () => {
    expect(parseAndSanitize("read:\u0000\u0000")).toBeNull();
  });
});

describe("applyToolDetail：开关判定 + ambient 入队（TC-M3-14-3/5）", () => {
  it("开关开：ambient 入队（source=tool:<tpl>；dwell 由级派生）", () => {
    applyToolDetail("edit:V2-DESIGN.md");
    const bubble = usePetStore.getState().bubble;
    expect(bubble.current?.level).toBe("ambient");
    expect(bubble.current?.source).toBe("tool:edit");
    expect(bubble.current?.text).toBe("正在编辑 V2-DESIGN.md");
    expect(bubble.current?.reminder).toBeUndefined();
  });

  it("文案经 i18n toolb.<tpl> 渲染，语言随 App 即时", async () => {
    await changeLanguage("en");
    try {
      applyToolDetail("bash:npm");
      expect(usePetStore.getState().bubble.current?.text).toBe("Running npm");
      // M2 ambient 语义：不顶替同级 → 第二条入队（不同 source 不合并）
      applyToolDetail("web:maven.aliyun.com");
      const b = usePetStore.getState().bubble;
      expect(b.current?.text).toBe("Running npm");
      expect(b.queue.map((q) => q.text)).toContain("Fetching maven.aliyun.com");
    } finally {
      await changeLanguage("zh");
    }
  });

  it("toolBubbleText 直接渲染五模板", () => {
    expect(toolBubbleText({ tpl: "read", param: "a.md" }, "zh")).toBe("正在读 a.md");
    expect(toolBubbleText({ tpl: "read", param: "a.md" }, "en")).toBe("Reading a.md");
    expect(toolBubbleText({ tpl: "search", param: "foo" }, "en")).toBe("Searching foo");
  });

  it("开关关：静默（不吞事件不报错，插件照发——App 侧过滤）", () => {
    useToolBroadcastStore.getState().setEnabled(false);
    applyToolDetail("edit:X.md");
    expect(usePetStore.getState().bubble.current).toBeNull();
    // 恢复后立即生效（广播语义的 store 位更新）
    useToolBroadcastStore.getState().setEnabled(true);
    applyToolDetail("edit:X.md");
    expect(usePetStore.getState().bubble.current?.source).toBe("tool:edit");
  });

  it("白名单外 / 空白 param：丢弃不入队", () => {
    applyToolDetail("rm:secret");
    applyToolDetail("read:  ");
    expect(usePetStore.getState().bubble.current).toBeNull();
  });
});

describe("parseToolBroadcastEnabled：广播载荷解析", () => {
  it("{enabled:boolean} → 值；非法 → null", () => {
    expect(parseToolBroadcastEnabled({ enabled: true })).toBe(true);
    expect(parseToolBroadcastEnabled({ enabled: false })).toBe(false);
    expect(parseToolBroadcastEnabled({ enabled: "yes" })).toBeNull();
    expect(parseToolBroadcastEnabled(null)).toBeNull();
  });
});

// ---- v2 M6（V2-DESIGN §6.2，TC-M6-03-1）：tool-bubble payload 补 agent ----

describe("applyToolDetail + agent（M6：/state 透传链路 (detail, agent)）", () => {
  it("带 agent：条目 agent 传入（[oc]/[cc] 徽标来源）", () => {
    usePetStore.getState().resetBubbles();
    applyToolDetail("edit:V2-DESIGN.md", "opencode");
    expect(usePetStore.getState().bubble.current?.agent).toBe("opencode");
    usePetStore.getState().resetBubbles();
    applyToolDetail("bash:npm", "claude-code");
    expect(usePetStore.getState().bubble.current?.agent).toBe("claude-code");
  });

  it("agent 缺省（旧载荷/旧事件）→ 条目无 agent（向后兼容，不渲染徽标）", () => {
    usePetStore.getState().resetBubbles();
    applyToolDetail("edit:X.md");
    expect(usePetStore.getState().bubble.current?.agent).toBeUndefined();
  });

  it("parseToolBubblePayload：{detail, agent} 解析；agent 非字符串按缺省", () => {
    expect(parseToolBubblePayload({ detail: "edit:a.md", agent: "opencode" })).toEqual({
      detail: "edit:a.md",
      agent: "opencode",
    });
    expect(parseToolBubblePayload({ detail: "edit:a.md" })).toEqual({
      detail: "edit:a.md",
      agent: null,
    });
    expect(parseToolBubblePayload({ detail: "edit:a.md", agent: 7 })).toEqual({
      detail: "edit:a.md",
      agent: null,
    });
    expect(parseToolBubblePayload(null)).toBeNull();
    expect(parseToolBubblePayload("edit:a.md")).toBeNull();
  });
});
