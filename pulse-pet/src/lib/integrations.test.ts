import { describe, expect, it } from "vitest";
import {
  composeActionNotice,
  focusRefreshAllowed,
  INTG_FOCUS_REFRESH_COOLDOWN_MS,
  uiStateOf,
  type IntegrationStatus,
} from "./integrations";
import { t, DICT } from "./i18n";

/** 构造一条 IntegrationStatus（字段缺省按健康值）。 */
function st(over: Partial<IntegrationStatus> = {}): IntegrationStatus {
  return {
    id: "claude-code",
    installed: false,
    stale: false,
    version: "0.2.0",
    configPath: "/x/settings.json",
    hookFile: { exists: true, matchesBundled: true },
    nodeAvailable: true,
    lastEventAt: null,
    message: "",
    error: null,
    ...over,
  };
}

describe("uiStateOf：状态点四态（V2-DESIGN §1.7）", () => {
  it("error > installed > stale > notInstalled 决策", () => {
    expect(uiStateOf(st({ error: "boom", installed: true }))).toBe("error");
    expect(uiStateOf(st({ installed: true }))).toBe("installed");
    expect(uiStateOf(st({ stale: true }))).toBe("stale");
    expect(uiStateOf(st())).toBe("notInstalled");
  });
});

describe("composeActionNotice：操作结果提示（tester P2-1 / TC-INT-07-5）", () => {
  it("Rust 返回 message → 前缀 + 全文（卸载提示必须可见）", () => {
    const status = st({
      message: "未安装 · node 已就绪 · 最近无事件 · 已卸载；如 CC 会话仍在运行，建议新开会话使其生效",
    });
    expect(composeActionNotice("操作完成：", status)).toBe(
      "操作完成：未安装 · node 已就绪 · 最近无事件 · 已卸载；如 CC 会话仍在运行，建议新开会话使其生效",
    );
  });

  it("message 空/空白 → null（不渲染提示条）；status null → null", () => {
    expect(composeActionNotice("操作完成：", st({ message: "" }))).toBeNull();
    expect(composeActionNotice("操作完成：", st({ message: "   " }))).toBeNull();
    expect(composeActionNotice("操作完成：", null)).toBeNull();
  });

  it("i18n 前缀键双语言齐备（zh/en 键集合一致由完备性测试守护）", () => {
    expect(t("integrations.actionDone")).toBe("操作完成：");
    expect(t("integrations.actionDone", undefined, "en")).toBe("Done: ");
    expect("integrations.actionDone" in DICT.zh).toBe(true);
    expect("integrations.actionDone" in DICT.en).toBe(true);
  });
});

describe("v2 M2 L2（P3-1）：提示条语言不烘焙——渲染时以当前语言现拼", () => {
  it("同一 status 在 zh/en 前缀下产出不同文案（Settings 渲染时现算，语言切换即跟随）", () => {
    const status = st({ message: "已安装 · v0.2.0" });
    const zh = composeActionNotice(t("integrations.actionDone", undefined, "zh"), status);
    const en = composeActionNotice(t("integrations.actionDone", undefined, "en"), status);
    expect(zh).toBe("操作完成：已安装 · v0.2.0");
    expect(en).toBe("Done: 已安装 · v0.2.0");
    expect(zh).not.toBe(en);
  });
});

describe("focusRefreshAllowed：focus 触发 doctor 刷新冷却（issue #19 防自激励）", () => {
  it("从未调用过 doctor（null）→ 放行（mount 后首个 focus 正常刷新）", () => {
    expect(focusRefreshAllowed(null, 12345)).toBe(true);
  });

  it("距上次 doctor 调用不足冷却窗 → 拒绝（掐断「探测 → 闪窗 → 重获焦点 → 再探测」循环第一圈）", () => {
    const t0 = 1_000_000;
    // 实测循环圈长 ≈ probe(200ms) + 派发(35ms)，远小于 3s 冷却
    expect(focusRefreshAllowed(t0, t0 + 235)).toBe(false);
    expect(focusRefreshAllowed(t0, t0 + INTG_FOCUS_REFRESH_COOLDOWN_MS - 1)).toBe(false);
  });

  it("距上次 doctor 调用 ≥ 冷却窗 → 放行（真实用户切走再切回仍刷新）", () => {
    const t0 = 1_000_000;
    expect(focusRefreshAllowed(t0, t0 + INTG_FOCUS_REFRESH_COOLDOWN_MS)).toBe(true);
    expect(focusRefreshAllowed(t0, t0 + 60_000)).toBe(true);
  });

  it("冷却时长为 3s（钉住常量，调阈值须连动本组用例语义）", () => {
    expect(INTG_FOCUS_REFRESH_COOLDOWN_MS).toBe(3000);
  });
});
