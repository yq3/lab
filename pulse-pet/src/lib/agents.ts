/**
 * v2 registry（docs/v2/agent-registry.md §6.2）：前端 agent 注册表——单一事实源。
 *
 * - 一个 agent 的展示属性（id / 短名 / i18n 键 / 是否有费用数据）只在此定义；
 * - 与 Rust 侧 `src-tauri/src/agents.rs` 的 AGENTS 表经 include_str! 测试互钉
 *   （§6.3：两端 id + short 集合逐项一致，防漂移）；
 * - 新增 agent = 此表加一行 + zh/en i18n 键成对添加（新增指南见
 *   docs/v2/agent-registry.md）。
 *
 * ⚠️ 表条目保持「每 agent 一行 `{ id: "..", short: "..", ... }`」字面格式——
 * Rust 侧互钉测试按此格式做源码匹配（include_str! 源码断言先例，v0.2.1 R4）。
 */

/** 注册表条目。hasCost：该 agent 的统计源是否产出费用数据（CC 恒 0 → 「—」）。 */
export interface AgentSpec {
  id: string;
  short: string;
  /** Token 页 tab / 徽标 title 的 i18n 全名键（现有 camelCase 键名风格，§6.5）。 */
  labelKey: string;
  /** Settings 接入卡名称键。 */
  descKey: string;
  hasCost: boolean;
}

export const AGENTS = [
  { id: "opencode", short: "oc", labelKey: "token.agent.opencode", descKey: "integrations.opencodeDesc", hasCost: true },
  { id: "claude-code", short: "cc", labelKey: "token.agent.claudeCode", descKey: "integrations.claudeDesc", hasCost: false },
] as const satisfies readonly AgentSpec[];

/** 表内 agent id 联合（IntegrationId 等由此派生——tsc 编译期自证）。 */
export type AgentId = (typeof AGENTS)[number]["id"];

/** 查表；未知 id → undefined。 */
export function specOf(agent: string): AgentSpec | undefined {
  return AGENTS.find((a) => a.id === agent);
}

/**
 * agent 短名（opencode→oc / claude-code→cc / task→task；未知 agent 原名兜底）。
 * 原 token-stats.ts `agentShortName` 迁入（§8.2）；气泡徽标 `[oc]` 与今日分布
 * 行 `oc 39M` 共用；技术名约定，i18n 不翻译。
 */
export function shortOf(agent: string): string {
  if (agent === "task") return "task";
  return specOf(agent)?.short ?? agent;
}

/**
 * 会话行徽标文本：查表；**未知 id 显原名**（消静默错误 ②——原 TokenStats.tsx
 * `agentBadgeOf` 三元 else→oc 无兜底，新 agent 会话行会被错标 oc，§4 #8）。
 */
export function badgeOf(agent: string): string {
  return specOf(agent)?.short ?? agent;
}

/** 该 agent 是否有费用数据（cost 列「—」规则：`!hasCostOf(agent)` → 「—」）。 */
export function hasCostOf(agent: string): boolean {
  return specOf(agent)?.hasCost ?? false;
}

/** Settings 接入卡名称键；未知 id → undefined（调用方原名兜底）。 */
export function descKeyOf(id: string): string | undefined {
  return specOf(id)?.descKey;
}
