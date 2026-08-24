// 类型声明：opencode-plugin/claude-code-hook.js 的纯函数导出（仅供前端 tsc
// 类型检查，不随安装器拷贝；hook 本体由 node 以一次性进程加载，v2 M1）。

// CC 侧编辑工具全集（Edit/Write/MultiEdit/NotebookEdit）。
export const EDIT_TOOLS: ReadonlySet<string>;

// stdin payload 上限（64KB）。
export const MAX_STDIN_BYTES: number;

// POST 超时（1s）。
export const POST_TIMEOUT_MS: number;

// 测试命令判定正则——与 pulse-pet-hook.js 的 TEST_CMD_RE 逐字一致（TC-INT-01-1）。
export const TEST_CMD_RE: RegExp;

/** PreToolUse 工具分类：editing / testing / working（§1.3.1 映射）。 */
export function classifyToolUse(
  toolName: unknown,
  toolInput?: { command?: unknown } | Record<string, unknown>,
): string;

/** CC hook input → kind；不注册的事件返回 null。 */
export function classifyHookInput(input: unknown): string | null;

/** stdin payload 是否超限（字节口径）。 */
export function isPayloadTooLarge(byteLength: number): boolean;

/** 净化错误文案中的家目录路径（仅 PULSEPET_HOOK_DEBUG=1 时输出）。 */
export function sanitizeMessage(message: unknown, homeDir?: string): string;

export function runtimeDir(): string;
export function killswitchActive(dir?: string): boolean;

/**
 * 一次性进程主流程（依赖可注入）。永不 reject（恒 exit 0 契约）。
 * 结果码：dropped:oversize | skipped:killswitch | dropped:parse |
 * dropped:classify | dropped:session | skipped:no-endpoint | posted | post-failed
 */
export function processHookInput(opts?: {
  input?: string;
  fetchImpl?: (
    input: string,
    init?: Record<string, unknown>,
  ) => Promise<{ status: number }>;
  dir?: string;
}): Promise<string>;
