import { describe, expect, it } from "vitest";
import { mergePlugin, uninstallPlugin } from "../../opencode-plugin/opencode-config.mjs";

const SPEC = "./plugins/pulse-pet-hook.js";

/** JSONC → 严格 JSON（字符串感知地去除注释与尾逗号），用于校验合并后仍是合法 JSONC。 */
function jsoncToJson(text: string): unknown {
  let out = "";
  let i = 0;
  const n = text.length;
  while (i < n) {
    const c = text[i];
    if (c === '"') {
      const start = i;
      i += 1;
      while (i < n && text[i] !== '"') {
        if (text[i] === "\\") i += 2;
        else i += 1;
      }
      i += 1; // 闭合引号
      out += text.slice(start, i);
      continue;
    }
    if (c === "/" && text[i + 1] === "/") {
      while (i < n && text[i] !== "\n") i += 1;
      continue;
    }
    if (c === "/" && text[i + 1] === "*") {
      i += 2;
      while (i < n && !(text[i] === "*" && text[i + 1] === "/")) i += 1;
      i = Math.min(i + 2, n);
      continue;
    }
    if (c === ",") {
      let j = i + 1;
      while (j < n && /\s/.test(text[j])) j += 1;
      if (text[j] === "}" || text[j] === "]") {
        i += 1; // 尾逗号：跳过
        continue;
      }
      out += c;
      i += 1;
      continue;
    }
    out += c;
    i += 1;
  }
  return JSON.parse(out);
}

describe("mergePlugin：JSONC 感知幂等合并（TC-EV-01）", () => {
  it("往已有 plugin 数组合并插件路径项，带 managed 标记，保留用户项", () => {
    const out = mergePlugin('{\n  "plugin": ["my-plugin"]\n}');
    expect(out).toContain(`"${SPEC}"`);
    expect(out).toContain("--pulse-pet-managed");
    expect(out).toContain('"my-plugin"');
    expect(jsoncToJson(out)).toEqual({ plugin: ["my-plugin", SPEC] });
  });

  it("重复安装幂等（不产生重复项）", () => {
    const once = mergePlugin('{\n  "plugin": ["my-plugin"]\n}');
    const twice = mergePlugin(once);
    expect(twice).toBe(once);
    expect(jsoncToJson(once)).toEqual({ plugin: ["my-plugin", SPEC] });
  });

  it("保留注释与尾逗号，合并后仍为合法 JSONC", () => {
    const src = [
      "{",
      '  // 用户注释',
      '  "$schema": "https://opencode.ai/config.json",',
      '  "plugin": [',
      '    "foo", // 尾逗号',
      "  ],",
      "}",
    ].join("\n");
    const out = mergePlugin(src);
    expect(out).toContain("// 用户注释");
    expect(out).toContain('"foo", // 尾逗号');
    expect(out).toContain(`"${SPEC}"`);
    expect(jsoncToJson(out)).toEqual({
      $schema: "https://opencode.ai/config.json",
      plugin: ["foo", SPEC],
    });
  });

  it("无 plugin 键时新增", () => {
    const out = mergePlugin('{\n  "$schema": "https://opencode.ai/config.json"\n}');
    expect(out).toContain('"plugin"');
    expect(out).toContain(`"${SPEC}"`);
    expect(jsoncToJson(out)).toEqual({
      $schema: "https://opencode.ai/config.json",
      plugin: [SPEC],
    });
  });

  it("空 plugin 数组合并", () => {
    const out = mergePlugin('{\n  "plugin": []\n}');
    expect(jsoncToJson(out)).toEqual({ plugin: [SPEC] });
  });

  it("已有尾逗号的非空数组合并", () => {
    const out = mergePlugin('{\n  "plugin": ["a", "b",]\n}');
    expect(jsoncToJson(out)).toEqual({ plugin: ["a", "b", SPEC] });
  });

  // ---- P2-9（M2 遗留）：tokenizer 零消费死循环修复 + block 注释用例 ----

  it("block 注释正确跳过，合并仍成功（P2-9 测试缺口）", () => {
    const src = [
      "{",
      "  /* 顶部块注释，",
      "     跨行 */",
      '  "plugin": [',
      '    "foo" /* 行内块注释 */',
      "  ]",
      "}",
    ].join("\n");
    const out = mergePlugin(src);
    expect(out).toContain("/* 顶部块注释，");
    expect(out).toContain("/* 行内块注释 */");
    expect(jsoncToJson(out)).toEqual({ plugin: ["foo", SPEC] });
  });

  it("非法 JSONC 字符（@/单引号/emoji）不挂死，返回有限结果（P2-9）", () => {
    // 旧实现 literal 分支零消费 → while 死循环 → install.sh 挂死；
    // 本用例能跑完即证明 tokenizer 总在推进。
    const cases = [
      '{\n  "plugin": ["a"],\n  "x": @\n}',
      "{\n  'plugin': ['a']\n}",
      '{\n  "plugin": ["a"], /* \u{1f600} */ "y": 1\n}',
    ];
    for (const src of cases) {
      const out = mergePlugin(src);
      expect(typeof out).toBe("string");
      expect(out.length).toBeGreaterThan(0);
    }
    // 非法但 plugin 数组仍可定位时，合并照常完成（幂等安装不受影响）。
    // jsoncToJson 是测试用严格转换器（不认 @），先把非法字面量替换回合法值再校验结构。
    const out = mergePlugin('{\n  "plugin": ["a"],\n  "x": @\n}');
    expect(jsoncToJson(out.replace('"x": @', '"x": null'))).toEqual({
      plugin: ["a", SPEC],
      x: null,
    });
    // 幂等仍成立（TC-EV-01）：二次合并原样返回
    expect(mergePlugin(out)).toBe(out);
  });
});

describe("uninstallPlugin：只移除 managed 项（TC-EV-02）", () => {
  it("移除插件项，保留用户原有 plugin", () => {
    const src = mergePlugin('{\n  "plugin": ["foo", "bar"]\n}');
    const out = uninstallPlugin(src);
    expect(out).not.toContain(`"${SPEC}"`);
    expect(out).not.toContain("--pulse-pet-managed");
    expect(out).toContain('"foo"');
    expect(out).toContain('"bar"');
    expect(jsoncToJson(out)).toEqual({ plugin: ["foo", "bar"] });
  });

  it("未安装时卸载幂等（原样返回）", () => {
    const src = '{\n  "plugin": ["foo"]\n}';
    expect(uninstallPlugin(src)).toBe(src);
  });

  it("卸载后仍是合法 JSONC，且不再含插件项", () => {
    const installed = mergePlugin('{\n  "plugin": ["foo"]\n}');
    const out = uninstallPlugin(installed);
    expect(jsoncToJson(out)).toEqual({ plugin: ["foo"] });
  });
});
