// PulsePet Claude Code hook 脚本（V2 M1，V2-DESIGN §1.3，TC-INT-01/02）。
//
// CC 每个事件 spawn 一个一次性进程：`node ~/.pulsepet/hooks/claude-code-hook.js
// --pulse-pet-managed`（由 settings.json hooks 里的 shell 包装条目调起）。
// 生命周期：spawn → 读 stdin（≤64KB）→ killswitch 检查 → 分类 → 读 runtime
// 文件 → POST /state（超时 1s）→ exit 0。
//
// 零阻塞三重防护的第三层（脚本级，§1.3.2）：
//   - 任何异常 catch-all → exit 0（进程退出码恒 0，不向 CC 报错）；
//   - 无 stderr 输出（除非 PULSEPET_HOOK_DEBUG=1，且错误文案净化路径）；
//   - 无重试、无退避——一次性进程不存在退避睡眠载体，缺席=丢弃
//     （endpoint/token 文件 ENOENT → 立即返回，复用 v1 §9.4 快速通道语义）。
//   - 不做客户端节流（M1 裁定：CC 事件低频 + POST 幂等覆盖 + App 侧限流兜底）。
//
// 本文件同时导出纯函数（classify*/processHookInput/sanitizeMessage），供 vitest
// 单测（src/lib/claude-code-hook.test.ts，与 pulse-pet-hook.js 同模式）。
//
// 运行环境说明：本文件为 ESM（源仓库 pulse-pet/package.json type:module；vitest
// 直接 import）。安装器（src-tauri/src/integrations.rs）把它拷到
// ~/.pulsepet/hooks/ 时会同时落一份 {"type":"module"} 的 package.json，使
// `node claude-code-hook.js` 以 ESM 加载。

import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { homedir } from "node:os";
import { pathToFileURL } from "node:url";

// 测试命令判定：与 opencode-plugin/pulse-pet-hook.js 的 TEST_CMD_RE 逐字一致
// （TC-INT-01-1 防两处漂移；cargo test / go test 经 "test" 子串天然覆盖）。
const TEST_CMD_RE = /(test|vitest|jest|pytest|npm\s+test|pnpm\s+test|yarn\s+test)/i;

// CC 侧编辑工具全集（Spike S 系 + openpets 粒度补 MultiEdit/NotebookEdit，§1.3.1）。
const EDIT_TOOLS = new Set(["Edit", "Write", "MultiEdit", "NotebookEdit"]);

// stdin payload 上限（openpets 同款 64KB；超出拒收）。
const MAX_STDIN_BYTES = 64 * 1024;

// POST 超时 1s（§1.3.2 生命周期；一次性进程不容久等）。
const POST_TIMEOUT_MS = 1000;

const DEBUG = typeof process !== "undefined" && process.env.PULSEPET_HOOK_DEBUG === "1";

export {
  EDIT_TOOLS,
  MAX_STDIN_BYTES,
  POST_TIMEOUT_MS,
  TEST_CMD_RE,
};

// ---- 归一化分类（纯函数，TC-INT-01） ----

/**
 * 分类 PreToolUse 的工具调用（§1.3.1 映射表）：
 * tool_name ∈ EDIT_TOOLS → editing；Bash 且 tool_input.command 命中测试正则 →
 * testing；其余（Bash 普通命令 / Read / Grep / 未知工具）→ working。
 */
export function classifyToolUse(toolName, toolInput) {
  const tool = String(toolName ?? "");
  if (EDIT_TOOLS.has(tool)) return "editing";
  if (tool === "Bash") {
    const cmd = String(toolInput?.command ?? "");
    return TEST_CMD_RE.test(cmd) ? "testing" : "working";
  }
  return "working";
}

/**
 * 分类 CC hook input（stdin JSON，hook_event_name 为事件名）。
 * 返回归一化 kind；不注册的事件（Notification / SubagentStart / SubagentStop /
 * SessionEnd / PreCompact 等）返回 null（忽略，§1.3.1「不注册」口径——安装
 * 条目与脚本分类均不出现）。
 */
export function classifyHookInput(input) {
  if (typeof input !== "object" || input === null) return null;
  switch (input.hook_event_name) {
    case "SessionStart":
      return "idle"; // --resume 时复位旧 session 残留状态
    case "UserPromptSubmit":
      return "thinking";
    case "PreToolUse":
      return classifyToolUse(input.tool_name, input.tool_input);
    case "PostToolUse":
      return "working"; // 瞬态复位主信号（对齐 opencode tool.execute.after）
    case "PostToolUseFailure":
      return "error"; // petdex + clawd 双参考；下一 Pre/PostToolUse 秒级覆盖自愈
    case "PermissionRequest":
      return "waiting-permission"; // 单向展示（终端审批后经 PostToolUse → working 自愈）
    case "Stop":
      return "idle"; // 与 openpets(success)/clawd(attention) 的分歧记录在案（§1.3.1）
    case "StopFailure":
      return "error";
    default:
      return null;
  }
}

