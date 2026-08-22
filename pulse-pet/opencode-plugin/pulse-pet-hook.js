// PulsePet opencode 插件（DESIGN §3.1，TC-EV-04~10 / TC-EV-18~21 / TC-SEC-01~02）。
//
// 监听 opencode 官方 hooks → 归一化 kind → POST /state 到 PulsePet 桌面 App。
// 本文件同时导出纯函数（classify*/Throttle/Backoff/sanitize*），便于 vitest 单测。
//
// ===========================================================================
// 状态复位实测结论（TC-EV-05，M2 done 补充验证项①，基于 opencode 1.18.18 +
// @opencode-ai/plugin 1.17.13 的 SDK 类型定义实测）：
//   - `tool.execute.after` hook **存在**：签名 (input:{tool,sessionID,callID,args})，
//     在编辑/测试工具完成后触发 → 作为「瞬态 → working」的**主复位信号**。
//   - `chat.message` hook **存在**：签名 (input:{sessionID,agent,model,messageID,
//     variant})，在用户发新消息时触发（模型开始思考）→ thinking；opencode 无
//     独立的「chat.message 完成」事件。
//   - 兜底复位信号：`event` bus 的 `session.status`（SessionStatus = idle|busy|retry），
//     非 idle → working；另有专用 `session.idle` 事件 → idle。
//   据此定案：主复位 = tool.execute.after → working；兜底 = session.status 非 idle
//   → working / session.idle → idle；App 侧另有 30s 瞬态超时兜底（Rust session_state）。
// ===========================================================================
// 零阻塞契约（2026-08-22 根因修复，实测 opencode 1.18.19/1.18.21）：
//   - opencode 服务端**同步 await 插件钩子且无超时**：chat.message 在用户消息
//     保存/推送 TUI 之前（session/prompt.ts），tool.execute.before/after 包夹
//     每次工具执行（session/tools.ts）。旧实现钩子 await 串行投递队列，PulsePet
//     未运行时 readFileSync(endpoint) 抛 ENOENT → 队列内退避 sleep 1s→30s 封顶
//     → 宿主症状：发消息延迟数秒上屏、read/write/edit 全体变慢（换 opencode
//     版本无效，因为阻塞源在本插件）。
//   - 修复双管齐下：① 全部钩子 fire-and-forget（绝不 await/return 投递 promise），
//     投递/退避只在后台队列进行；② endpoint/update-token 缺失（App 未运行）→
//     postState 返回 null，deliver 静默跳过且不计退避（下游缺席≠错误）。
// ===========================================================================

import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { homedir } from "node:os";

// 注意：opencode 1.18.x 的 `@opencode-ai/plugin` 已无 `plugin()` 工厂函数；插件模块用
// v1 格式 `export default { id, server }`（server 为 async 函数返回 Hooks）。本文件
// 同时导出纯函数（classify*/Throttle/Backoff/sanitize*）供 vitest 单测——opencode 的
// v1 加载器只读取 `mod.default`，不会遍历其它导出，故可安全共存。

// 8 种归一化状态（与 Rust session_state.rs / 前端 src/lib/state.ts 一致）。
export const KINDS = Object.freeze([
  "idle",
  "working",
  "thinking",
  "editing",
  "testing",
  "waiting-permission",
  "success",
  "error",
]);

// ---- 归一化分类（纯函数，TC-EV-04） ----

const EDIT_TOOLS = new Set(["edit", "write", "patch", "apply_patch"]);
const SHELL_TOOLS = new Set(["bash", "shell", "terminal"]);
const SELF_TOOL_RE = /pulsepet_(status|say|react)/;
const TEST_CMD_RE = /(test|vitest|jest|pytest|npm\s+test|pnpm\s+test|yarn\s+test)/i;

/** 是否自忽略工具（防回环，TC-EV-19）。 */
export function isSelfTool(tool) {
  return SELF_TOOL_RE.test(String(tool ?? ""));
}

/**
 * 分类 `event` bus 事件（opencode SDK 的 Event union）。
 * 返回归一化 kind，无法分类返回 null（忽略）。
 */
