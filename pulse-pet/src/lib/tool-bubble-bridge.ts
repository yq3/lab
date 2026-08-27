/**
 * tool-bubble-bridge：v2 M3 工具级气泡 pet 桥（V2-DESIGN §3.7.2，TC-M3-14）。
 *
 * ① 解析：detail = "<tplId>:<param>" 按**首个** `:` 切分（param 可含 `:`——
 *    macOS 文件名 / grep pattern 均合法）；tplId 白名单（read/edit/bash/
 *    search/web）外的值或 param 空/纯空白 → 丢弃；
 * ② param 再净化（格式级兜底，R8：单行、≤40 字符、去控制字符——路径/参数
 *    剥除责任完全在插件提取层）；
 * ③ 开关 store：启动 `tool_broadcast_get` 初始化 + 订阅
 *    `pulsepet://tool-broadcast` 实时更新（panel set → Rust 定向广播 → 即时
 *    静默/恢复，无需重启）；热路径判定只读 store 位（零 IPC）；
 * ④ 通过 → `pushBubble({level:"ambient", source:"tool:<tplId>"})`（dwell 由
 *    级派生 4s；M2 ambient 语义可顶可丢）；文案经 i18n `toolb.<tplId>` 渲染
 *    （语言随 App 即时）。
 *
 * Rust 侧（lib.rs/http_server.rs）只做字符串非空校验 + emit_to("pet",
 * "pulsepet://tool-bubble", {detail}) 原样透传——不解析不判开关（N8）。
 */

import { create } from "zustand";
import { usePetStore } from "../pet/petStore";
import { t } from "./i18n";

/** Rust 广播工具播报开关变化的 Tauri event 名（与 interaction.rs 常量一致）。 */
export const TOOL_BROADCAST_EVENT = "pulsepet://tool-broadcast";

/** Rust 下发 detail 透传的 Tauri event 名。 */
export const TOOL_BUBBLE_EVENT = "pulsepet://tool-bubble";

/** 模板白名单（§3.7.1 表；双侧各自测试钉同一常量表，文档为唯一权威，R4）。 */
export const TOOL_TPLS = ["read", "edit", "bash", "search", "web"] as const;
export type ToolTpl = (typeof TOOL_TPLS)[number];

/** param 再净化上限（格式级兜底，与插件侧提取同口径）。 */
export const TOOL_PARAM_MAX = 40;

/** 解析结果：tpl ∈ 白名单 且 param 非空。 */
export interface ToolDetail {
  tpl: ToolTpl;
  param: string;
}

/** 按首个 `:` 切分 + 白名单校验 + param 空白丢弃（再净化另走 sanitizeToolParam）。 */
export function parseToolDetail(detail: unknown): ToolDetail | null {
  if (typeof detail !== "string") return null;
  const sep = detail.indexOf(":");
  if (sep <= 0) return null; // 无 tpl / 空 tpl
  const tpl = detail.slice(0, sep);
  if (!(TOOL_TPLS as readonly string[]).includes(tpl)) return null; // 白名单外
  const rawParam = detail.slice(sep + 1);
  if (!rawParam.trim()) return null; // 空 / 纯空白
  return { tpl: tpl as ToolTpl, param: rawParam };
}

/** param 格式级再净化：去控制字符、单行化、trim、≤40 字符（R8 兜底）。 */
export function sanitizeToolParam(p: string): string {
  const s = p
    // 去控制字符（C0 + C1 段），单行化（\r\n\t → 空格）
    .replace(/[\u0000-\u001f\u007f-\u009f]/g, " ")
    .trim();
  if (!s) return "";
  return [...s].length > TOOL_PARAM_MAX ? [...s].slice(0, TOOL_PARAM_MAX).join("") : s;
}

/** 解析 + 再净化全链（净化后为空也丢弃）。 */
export function parseAndSanitize(detail: unknown): ToolDetail | null {
  const parsed = parseToolDetail(detail);
  if (!parsed) return null;
  const param = sanitizeToolParam(parsed.param);
  if (!param) return null;
  return { tpl: parsed.tpl, param };
}

// ---- 开关 store（panel/pet 双 webview 各持一份；跨窗口同步经 Rust 广播） ----

interface ToolBroadcastState {
  /** 默认 true（Rust app_state 缺省；未知/初始化前保持 true = 不吞气泡）。 */
  enabled: boolean;
  setEnabled: (enabled: boolean) => void;
}

