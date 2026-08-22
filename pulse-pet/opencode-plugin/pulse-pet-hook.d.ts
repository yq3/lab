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
): Promise<unknown | null>; // null = App 未运行（runtime 文件缺失）：跳过，不退避

export interface Deliverer {
  deliver(kind: string | null, sessionId?: string): Promise<void>;
}

export function createDeliverer(opts?: {
  throttle?: { shouldSend(kind: string): boolean };
  backoff?: Backoff;
  postStateImpl?: typeof postState;
  killswitch?: () => boolean;
  agent?: string;
  sticky?: ThinkingSticky;
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
  "command.execute.before": (input?: { command?: string }) => void;
};
