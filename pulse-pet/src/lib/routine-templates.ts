/**
 * 例程模板注册表（docs/v2/routine-exec.md Part B §3.3，2026-08-30 定稿）：
 * 前端单侧 `ROUTINE_TEMPLATES`——每 agent 一行（matches / build / flags），
 * 加新 agent 例程 = 此表一行 + i18n 键对，UI 零改动（chips 文案复用
 * agents.ts `labelKey`，无需 per-agent title 键）。
 *
 * - 模板纯填表辅助，**执行层不感知 agent**（§4.6 原则延伸）；
 * - matches = startsWith 前缀形态（比 includes 严——复合命令如
 *   `cd x && opencode run …` 不被自动重拼，有意语义）；裸 `opencode run`
 *   （无尾空格）与 `claude --print`（长形式）不匹配——手写不被重拼；
 *   build 输出对自身 matches 幂等（重拼稳定）；
 * - shellQuote 自 reminders.ts 迁入本表供两行 build 共用（reminders.ts 旧定义
 *   已清退）；reminders 单向 import routine-templates（execFromParams 需
 *   matchOf），无循环依赖；
 * - claude CLI 形状经 `claude --help` 实测（2026-08-30）：`-p, --print`
 *   "Print response and exit" + `--dangerously-skip-permissions`
 *   "Bypass all permission checks" 存在；任务名不进命令（CC 无 --title，
 *   例程会话在 Token 页无 ⚡ 徽标——已裁定接受边界）。
 */
import type { AgentId } from "./agents";

/** 单个模板 flag 的声明。label/hint 键 = `i18nKey` / `i18nKey + "Hint"` 派生。 */
export interface RoutineFlagSpec {
  key: string;
  i18nKey: string;
  danger: boolean;
}

/**
 * 例程模板行。flags 值只认布尔（未来带值 flag 如 `--model xxx` 需结构升级，
 * 且与 Rust validate「所有值布尔」校验两处锁步改——routine-exec.md P3-3 备忘）。
 */
export interface RoutineTemplateSpec {
  agentId: AgentId | string;
  /** 重拼启发式 + 编辑回填反推（判定永远看 command，不看 chips 选中态）。 */
  matches: (command: string) => boolean;
  build: (taskName: string, instruction: string, flags: Record<string, boolean>) => string;
  flags: RoutineFlagSpec[];
}

/** POSIX 单引号安全引用（sh -c 双层语义下最稳的引用形态）。 */
export function shellQuote(s: string): string {
  return `'${s.replace(/'/g, `'\\''`)}'`;
}

export const ROUTINE_TEMPLATES: RoutineTemplateSpec[] = [
  {
    agentId: "opencode",
    matches: (c) => c.startsWith("opencode run "),
    build: (taskName, instruction, flags) => {
      const title = `pulsepet 例程: ${taskName.trim()}`;
      const autoFlag = flags.auto ? " --auto" : "";
      return `opencode run --title ${shellQuote(title)}${autoFlag} ${shellQuote(instruction.trim())}`;
    },
    flags: [{ key: "auto", i18nKey: "tasks.tpl.opencode.auto", danger: true }],
  },
  {
    agentId: "claude-code",
    matches: (c) => c.startsWith("claude -p "),
    // 任务名只进 PulsePet label 不进命令（CC 无 --title，审查 P2-1 口径）
    build: (_taskName, instruction, flags) =>
      `claude -p ${shellQuote(instruction.trim())}` +
      (flags.skipPerms ? " --dangerously-skip-permissions" : ""),
    flags: [{ key: "skipPerms", i18nKey: "tasks.tpl.claudeCode.skipPerms", danger: true }],
  },
];

/** 按 agentId 查行；未知 → undefined。 */
export function templateOf(agentId: string): RoutineTemplateSpec | undefined {
  return ROUTINE_TEMPLATES.find((t) => t.agentId === agentId);
}

/** 按 command 前缀形态反推模板行（重拼启发式 + 编辑回填）；无匹配 → undefined。 */
export function matchOf(command: string): RoutineTemplateSpec | undefined {
  return ROUTINE_TEMPLATES.find((t) => t.matches(command));
}

/** 模板 hint 键派生：kebab agentId → camelCase 命名空间（tasks.tpl.<camel>.hint）。 */
export function tplHintKey(agentId: string): string {
  return `tasks.tpl.${agentId.replace(/-([a-z])/g, (_, c: string) => c.toUpperCase())}.hint`;
}
