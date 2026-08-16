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

export function bucketFor(kind: string): string | null;

export class Throttle {
  constructor(now?: () => number);
  shouldSend(kind: string): boolean;
}

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
): Promise<unknown>;

export interface Deliverer {
  deliver(kind: string | null, sessionId?: string): Promise<void>;
}

export function createDeliverer(opts?: {
  throttle?: { shouldSend(kind: string): boolean };
  backoff?: Backoff;
  postStateImpl?: typeof postState;
  killswitch?: () => boolean;
  agent?: string;
}): Deliverer;