/** stdin payload 是否超限（字节口径）。 */
export function isPayloadTooLarge(byteLength) {
  return byteLength > MAX_STDIN_BYTES;
}

/** 净化错误文案中的家目录路径（仅 PULSEPET_HOOK_DEBUG=1 时输出，openpets 同款）。 */
export function sanitizeMessage(message, homeDir = homedir()) {
  return String(message ?? "").split(String(homeDir)).join("~");
}

function debugLog(message) {
  if (!DEBUG || typeof process === "undefined") return;
  try {
    process.stderr.write(`[pulsepet-cc-hook] ${sanitizeMessage(message)}\n`);
  } catch {
    // stderr 不可写（被重定向到已关闭管道等）时静默——恒 exit 0 契约优先
  }
}

// ---- runtime 文件与 HTTP 投递 ----

export function runtimeDir() {
  if (process.platform === "win32") {
    const base = process.env.LOCALAPPDATA || ".";
    return join(base, "pulsepet", "runtime");
  }
  return join(homedir(), ".pulsepet", "runtime");
}

export function killswitchActive(dir = runtimeDir()) {
  return existsSync(join(dir, "hooks-disabled"));
}

function readRuntimeFile(dir, name) {
  try {
    return readFileSync(join(dir, name), "utf8").trim();
  } catch (err) {
    if (err && err.code === "ENOENT") return null;
    throw err;
  }
}

/**
 * 一次性进程主流程（纯函数化，全部依赖可注入，TC-INT-02 单测入口）。
 *
 * 步骤：超限拒收 → killswitch → JSON 解析 → 分类 → 缺 session_id 丢弃 →
 * endpoint/token ENOENT 快速通道 → POST。任何异常 catch-all，永不 reject
 * （调用方无需 try/catch，进程恒 exit 0）。
 *
 * 返回结果码（测试断言用；运行时只写 debug 日志）：
 * dropped:oversize | skipped:killswitch | dropped:parse | dropped:classify |
 * dropped:session | skipped:no-endpoint | posted | post-failed
 */
export async function processHookInput({
  input = "",
  fetchImpl = fetch,
  dir = runtimeDir(),
} = {}) {
  try {
    if (isPayloadTooLarge(Buffer.byteLength(input))) return "dropped:oversize";
    if (killswitchActive(dir)) return "skipped:killswitch";
    let json;
    try {
      json = JSON.parse(input);
    } catch {
      return "dropped:parse";
    }
    const kind = classifyHookInput(json);
    if (!kind) return "dropped:classify";
    // §1.3.2：CC 侧全事件缺号丢弃（session_id 是 hook input 里唯一可靠会话标识，
    // 较 opencode 侧「仅流式心跳缺号丢弃」更严，不落 default）。
    if (typeof json.session_id !== "string" || !json.session_id) return "dropped:session";
    const endpoint = readRuntimeFile(dir, "endpoint");
    const token = readRuntimeFile(dir, "update-token");
    if (!endpoint || !token) return "skipped:no-endpoint"; // App 未运行：快速跳过
    const res = await fetchImpl(`http://${endpoint}/state`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-pulsepet-token": token,
      },
      body: JSON.stringify({ sessionId: json.session_id, kind, agent: "claude-code" }),
      signal: AbortSignal.timeout(POST_TIMEOUT_MS),
    });
    if (res.status >= 400) return "post-failed";
    return "posted";
  } catch (err) {
    // catch-all：静默失败（debug 模式下净化路径后写 stderr）
    debugLog(`event dropped: ${err && err.message ? err.message : err}`);
    return "post-failed";
  }
}

// ---- CLI 入口（被 CC 的 shell 包装 exec 调起） ----

function readStdinCapped(maxBytes) {
  return new Promise((resolve) => {
    let data = Buffer.alloc(0);
    let done = false;
    const finish = () => {
      if (!done) {
        done = true;
        resolve(data);
      }
    };
    process.stdin.on("data", (chunk) => {
      if (done) return;
      if (data.length + chunk.length > maxBytes) {
        // 超限：拼到 maxBytes+1 证据长度即停（拒收判定够用，不再消费后续）
        data = Buffer.concat([data, chunk]).subarray(0, maxBytes + 1);
        finish();
        return;
      }
      data = Buffer.concat([data, chunk]);
    });
    process.stdin.on("end", finish);
    process.stdin.on("error", finish);
  });
}

const isMain =
  typeof process !== "undefined" &&
  process.argv[1] != null &&
  import.meta.url === pathToFileURL(process.argv[1]).href;

if (isMain) {
  try {
    const input = (await readStdinCapped(MAX_STDIN_BYTES)).toString("utf8");
    const outcome = await processHookInput({ input });
    debugLog(`outcome: ${outcome}`);
  } catch (err) {
    debugLog(`fatal: ${err && err.message ? err.message : err}`);
  }
  // 恒 exit 0：绝不向 CC 报错（§1.3.2 契约）
}
