import { describe, expect, it } from "vitest";
import { AGENTS, badgeOf, descKeyOf, hasCostOf, shortOf } from "./agents";

/**
 * v2 registry（docs/v2/agent-registry.md §6.2/§8.7.2 P2 钉）：前端 agent
 * 注册表 helpers 的钉子。badgeOf 未知 id 显原名 = 消静默错误 ②（原
 * TokenStats.tsx `agentBadgeOf` 三元 else→oc 会把新 agent 会话行错标 oc，
 * 且模块私有零直接测试）；两端表一致性由 Rust 侧 include_str! 互钉把守
 * （agents.rs tests）。
 */
describe("agents registry（agent-registry §6.2）", () => {
  it("shortOf：已知 id 查表 + task 伪 agent 特例 + 未知原名兜底", () => {
    expect(shortOf("opencode")).toBe("oc");
    expect(shortOf("claude-code")).toBe("cc");
    // task 伪 agent（action_exec）——短名即原名，技术名不翻译
    expect(shortOf("task")).toBe("task");
    // 未知 agent 原名兜底（良性形态，§2）
    expect(shortOf("codex")).toBe("codex");
    expect(shortOf("")).toBe("");
  });

  it("badgeOf：未知 id 显原名而非 oc（P2 钉 1，消静默错误 ②）", () => {
    expect(badgeOf("opencode")).toBe("oc");
    expect(badgeOf("claude-code")).toBe("cc");
    // 新 agent 不得被错标 oc（原 agentBadgeOf 三元 else→oc 无兜底）
    expect(badgeOf("codex")).toBe("codex");
    expect(badgeOf("")).toBe("");
  });

  it("hasCostOf：opencode true / claude-code false（cost「—」规则查表）", () => {
    expect(hasCostOf("opencode")).toBe(true);
    // CC 行 cost 数据层恒 0（S4）
    expect(hasCostOf("claude-code")).toBe(false);
  });

  it("descKeyOf：接入卡描述键查表，未知 id → undefined（原名兜底信号）", () => {
    expect(descKeyOf("opencode")).toBe("integrations.opencodeDesc");
    expect(descKeyOf("claude-code")).toBe("integrations.claudeDesc");
    expect(descKeyOf("codex")).toBeUndefined();
  });

  it("AGENTS：id 唯一、无 task（与 Rust 侧约束对齐）", () => {
    const ids = AGENTS.map((a) => a.id);
    // id 必须唯一（重复注册 = 查表命中歧义）
    expect(new Set(ids).size).toBe(ids.length);
    expect(ids).not.toContain("task");
    // labelKey/descKey 均有归属（i18n 完备性测试另把守键存在）
    for (const a of AGENTS) {
      expect(a.labelKey).toMatch(/^token\.agent\./);
      expect(a.descKey).toMatch(/^integrations\./);
    }
  });
});
