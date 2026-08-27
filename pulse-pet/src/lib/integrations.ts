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

// ---- focus 触发刷新冷却（issue #19 防自激励加固） ----

/** focus 触发 doctor 刷新的冷却窗口：距上一次任意 doctor 调用 3s 内的 focus 事件不刷新。 */
export const INTG_FOCUS_REFRESH_COOLDOWN_MS = 3000;

/**
 * focus 触发的 doctor 刷新是否放行（冷却判定，纯函数，issue #19）。
 *
 * 背景：doctor 每次调用 spawn `node --version` 探测；Windows release（GUI
 * 子系统）下若 spawn 闪控制台窗扰动焦点，focus 事件与 doctor 会构成
 * 「探测 → 闪窗 → 重获焦点 → 再探测」的自激励死循环（~4 轮/s）。以「上次
 * 任意 doctor 调用时刻」为基准冷却 focus 路径，循环在第一圈即被掐断。
 *
 * 仅限 focus 触发路径：mount / `panel://tab` / 安装操作后的重拉不受限
 * （保持「重开面板即刷新」语义）。Rust 侧 CREATE_NO_WINDOW（R1）为主修复，
 * 本冷却为第二道防线。
 */
export function focusRefreshAllowed(
  lastDoctorAt: number | null,
  now: number,
): boolean {
  if (lastDoctorAt == null) return true;
  return now - lastDoctorAt >= INTG_FOCUS_REFRESH_COOLDOWN_MS;
}
