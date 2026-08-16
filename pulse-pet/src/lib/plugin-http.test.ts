import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { killswitchActive, postState } from "../../opencode-plugin/pulse-pet-hook.js";

/** 插件 HTTP 客户端回环（TC-EV-09/11/07 的插件侧行为）。 */
describe("postState：读 endpoint/token 文件并 POST（TC-EV-09）", () => {
  let dir: string;

  beforeAll(() => {
    dir = mkdtempSync(join(tmpdir(), "pulsepet-e2e-"));
  });

  afterAll(() => {
    rmSync(dir, { recursive: true, force: true });
  });

  function writeRuntime(endpoint: string, token = "tok-123") {
    writeFileSync(join(dir, "endpoint"), endpoint);
    writeFileSync(join(dir, "update-token"), token);
  }

  it("按最新 endpoint/token 文件 POST /state，带 x-pulsepet-token 头", async () => {
    writeRuntime("127.0.0.1:47999", "tok-123");
    const fetchImpl = vi.fn<
      (input: string, init?: Record<string, unknown>) => Promise<{ status: number }>
    >(async () => ({ status: 200 }));
    await postState("editing", "sess-1", "opencode", fetchImpl, dir);

    expect(fetchImpl).toHaveBeenCalledTimes(1);
    const [url, opts] = fetchImpl.mock.calls[0];
    expect(url).toBe("http://127.0.0.1:47999/state");
    const init = opts as Record<string, any>;
    expect(init.method).toBe("POST");
    expect(init.headers["x-pulsepet-token"]).toBe("tok-123");
    expect(init.headers.connection).toBe("close");
    expect(JSON.parse(init.body as string)).toEqual({
      sessionId: "sess-1",
      kind: "editing",
      agent: "opencode",
    });
  });

  it("端口回退后每次读最新 endpoint（无需重装插件，TC-EV-09）", async () => {
    const fetchImpl = vi.fn<
      (input: string, init?: Record<string, unknown>) => Promise<{ status: number }>
    >(async () => ({ status: 200 }));
    writeRuntime("127.0.0.1:47000");
    await postState("idle", "s1", "opencode", fetchImpl, dir);
    writeRuntime("127.0.0.1:47001"); // 模拟换端口
    await postState("working", "s1", "opencode", fetchImpl, dir);

    expect(fetchImpl.mock.calls[0][0]).toBe("http://127.0.0.1:47000/state");
    expect(fetchImpl.mock.calls[1][0]).toBe("http://127.0.0.1:47001/state");
  });

  it("401 视为失败抛出（调用方静默退避，TC-EV-07）", async () => {
    writeRuntime("127.0.0.1:47998");
    const fetchImpl = vi.fn<
      (input: string, init?: Record<string, unknown>) => Promise<{ status: number }>
    >(async () => ({ status: 401 }));
    await expect(
      postState("idle", "s1", "opencode", fetchImpl, dir),
    ).rejects.toThrow("http 401");
  });
});

describe("killswitchActive（TC-EV-10）", () => {
  it("hooks-disabled 存在即返回 true，删除后 false", () => {
    const dir = mkdtempSync(join(tmpdir(), "pulsepet-ks-"));
    try {
      expect(killswitchActive(dir)).toBe(false);
      mkdirSync(dir, { recursive: true });
      writeFileSync(join(dir, "hooks-disabled"), "");
      expect(killswitchActive(dir)).toBe(true);
      rmSync(join(dir, "hooks-disabled"));
      expect(killswitchActive(dir)).toBe(false);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });
});
