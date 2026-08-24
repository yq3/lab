/**
 * v2 M1 接入管理前端桥（V2-DESIGN §1.6/§1.7，TC-INT-09）。
 *
 * 与 Rust `integrations.rs` 三命令对齐；类型字段为 Rust IntegrationStatus 的
 * camelCase 序列化（serde rename_all）。doctor message 组装在 Rust 侧
 * （i18n.rs 双语模板），前端只渲染。
 */

/** hook 脚本文件健康快照（与 App 内嵌副本逐字节对账的等价表达）。 */
export interface HookFileStatus {
  exists: boolean;
  matchesBundled: boolean;
}

/** 一条接入的健康快照（§1.4.1 IntegrationStatus）。 */
export interface IntegrationStatus {
  id: string;
  installed: boolean;
  stale: boolean;
  version: string;
  configPath: string;
  hookFile: HookFileStatus;
  /** CC 接入独有（null = 不适用，如 opencode）。 */
  nodeAvailable: boolean | null;
  /** epoch ms；null = App 侧尚未收到该 agent 事件。 */
  lastEventAt: number | null;
  /** 人类可读诊断（Rust i18n.rs 组装，随语言切换重新拉取）。 */
  message: string;
  /** 检测/操作失败原因（非 null → UI「错误」态）。 */
  error: string | null;
}

export type IntegrationId = "opencode" | "claude-code";

function tauriInvoke<T>(cmd: string, args?: Record<string, unknown>): Promise<T> {
  // 动态 import（与 http-bridge 同模式），保持本模块在 vitest/node 下可 import
  return import("@tauri-apps/api/core").then(({ invoke }) => invoke<T>(cmd, args));
}

/** doctor：两接入完整状态（进入设置页 / tauri://focus 时调用）。 */
export function fetchIntegrations(): Promise<IntegrationStatus[]> {
  return tauriInvoke<IntegrationStatus[]>("integrations_status");
}

/** 安装/重装（升级即重装）。 */
export function installIntegration(id: IntegrationId): Promise<IntegrationStatus> {
  return tauriInvoke<IntegrationStatus>("integrations_install", { id });
}

/** 卸载（幂等）。 */
export function uninstallIntegration(id: IntegrationId): Promise<IntegrationStatus> {
  return tauriInvoke<IntegrationStatus>("integrations_uninstall", { id });
}

/** 状态点四态（§1.7：已安装/未安装/需更新/错误）。 */
export type IntegrationUiState = "installed" | "notInstalled" | "stale" | "error";

export function uiStateOf(s: IntegrationStatus): IntegrationUiState {
  if (s.error) return "error";
  if (s.installed) return "installed";
  if (s.stale) return "stale";
  return "notInstalled";
}

/**
 * 组装操作结果行内提示（tester P2-1 修复，TC-INT-07-5）：
 * install/uninstall 命令返回的 `IntegrationStatus.message`（Rust 侧组装，
 * claude-code 卸载/重装含「建议新开 CC 会话」提示）必须展示给用户——
 * doctor 重拉不含该提示。message 为空 → null（不渲染提示条）。
 */
export function composeActionNotice(
  prefix: string,
  status: IntegrationStatus | null,
): string | null {
  const msg = status?.message?.trim();
  if (!msg) return null;
  return `${prefix}${msg}`;
}