export function classifyEvent(event) {
  switch (event?.type) {
    case "session.status":
      // SessionStatus.type ∈ {idle, busy, retry}；idle 是复位主信号
      return event?.properties?.status?.type === "idle" ? "idle" : "working";
    case "session.idle":
      return "idle";
    case "session.error":
      return "error";
    case "permission.asked":
      // A6（M2 P3-⑤ 清偿，DESIGN §3.1 归一化表）：总线 permission.asked →
      // waiting-permission。此前仅 permission.ask hook 处理该信号（前端兜底
      // 双处理）；补总线分支后两条通道一致——同一次询问若 hook 与总线都发，
      // permission 桶 3s 冷却天然去重，无双发。
      return "waiting-permission";
    default:
      return null;
  }
}

/**
 * 分类 `tool.execute.before`（tool 名 + 可选 args/command）。
 * 返回归一化 kind；自忽略工具返回 null（跳过，TC-EV-19）。
 */
export function classifyToolBefore(tool, args, command) {
  if (!tool) return null;
  if (isSelfTool(tool)) return null;
  if (EDIT_TOOLS.has(tool)) return "editing";
  if (SHELL_TOOLS.has(tool)) {
    const cmd = args?.command ?? args?.cmd ?? command ?? "";
    return TEST_CMD_RE.test(cmd) ? "testing" : "working";
  }
  return "working";
}

// ---- 节流（TC-EV-18，三类互不干扰 + 同桶升级放行） ----

const SPEECH_KINDS = new Set(["thinking", "success", "error"]);
const PERMISSION_KINDS = new Set(["waiting-permission"]);
const REACTION_KINDS = new Set(["working", "editing", "testing", "idle"]);
const COOLDOWNS = { speech: 20000, permission: 3000, reaction: 10000 };

// 视觉优先级（与 Rust session_state.rs / DESIGN §3.3 一致，M5 同桶升级放行用）：
// error 7 > waiting-permission 6 > testing 5 > editing 4 > thinking 3 > success 2 > working 1 > idle 0
export const VISUAL_PRIORITY = Object.freeze({
  error: 7,
  "waiting-permission": 6,
  testing: 5,
  editing: 4,
  thinking: 3,
  success: 2,
  working: 1,
  idle: 0,
});

export function bucketFor(kind) {
  if (SPEECH_KINDS.has(kind)) return "speech";
  if (PERMISSION_KINDS.has(kind)) return "permission";
  if (REACTION_KINDS.has(kind)) return "reaction";
  return null;
}

export class Throttle {
  constructor(now = () => Date.now()) {
    this.now = now;
    this.last = { speech: -Infinity, permission: -Infinity, reaction: -Infinity };
    // 各桶最近一次**实际放行**的 kind（同桶升级放行的比较基准）
    this.delivered = { speech: null, permission: null, reaction: null };
  }

  /**
   * 返回 true 表示放行（并记录本次发送时刻）。
   *
   * 同桶升级放行（DESIGN §3.1，M2 移交 M5 前定案）：冷却期内，若新事件的
   * 视觉优先级**高于**该桶已投递事件（如 editing(4) > 已投递 working(1)，
   * 背景：session.status busy 先占 reaction 桶会把紧随的 tool.execute.before
   * editing/testing 吞掉——占位降级渲染无视觉影响，M5 切 atlas 后有独立动画
   * 需放行）→ 绕过冷却直接放行，且冷却窗从该次放行时刻重新起算；
   * 优先级不高于（≤）已投递事件时维持节流。瞬态被 tool.execute.after 复位
   * 吞没的情况由 App 侧 30s 超时兜底。
   */
  shouldSend(kind) {
    const bucket = bucketFor(kind);
    if (!bucket) return true; // 无冷却分类的 kind 直接放行
    const t = this.now();
    if (t - this.last[bucket] >= COOLDOWNS[bucket]) {
      this.last[bucket] = t;
      this.delivered[bucket] = kind;
      return true;
    }
    const prio = VISUAL_PRIORITY[kind] ?? -1;
    const lastKind = this.delivered[bucket];
    const lastPrio = lastKind == null ? -1 : (VISUAL_PRIORITY[lastKind] ?? -1);
    if (prio > lastPrio) {
      this.last[bucket] = t; // 升级放行：冷却窗重新起算
      this.delivered[bucket] = kind;
      return true;
    }
    return false;
  }
}

// ---- 指数退避（TC-EV-07，静默 + 1s→2s→5s→30s 封顶） ----

