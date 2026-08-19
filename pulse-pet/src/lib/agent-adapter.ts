/**
 * AgentAdapter 抽象（DESIGN §3.4，TC-EV-23）。
 *
 * v1 仅实现 OpenCodeAdapter（见 ./adapters/opencode.ts）。插件侧已把原始事件归一化，
 * 本抽象层 `normalizeRawEvent` 作兜底；token 读取在 Rust 侧（M3），此处只声明
 * `tokenSource` 语义。新增 adapter（如 ClaudeCodeAdapter）只需新增文件，不改主链路。
 */

import type { NormalizedState } from "./state";

/** token 数据来源（M3 起使用；v1 仅声明）。 */
export type TokenSource =
  | "opencode-sqlite"
  | "transcript-incremental"
  | "telemetry"
  | "estimate";

/** 归一化事件（与插件 POST /state 的 body 一致）。 */
export interface NormalizedEvent {
  sessionId: string;
  kind: NormalizedState;
  agent: string;
  project?: string;
  detail?: string;
}

export interface AgentAdapter {
  /** "opencode" / "claude-code" / ... */
  readonly id: string;
  /** 把原始事件归一化（插件侧已归一化，此层兜底）。返回 null 表示忽略。 */
  normalizeRawEvent(raw: unknown): NormalizedEvent | null;
  readonly tokenSource: TokenSource;
  /** 图标集 id（"opencode" / "claude-code" / "codex" / ...）。 */
  readonly iconSet: string;
}
