import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";
import {
  cpSync,
  mkdirSync,
  mkdtempSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { readFileSync } from "node:fs";

import {
  EDIT_TOOLS,
  MAX_STDIN_BYTES,
  TEST_CMD_RE,
  classifyHookInput,
  classifyToolUse,
  isPayloadTooLarge,
  processHookInput,
  sanitizeMessage,
} from "../../opencode-plugin/claude-code-hook.js";

/** 构造 CC hook input（stdin JSON）。 */
function ccInput(event: string, extra: Record<string, unknown> = {}) {
  return { hook_event_name: event, session_id: "cc-uuid-1", ...extra };
}

describe("TC-INT-01：CC hook 事件归一化映射", () => {
  it("八事件 → kind 映射逐条符合 V2-DESIGN §1.3.1", () => {
    expect(classifyHookInput(ccInput("SessionStart"))).toBe("idle");
    expect(classifyHookInput(ccInput("UserPromptSubmit"))).toBe("thinking");
    expect(classifyHookInput(ccInput("PostToolUse", { tool_name: "Bash" }))).toBe("working");
    expect(classifyHookInput(ccInput("PostToolUseFailure", { tool_name: "Bash" }))).toBe("error");
    expect(classifyHookInput(ccInput("PermissionRequest", { tool_name: "Bash" }))).toBe(
      "waiting-permission",
    );
    expect(classifyHookInput(ccInput("Stop"))).toBe("idle");
    expect(classifyHookInput(ccInput("StopFailure", { error: "x" }))).toBe("error");
  });

  it("PreToolUse 工具分类：Edit/Write/MultiEdit/NotebookEdit → editing", () => {
    for (const tool of ["Edit", "Write", "MultiEdit", "NotebookEdit"]) {
      expect(classifyToolUse(tool, {})).toBe("editing");
      expect(classifyHookInput(ccInput("PreToolUse", { tool_name: tool }))).toBe("editing");
    }
  });

  it("PreToolUse Bash：命中测试正则 → testing（含 cargo/go test 天然覆盖）", () => {
    expect(classifyToolUse("Bash", { command: "cargo test" })).toBe("testing");
    expect(classifyToolUse("Bash", { command: "go test ./..." })).toBe("testing");
    expect(classifyToolUse("Bash", { command: "npm test" })).toBe("testing");
    expect(classifyToolUse("Bash", { command: "pnpm run vitest --run" })).toBe("testing");
    expect(classifyToolUse("Bash", { command: "pytest -x" })).toBe("testing");
    expect(classifyHookInput(ccInput("PreToolUse", {
      tool_name: "Bash",
      tool_input: { command: "npm test" },
    }))).toBe("testing");
  });

  it("PreToolUse Bash 普通命令 / Read / Grep / 其余工具 → working", () => {
    expect(classifyToolUse("Bash", { command: "ls -la" })).toBe("working");
    expect(classifyToolUse("Bash", { command: "echo hello" })).toBe("working");
    expect(classifyToolUse("Read", {})).toBe("working");
    expect(classifyToolUse("Grep", { pattern: "x" })).toBe("working");
    expect(classifyHookInput(ccInput("PreToolUse", {
      tool_name: "WebFetch",
      tool_input: { url: "https://x" },
    }))).toBe("working");
  });

  it("TEST_CMD_RE 与 opencode 插件 pulse-pet-hook.js 逐字一致（TC-INT-01-1）", () => {
    expect(String(TEST_CMD_RE)).toBe(
      "/(test|vitest|jest|pytest|npm\\s+test|pnpm\\s+test|yarn\\s+test)/i",
    );
    // 源码级钉子：两文件里的正则字面量必须逐字符相同（含标志位）——
    // pulse-pet-hook.js 的 TEST_CMD_RE 是模块私有 const，故以源码文本比对
    const ccSrc = readFileSync(
      new URL("../../opencode-plugin/claude-code-hook.js", import.meta.url),
      "utf8",
    );
    const ocSrc = readFileSync(
      new URL("../../opencode-plugin/pulse-pet-hook.js", import.meta.url),
      "utf8",
    );
    const pick = (src: string) => src.match(/TEST_CMD_RE = (\/.*\/[a-z]*);/)?.[1];
    expect(pick(ccSrc)).toBeDefined();
    expect(pick(ocSrc)).toBeDefined();
    expect(pick(ccSrc)).toBe(pick(ocSrc));
  });

  it("不注册的事件一律 null（Notification/Subagent*/SessionEnd/Compact 等 + 未知 + 缺名）", () => {
    for (const ev of [
      "Notification",
      "SubagentStart",
      "SubagentStop",
      "SessionEnd",
      "PreCompact",
      "PostCompact",
      "PostToolBatch",
      "TaskCreated",
      "TaskCompleted",
      "WhateverEvent",
    ]) {
      expect(classifyHookInput(ccInput(ev))).toBeNull();
    }
    expect(classifyHookInput({ session_id: "x" })).toBeNull(); // 缺 hook_event_name
    expect(classifyHookInput(null)).toBeNull();
    expect(classifyHookInput("not-an-object")).toBeNull();
  });

  it("EDIT_TOOLS 恰为四种编辑工具", () => {
    expect([...EDIT_TOOLS].sort()).toEqual(["Edit", "MultiEdit", "NotebookEdit", "Write"]);
  });
});

describe("TC-INT-02：CC hook 行为契约（零阻塞）", () => {
  let dir: string;

  beforeAll(() => {
    dir = mkdtempSync(join(tmpdir(), "pulsepet-cchook-"));
  });

  afterAll(() => {
    rmSync(dir, { recursive: true, force: true });
  });

  function writeRuntime(endpoint = "127.0.0.1:47811", token = "tok-cc") {
    mkdirSync(dir, { recursive: true });
    writeFileSync(join(dir, "endpoint"), endpoint);
    writeFileSync(join(dir, "update-token"), token);
  }

  const okFetch = () =>
    vi.fn(async () => ({ status: 200 })) as unknown as typeof fetch;

  it("stdin payload >64KB → 拒收（不 POST）", async () => {
    const fetchImpl = okFetch();
    const big = JSON.stringify(ccInput("UserPromptSubmit")).padEnd(MAX_STDIN_BYTES + 1, "x");
    expect(isPayloadTooLarge(Buffer.byteLength(big))).toBe(true);
    const out = await processHookInput({ input: big, fetchImpl, dir });
    expect(out).toBe("dropped:oversize");
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("恰 64KB 不视为超限", () => {
    expect(isPayloadTooLarge(MAX_STDIN_BYTES)).toBe(false);
    expect(isPayloadTooLarge(MAX_STDIN_BYTES + 1)).toBe(true);
  });

  it("缺 session_id → 全事件丢弃（不落 default，较 opencode 侧更严）", async () => {
    const fetchImpl = okFetch();
    const input = JSON.stringify({ hook_event_name: "UserPromptSubmit" });
    const out = await processHookInput({ input, fetchImpl, dir });
    expect(out).toBe("dropped:session");
    expect(fetchImpl).not.toHaveBeenCalled();
    // session_id 非字符串同样丢弃
    const out2 = await processHookInput({
      input: JSON.stringify({ hook_event_name: "Stop", session_id: 42 }),
      fetchImpl,
      dir,
    });
    expect(out2).toBe("dropped:session");
  });

  it("killswitch 文件存在 → 整体跳过不 POST", async () => {
    mkdirSync(dir, { recursive: true });
    writeFileSync(join(dir, "hooks-disabled"), "");
    try {
      const fetchImpl = okFetch();
      const out = await processHookInput({
        input: JSON.stringify(ccInput("Stop")),
        fetchImpl,
        dir,
      });
      expect(out).toBe("skipped:killswitch");
      expect(fetchImpl).not.toHaveBeenCalled();
    } finally {
      rmSync(join(dir, "hooks-disabled"));
    }
  });

  it("endpoint / token 文件 ENOENT → 快速通道（不 POST、无重试无退避）", async () => {
    const empty = mkdtempSync(join(tmpdir(), "pulsepet-cchook-empty-"));
    try {
      const fetchImpl = okFetch();
      const out = await processHookInput({
        input: JSON.stringify(ccInput("Stop")),
        fetchImpl,
        dir: empty,
      });
      expect(out).toBe("skipped:no-endpoint");
      expect(fetchImpl).not.toHaveBeenCalled();
    } finally {
      rmSync(empty, { recursive: true, force: true });
    }
  });

  it("POST body 恰为 {sessionId, kind, agent:'claude-code'}，超时 1s", async () => {
    writeRuntime("127.0.0.1:47899", "tok-cc-9");
    const calls: Array<[string, Record<string, any>]> = [];
    const fetchImpl = (async (url: string, init?: Record<string, any>) => {
      calls.push([url, init ?? {}]);
      return { status: 200 };
    }) as unknown as typeof fetch;
    const out = await processHookInput({
      input: JSON.stringify(ccInput("UserPromptSubmit", { session_id: "uuid-abc" })),
      fetchImpl,
      dir,
    });
    expect(out).toBe("posted");
    expect(calls.length).toBe(1);
    const [url, init] = calls[0];
    expect(url).toBe("http://127.0.0.1:47899/state");
    expect(init.method).toBe("POST");
    expect(init.headers["x-pulsepet-token"]).toBe("tok-cc-9");
    expect(init.headers["content-type"]).toBe("application/json");
    expect(JSON.parse(init.body)).toEqual({
      sessionId: "uuid-abc",
      kind: "thinking",
      agent: "claude-code",
    });
    // POST 超时信号已挂（AbortSignal.timeout(1000)，未立即中止）
    expect((init.signal as AbortSignal).aborted).toBe(false);
  });

  it("POST 超时信号为 1s（TC-INT-02-5）", async () => {
    writeRuntime("127.0.0.1:47898");
    let captured: AbortSignal | undefined;
    const fetchImpl = ((_url: string, init?: Record<string, unknown>) => {
      captured = init?.signal as AbortSignal;
      return Promise.resolve({ status: 200 });
    }) as unknown as typeof fetch;
    await processHookInput({ input: JSON.stringify(ccInput("Stop")), fetchImpl, dir });
    // AbortSignal.timeout 的 abort 时间不可直接读取；用真实定时器验证 ~1s 后中止
    expect(captured).toBeDefined();
    await new Promise((r) => setTimeout(r, 1200));
    expect(captured!.aborted).toBe(true);
  }, 5000);

  it("HTTP ≥400 / 网络错误 → 静默失败（不抛错、无重试）", async () => {
    writeRuntime("127.0.0.1:47897");
    const bad = vi.fn(async () => ({ status: 500 })) as unknown as typeof fetch;
    const out = await processHookInput({ input: JSON.stringify(ccInput("Stop")), fetchImpl: bad, dir });
    expect(out).toBe("post-failed");
    expect(bad).toHaveBeenCalledTimes(1); // 无重试
    const throwing = vi.fn(async () => {
      throw new Error("ECONNREFUSED");
    }) as unknown as typeof fetch;
    const out2 = await processHookInput({
      input: JSON.stringify(ccInput("Stop")),
      fetchImpl: throwing,
      dir,
    });
    expect(out2).toBe("post-failed");
  });

  it("非法 JSON / 非对象 JSON / 无法分类 → 静默丢弃，全部路径 resolve（恒 exit 0 语义）", async () => {
    const fetchImpl = okFetch();
    for (const input of ["not json", "[]", "42", "null", "", '{"hook_event_name":"Notification","session_id":"x"}']) {
      const out = await processHookInput({ input, fetchImpl, dir });
      expect(String(out).startsWith("dropped:")).toBe(true);
    }
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("不做客户端节流：同 kind 连续事件每次都 POST（M1 裁定）", async () => {
    writeRuntime("127.0.0.1:47896");
    const fetchImpl = vi.fn(async () => ({ status: 200 })) as unknown as typeof fetch;
    for (let i = 0; i < 5; i += 1) {
      const out = await processHookInput({
        input: JSON.stringify(ccInput("PostToolUse")),
        fetchImpl,
        dir,
      });
      expect(out).toBe("posted");
    }
    expect(fetchImpl).toHaveBeenCalledTimes(5);
  });

  it("sanitizeMessage 净化路径（PULSEPET_HOOK_DEBUG=1 时的错误文案）", () => {
    const home = "/Users/someone";
    const msg = `ENOENT: no such file ${home}/.pulsepet/runtime/endpoint`;
    expect(sanitizeMessage(msg, home)).not.toContain(home);
    expect(sanitizeMessage(msg, home)).toContain("~/.pulsepet/runtime/endpoint");
  });

  it("CLI 入口判定用 realpath（/tmp symlink 目录下主流程不被静默跳过）", async () => {
    // 2026-08-24 修复回归钉子：macOS /tmp 是 /private/tmp 的 symlink，字面
    // pathToFileURL(argv[1]) 与 node realpath 后的 import.meta.url 不等 →
    // isMain false → 主流程空跑（exit 0 假阳性）。经子进程真实执行验证。
    const { spawnSync } = await import("node:child_process");
    const tmp = mkdtempSync(join(tmpdir(), "pulsepet-ismain-"));
    try {
      // 人为构造一层 symlink 指向真实目录，模拟 /tmp → /private/tmp 场景
      mkdirSync(join(tmp, "real"), { recursive: true });
      const link = join(tmp, "link");
      const { symlinkSync } = await import("node:fs");
      symlinkSync(join(tmp, "real"), link);
      cpSync(new URL("../../opencode-plugin/claude-code-hook.js", import.meta.url).pathname, join(link, "claude-code-hook.js"));
      writeFileSync(join(link, "package.json"), '{"type":"module"}');
      const res = spawnSync(
        process.execPath,
        [join(link, "claude-code-hook.js")],
        {
          input: '{"hook_event_name":"Stop","session_id":"smoke"}',
          env: { ...process.env, PULSEPET_HOOK_DEBUG: "1", HOME: join(tmp, "nohome") },
        },
      );
      expect(res.status).toBe(0);
      // 主流程真的执行过（经 symlink 路径调用仍进入 isMain 分支；
      // debugLog 走 stderr）
      expect(res.stderr.toString()).toContain("outcome:");
    } finally {
      rmSync(tmp, { recursive: true, force: true });
    }
  });
});