const BACKOFF_DELAYS = [0, 1000, 2000, 5000, 30000];

export class Backoff {
  constructor(sleepFn = (ms) => new Promise((r) => setTimeout(r, ms))) {
    this.sleep = sleepFn;
    this.index = 0;
  }

  /** 下一次失败应等待的毫秒数（首次 0=立即重试，之后 1s→2s→5s→30s 封顶）。 */
  nextDelay() {
    const d = BACKOFF_DELAYS[Math.min(this.index, BACKOFF_DELAYS.length - 1)];
    this.index += 1;
    return d;
  }

  /** 等待并返回本次等待时长。 */
  async wait() {
    const d = this.nextDelay();
    if (d > 0) await this.sleep(d);
    return d;
  }

  /** 恢复后复位，下次失败立即重试。 */
  reset() {
    this.index = 0;
  }
}

// ---- 消息净化（TC-EV-20/21：白名单语音池，不落原始内容） ----

// 五类白名单模板（thinking/success/error/permission/waiting；waiting 为 PulsePet 扩展）。
export const BUBBLE_POOL = Object.freeze({
  thinking: ["让我想想…", "正在思考…", "Hmm…"],
  success: ["搞定！", "完成啦！", "干得漂亮 🎉"],
  error: ["出错了…", "遇到点问题", "需要你来看看"],
  permission: ["需要你的确认", "等你审批", "看看这个请求"],
  waiting: ["稍等一下…", "在排队…", "等会儿回来"],
});

/** kind → 气泡模板分类（working/editing/testing/idle 属反应类，不出气泡）。 */
export function bubbleCategoryFor(kind) {
  switch (kind) {
    case "thinking":
      return "thinking";
    case "success":
      return "success";
    case "error":
      return "error";
    case "waiting-permission":
      return "permission";
    default:
      return null;
  }
}

/** 单行 + 1-140 字符约束（超长截断；非法输入返回空串丢弃）。 */
export function sanitizeText(text) {
  const s = String(text ?? "")
    .replace(/[\r\n]+/g, " ") // 单行化
    .trim();
  if (!s) return "";
  return s.length > 140 ? s.slice(0, 140) : s;
}

/** 从白名单池取一条（可传索引避免随机；仅用池内模板，绝不回显原始内容）。 */
export function pickBubble(kind, index = 0) {
  const cat = bubbleCategoryFor(kind);
  if (!cat) return "";
  const pool = BUBBLE_POOL[cat];
  return sanitizeText(pool[index % pool.length]);
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

/**
 * POST /state。每次发请求前读最新 endpoint/token 文件（端口回退后无需重装插件，
 * TC-EV-09）。返回 response；任何网络/HTTP≥400 错误抛出（由调用方静默退避）。
 *
 * **App 未运行快速通道（2026-08-22 根因修复）**：endpoint/update-token 文件
 * 缺失（ENOENT）或为空 → 返回 null，不发起请求——「下游缺席」不是错误，调用方
 * 静默跳过且不计退避（对齐 Langfuse/LangSmith 等遥测插件「下游缺席→丢弃，
 * 遥测永不伤害宿主」的主流语义）。
 *
 * P3-③（M2 遗留）：不再发送 `connection: close` 头——`Connection` 是 fetch 规范的
 * forbidden header name，实现会静默忽略，发了也是冗余；一次性连接语义由服务端
 * tiny_http「一请求一连接」保证（TC-EV-14），客户端配合 AbortSignal 3s 兜底。
 */
function readRuntimeFile(dir, name) {
  try {
    return readFileSync(join(dir, name), "utf8").trim();
  } catch (err) {
    if (err && err.code === "ENOENT") return null;
    throw err;
  }
}

export async function postState(
  kind,
  sessionId,
  agent = "opencode",
  fetchImpl = fetch,
  dir = runtimeDir(),
) {
  const endpoint = readRuntimeFile(dir, "endpoint");
  const token = readRuntimeFile(dir, "update-token");
  if (!endpoint || !token) return null; // App 未运行：快速跳过（非错误）
  const res = await fetchImpl(`http://${endpoint}/state`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-pulsepet-token": token,
    },
    body: JSON.stringify({ sessionId, kind, agent }),
    signal: AbortSignal.timeout(3000),
  });
  if (res.status === 401 || res.status >= 400) {
    throw new Error(`http ${res.status}`);
  }
  return res;
}

