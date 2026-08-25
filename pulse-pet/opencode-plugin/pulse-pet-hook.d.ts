// 类型声明：opencode-plugin/pulse-pet-hook.js 的纯函数导出（仅供前端 tsc 类型检查，
// 不随 install 脚本拷贝；插件本体在 opencode Bun 运行时加载）。

export const KINDS: readonly string[];

export function isSelfTool(tool: unknown): boolean;

export function classifyEvent(event: unknown): string | null;

export function classifyToolBefore(
  tool: unknown,
  args?: unknown,
  command?: unknown,
): string | null;

export function bucketFor(kind: string): string | null; // v0.1.3：idle → null（节流豁免，永远放行）

export class Throttle {
  constructor(now?: () => number);
  shouldSend(kind: string): boolean;
}

// v0.1.3 四-2：thinking 粘性窗口——thinking 后 STICKY_MS 内吞同 session 的
// working/idle（节流前判定、不占桶）；更高优先级事件自然穿透。
export class ThinkingSticky {
  constructor(now?: () => number);
  arm(sessionId: string): void;
  swallows(kind: string, sessionId: string): boolean;
}

export const STICKY_MS: number;

export class Backoff {
  constructor(sleepFn?: (ms: number) => Promise<unknown>);
  nextDelay(): number;
  wait(): Promise<number>;
  reset(): void;
}

export const BUBBLE_POOL: Readonly<Record<string, readonly string[]>>;

// ---- v2 M3 工具级气泡：detail 模板 ID 协议（V2-DESIGN §3.7.1）----

/** 工具族 → 模板 ID 白名单映射（read/edit/bash/search/web 五模板）。 */
export const DETAIL_TPLS: Readonly<Record<string, ReadonlySet<string>>>;

/** 工具 → 模板 ID（白名单外 → null）。 */
export function detailTplOf(tool: unknown): string | null;

/** 路径 basename（按 / 与 \ 切分取末段非空）。 */
export function basenameOf(s: unknown): string;

export const DETAIL_PARAM_MAX: number;

/** detail param 提取净化（read/edit basename、bash 剥 env 赋值取首词、
 * search ≤40 pattern、web hostname；无参/失败 → null）。 */
export function extractDetailParam(tool: unknown, args?: unknown): string | null;

/** detail = "<tplId>:<param>" 组装（失败 → null 不携带）。 */
export function buildDetail(tool: unknown, args?: unknown): string | null;

export const DETAIL_COOLDOWN_MS: number;

/** detail 独立 20s 单桶（与 speech 桶同参数非复用；消耗不因网络失败回滚）。 */
export class DetailThrottle {
  constructor(now?: () => number);
  shouldSend(): boolean;
}

export function bubbleCategoryFor(kind: string): string | null;

export function sanitizeText(text: unknown): string;

export function pickBubble(kind: string, index?: number): string;

export function runtimeDir(): string;
export function killswitchActive(dir?: string): boolean;
export function postState(
  kind: string,
  sessionId: string,
  agent?: string,
  fetchImpl?: (
    input: string,
    init?: Record<string, unknown>,
  ) => Promise<{ status: number }>,
  dir?: string,
  detail?: string | null,
): Promise<unknown | null>; // null = App 未运行（runtime 文件缺失）：跳过，不退避

export interface Deliverer {
  /** v2 M3：可选 detail（仅 tool.execute.before 路径携带；reaction 放行后判定）。 */
  deliver(kind: string | null, sessionId?: string, detail?: string | null): Promise<void>;
}

export function createDeliverer(opts?: {
  throttle?: { shouldSend(kind: string): boolean };
  backoff?: Backoff;
  postStateImpl?: typeof postState;
  killswitch?: () => boolean;
  agent?: string;
  sticky?: ThinkingSticky;
  detailThrottle?: DetailThrottle;
}): Deliverer;

// 注册给 opencode 的 Hooks：全部 fire-and-forget（返回 void，绝不返回投递
// promise——宿主会同步 await 每个钩子且无超时，详见 pulse-pet-hook.js 头注）。
export function buildHooks(deliverer?: Deliverer): {
  event: (input: { event?: unknown }) => void;
  "chat.message": (input?: { sessionID?: string }) => void;
  "permission.ask": (input?: { sessionID?: string }) => void;
  "tool.execute.before": (
    input?: { tool?: unknown; sessionID?: string },
    output?: { args?: unknown },
  ) => void;
  "tool.execute.after": (input?: { tool?: unknown; sessionID?: string }) => void;
  "command.execute.before": (input?: { command?: string; sessionID?: string }) => void;
};
