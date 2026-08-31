/**
 * 例程模板注册表（docs/v2/routine-exec.md Part B §3.3）：matches/build/flags
 * 纯函数钉。opencode build 逐字断言沿用 reminders.test.ts §4.6 既有钉迁移；
 * matches 三正向 + 负例（复合命令 / 裸命令 / 长形式——有意语义：手写不被重拼）；
 * claude CLI 形状经 `claude --help` 实测（2026-08-30：-p/--print 与
 * --dangerously-skip-permissions 存在）。
 */
import { describe, expect, it } from "vitest";
import {
  ROUTINE_TEMPLATES,
  matchOf,
  shellQuote,
  templateOf,
  tplHintKey,
} from "./routine-templates";

describe("Part B：注册表结构（两行初始 + flag 声明）", () => {
  it("hint 键派生：kebab agentId → camelCase 命名空间（§3.2 次要口径）", () => {
    expect(tplHintKey("opencode")).toBe("tasks.tpl.opencode.hint");
    expect(tplHintKey("claude-code")).toBe("tasks.tpl.claudeCode.hint");
  });

  it("opencode / claude-code 各一行，flag 均声明 danger 与 i18n 键", () => {
    expect(ROUTINE_TEMPLATES.map((t) => t.agentId)).toEqual(["opencode", "claude-code"]);
    const oc = templateOf("opencode");
    expect(oc?.flags.map((f) => f.key)).toEqual(["auto"]);
    expect(oc?.flags[0].danger).toBe(true);
    expect(oc?.flags[0].i18nKey).toBe("tasks.tpl.opencode.auto");
    const cc = templateOf("claude-code");
    expect(cc?.flags.map((f) => f.key)).toEqual(["skipPerms"]);
    expect(cc?.flags[0].danger).toBe(true);
    expect(cc?.flags[0].i18nKey).toBe("tasks.tpl.claudeCode.skipPerms");
  });

  it("templateOf 未知 agent → undefined", () => {
    expect(templateOf("nope")).toBeUndefined();
  });
});

describe("Part B：opencode build 逐字（自 reminders.test.ts §4.6 迁移）", () => {
  const build = (name: string, instr: string, flags: Record<string, boolean> = {}) =>
    templateOf("opencode")!.build(name, instr, flags);

  it("逐字模板：--title 前缀 + 可选 --auto + 指令引用（不用 --dir）", () => {
    expect(build("数 md 文件", "数一下仓库有几个 md 文件")).toBe(
      `opencode run --title 'pulsepet 例程: 数 md 文件' '数一下仓库有几个 md 文件'`,
    );
    expect(build("任务A", "做 X", { auto: true })).toBe(
      `opencode run --title 'pulsepet 例程: 任务A' --auto '做 X'`,
    );
    expect(shellQuote("it's")).toBe(`'it'\\''s'`);
    expect(build("n", "don't stop")).not.toMatch(/--dir/);
  });

  it("§二十三：弯引号内容原样保留（内容不归一——单引号串内是合法字面量）", () => {
    expect(build("该喝水啦 💧’", "他说“你好”")).toBe(
      `opencode run --title 'pulsepet 例程: 该喝水啦 💧’' '他说“你好”'`,
    );
  });
});

describe("Part B：claude-code build（claude -p headless）", () => {
  const build = (name: string, instr: string, flags: Record<string, boolean> = {}) =>
    templateOf("claude-code")!.build(name, instr, flags);

  it("基本形态 claude -p '<指令>'；任务名不进命令（CC 无 --title）", () => {
    expect(build("评审 PR", "评审当前分支")).toBe(`claude -p '评审当前分支'`);
  });

  it("skipPerms → 追加 --dangerously-skip-permissions", () => {
    expect(build("x", "跑测试", { skipPerms: true })).toBe(
      `claude -p '跑测试' --dangerously-skip-permissions`,
    );
  });

  it("指令含单引号 → shellQuote 转义", () => {
    expect(build("x", "it's fine")).toBe(`claude -p 'it'\\''s fine'`);
  });
});

describe("Part B：matches（重拼启发式 + 编辑回填反推）", () => {
  it("三正向", () => {
    expect(matchOf("opencode run --title 'x' 'y'")?.agentId).toBe("opencode");
    expect(matchOf("claude -p '评审'")?.agentId).toBe("claude-code");
    expect(matchOf("echo hi")).toBeUndefined();
  });

  it("负例：复合命令 / 裸 opencode run / claude --print 长形式（有意语义）", () => {
    expect(matchOf("cd x && opencode run --title 'x' 'y'")).toBeUndefined();
    expect(matchOf("opencode run")).toBeUndefined();
    expect(matchOf("claude --print 'x'")).toBeUndefined();
  });

  it("build 输出对自身 matches 幂等", () => {
    const oc = templateOf("opencode")!.build("n", "i", {});
    const cc = templateOf("claude-code")!.build("n", "i", {});
    expect(matchOf(oc)?.agentId).toBe("opencode");
    expect(matchOf(cc)?.agentId).toBe("claude-code");
  });
});