// ---- 投递器（P3-②：并发投递串行化，Backoff 不跳级/不误复位） ----

/**
 * 创建 deliver：killswitch / 节流检查后，把实际 POST 放入串行队列。
 *
 * 背景（M2 遗留 P3-②）：opencode 的 hooks 可能并发触发，若多个 deliver 同时失败，
 * 每个都推进一次 backoff index——一次「失败脉冲」连跳多级退避（并发 3 个失败一步
 * 到 2s），且并发里的成功 reset 会把别的失败正在等待的序列打断复位。串行化后：
 *   - 同一时刻至多一个 POST 在飞（与单连接服务端的语义一致）；
 *   - 每次失败只消耗一级退避（0→1s→2s→5s→30s 严格递进，不跳级）；
 *   - reset 只发生在队列排空的成功之后（无误复位）。
 */
export function createDeliverer({
  throttle = new Throttle(),
  backoff = new Backoff(),
  postStateImpl = postState,
  killswitch = killswitchActive,
  agent = "opencode",
} = {}) {
  let queue = Promise.resolve();
  const enqueue = (fn) => {
    // 上一步无论成败都继续（deliver 内部已吞错，这里兜底防断链）
    const run = queue.then(fn, fn);
    queue = run.then(
      () => {},
      () => {},
    );
    return run;
  };
  async function deliver(kind, sessionId) {
    if (!kind) return;
    if (killswitch()) return; // TC-EV-10：killswitch 整体跳过
    if (!throttle.shouldSend(kind)) return; // TC-EV-18：节流
    await enqueue(async () => {
      try {
        const res = await postStateImpl(kind, sessionId ?? "default", agent);
        if (res == null) return; // App 未运行：静默跳过（不 reset、不退避）
        backoff.reset(); // 恢复后下次立即投递
      } catch {
        // TC-EV-07：静默跳过（不打日志不报错）+ 指数退避
        await backoff.wait();
      }
    });
  }
  return { deliver };
}

// ---- opencode 插件注册（v1 格式：export default { id, server }）----

/**
 * 构建注册给 opencode 的 Hooks（deliverer 可注入，供单测替换）。
 *
 * **零阻塞契约（2026-08-22 根因修复，实测 opencode 1.18.x）**：opencode 服务端
 * 会同步 await 每个插件钩子且无任何超时保护——`chat.message` 在用户消息保存/
 * 推送 TUI **之前**触发（session/prompt.ts），`tool.execute.before/after` **包夹**
 * 每次工具执行（session/tools.ts）。钩子一旦 await 投递队列（含退避 sleep
 * 1s→30s），宿主会整体卡住：发消息延迟数秒才上屏、read/write/edit 全体变慢。
 * 因此所有钩子 fire-and-forget：绝不 await、也绝不 return 投递 promise（宿主会
 * await 钩子返回值）——对齐 Langfuse/LangSmith 等遥测类插件「热路径零网络 I/O」
 * 的主流设计。
 */
export function buildHooks(deliverer = createDeliverer()) {
  const fire = (kind, sessionId) => {
    try {
      void deliverer.deliver(kind, sessionId).catch(() => {});
    } catch {
      // deliver 为 async 函数不会同步抛错；防御性吞掉，钩子永不向宿主抛错
    }
  };

  return {
    event: ({ event }) => {
      fire(classifyEvent(event), event?.properties?.sessionID);
    },
    "chat.message": (input) => {
      fire("thinking", input?.sessionID);
    },
    "permission.ask": (input) => {
      fire("waiting-permission", input?.sessionID);
    },
    "tool.execute.before": (input, output) => {
      fire(classifyToolBefore(input?.tool, output?.args), input?.sessionID);
    },
    "tool.execute.after": (input) => {
      // TC-EV-05：主复位信号（把 editing/testing 拉回 working）
      if (isSelfTool(input?.tool)) return; // 自忽略
      fire("working", input?.sessionID);
    },
    "command.execute.before": (input) => {
      const cmd = input?.command ?? "";
      if (TEST_CMD_RE.test(cmd)) fire("testing", input?.sessionID);
    },
  };
}

export default {
  id: "pulse-pet",
  server: async () => buildHooks(),
};