export const useToolBroadcastStore = create<ToolBroadcastState>((set) => ({
  enabled: true,
  setEnabled: (enabled) => set({ enabled }),
}));

/** 气泡文案（i18n toolb.<tpl>；语言随 App 即时——渲染时取当前 store 语言）。 */
export function toolBubbleText(d: ToolDetail, lang?: Parameters<typeof t>[2]): string {
  return t(`toolb.${d.tpl}`, { p: d.param }, lang);
}

/**
 * 应用一条 detail：解析 → 白名单/净化 → 开关判定（只读 store 位，零 IPC）→
 * ambient 入队（source="tool:<tplId>"；dwell 由级派生）。
 * v2 M6（§6.2，TC-M6-03-1）：+agent（Rust `/state` 透传链路 (detail, agent)——
 * [oc]/[cc] 徽标数据源；缺省不带——旧载荷向后兼容）。
 */
export function applyToolDetail(detail: unknown, agent?: unknown): void {
  if (!useToolBroadcastStore.getState().enabled) return; // 开关关：静默（插件照发）
  const d = parseAndSanitize(detail);
  if (!d) return; // 白名单外 / param 空：丢弃（不发气泡）
  const a = typeof agent === "string" && agent ? agent : undefined;
  usePetStore.getState().pushBubble({
    text: toolBubbleText(d),
    level: "ambient",
    source: `tool:${d.tpl}`,
    ...(a ? { agent: a } : {}),
  });
}

/** v2 M6：`pulsepet://tool-bubble` payload `{detail, agent}`（agent 缺省 null）。 */
export interface ToolBubblePayload {
  detail: unknown;
  agent: string | null;
}

/** 解析 `pulsepet://tool-bubble` 载荷；payload 非对象 → null（agent 非字符串按缺省）。 */
export function parseToolBubblePayload(payload: unknown): ToolBubblePayload | null {
  if (typeof payload !== "object" || payload === null) return null;
  const p = payload as { detail?: unknown; agent?: unknown };
  const agent = typeof p.agent === "string" && p.agent ? p.agent : null;
  return { detail: p.detail, agent };
}

/** 解析 `pulsepet://tool-broadcast` 载荷；非法 → null。 */
export function parseToolBroadcastEnabled(payload: unknown): boolean | null {
  if (typeof payload === "object" && payload !== null && "enabled" in payload) {
    const v = (payload as { enabled: unknown }).enabled;
    if (typeof v === "boolean") return v;
  }
  return null;
}

/**
 * pet 窗启动桥接：get 初始化 store 位 + 订阅 detail 透传与开关广播。
 * 非 Tauri 环境（vitest / 纯浏览器 dev）直接返回。
 */
export async function initToolBubbleBridge(): Promise<void> {
  if (typeof window === "undefined") return;
  if (!(window as unknown as { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__) {
    return;
  }
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    const enabled = await invoke<boolean>("tool_broadcast_get");
    useToolBroadcastStore.getState().setEnabled(enabled);
  } catch (e) {
    console.error("[pulsepet] tool broadcast init failed:", e); // 保持默认 true
  }
  const { listen } = await import("@tauri-apps/api/event");
  await listen(TOOL_BUBBLE_EVENT, (event) => {
    // v2 M6：payload {detail, agent}（agent 透传自 /state body——徽标数据源）
    const p = parseToolBubblePayload(event.payload);
    if (!p) return;
    applyToolDetail(p.detail, p.agent);
  });
  await listen(TOOL_BROADCAST_EVENT, (event) => {
    const v = parseToolBroadcastEnabled(event.payload);
    if (v !== null) useToolBroadcastStore.getState().setEnabled(v);
  });
}

// ---- panel 侧（设置页开关）：invoke 封装 ----

/** 查询工具播报开关（panel 开关初始显示值经 get 初始化，N13）。 */
export async function fetchToolBroadcast(): Promise<boolean> {
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<boolean>("tool_broadcast_get");
}

/** 设置工具播报开关（Rust 持久化 + 定向 pet 窗广播 → 即时静默/恢复）。 */
export async function setToolBroadcast(enabled: boolean): Promise<boolean> {
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<boolean>("tool_broadcast_set", { enabled });
}
