/**
 * reminder-bridge：M4 提醒/任务事件桥（pet 窗口侧），DESIGN §5.1/§5.2/§5.3 +
 * v2 M4 §4.5/§4.9（TC-M4-11/13）。
 *
 * Rust 调度器到点广播 `reminder://trigger`（payload 见 parseReminderTrigger）：
 * - 气泡路径（无条件）：planReminderActions 产出的净化文案 → petStore.
 *   pushBubble（v2 M2 排队模型：critical 级 source="reminder:<logId>"，分级
 *   dwell 8s 到期回报 'auto'；点击宠物确认回报 'bubble'；snooze 按钮回报
 *   'snooze'——由本模块注册的 reporter invoke 回 Rust）；
 * - 烟花（use_fireworks 或全局开关开，TC-RM-11 的 OR 语义）**额外** invoke
 *   `reminder_play_fireworks`，由 Rust 定位发射点并编排 fireworks 窗口。
 *   v0.1.3 四-5 定案：特效只叠加、不替代气泡。
 *
 * v2 M4（P1-3）：`pulsepet://task-result`——exec 结果气泡独立事件（不复用被
 * M2 冻结为 info 级 token-report 映射的 `pulsepet://bubble`），按 M2 critical
 * 入队 source="task:<logId>"；**无 reminder 载荷**（点宠物即消、不写
 * reminder_logs、无 snooze 按钮——按钮条件 = critical 且 reminder 载荷）。
 *
 * 仅 pet 路由注册（fireworks 窗口自己的 play/ready 在 Fireworks.tsx 内接线，
 * panel 不消费触发事件）；非 Tauri 环境（vitest/浏览器 dev）静默返回。
 * 纯函数解析在 lib/reminders.ts（parseReminderTrigger / planReminderActions 已单测）。
 */

import { setReminderReporter, usePetStore } from "../pet/petStore";
import { parseReminderTrigger, planReminderActions } from "./reminders";

/** Rust exec 执行链的结果气泡事件名（§4.5，P1-3 独立事件）。 */
export const TASK_RESULT_EVENT = "pulsepet://task-result";

/** `pulsepet://task-result` payload（Rust run_task emit_to）。 */
export interface TaskResultPayload {
  text: string;
  logId: number;
  status: string;
}

/** 解析 task-result payload；字段缺失/类型不对 → null（静默忽略）。 */
export function parseTaskResult(payload: unknown): TaskResultPayload | null {
  if (typeof payload !== "object" || payload === null) return null;
  const p = payload as Record<string, unknown>;
  if (typeof p.text !== "string" || !p.text) return null;
  if (typeof p.logId !== "number" || !Number.isFinite(p.logId)) return null;
  if (typeof p.status !== "string") return null;
  return { text: p.text, logId: p.logId, status: p.status };
}

export function initReminderBridge(): void {
  if (typeof window === "undefined") return;
  if (!(window as unknown as { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__) {
    return;
  }
  // 路由门控：仅 pet 窗口消费触发事件（#/pet）
  const hash = window.location.hash ?? "";
  if (!(hash.includes("pet") || hash === "" || hash === "#" || hash === "#/")) {
    return;
  }

  void (async () => {
    const { listen } = await import("@tauri-apps/api/event");
    const { invoke } = await import("@tauri-apps/api/core");

    // 气泡消失方式回报（petStore 侧无 Tauri 依赖，经此注入）。
    // v2 M4：+ 'snooze'（气泡按钮 → reminders_snooze：log 结案 + 重发编排）
    setReminderReporter((logId: number, via: "bubble" | "auto" | "snooze") => {
      void (async () => {
        try {
          if (via === "bubble") {
            await invoke("reminders_ack", { logId });
          } else if (via === "snooze") {
            await invoke("reminders_snooze", { logId });
          } else {
            await invoke("reminders_dismiss", { logId, via: "auto" });
          }
        } catch (e) {
          console.error(`[pulsepet] reminder report (${via}) failed:`, e);
        }
      })();
    });

    await listen("reminder://trigger", (event) => {
      const t = parseReminderTrigger(event.payload);
      if (!t) return;
      // v0.1.3 四-5（TC-RM-17/09）：气泡无条件展示，烟花按 plan 额外叠加——
      // 特效只叠加、不替代气泡（烟花触发时用户同样能看到提醒文案）。
      // v2 M2：critical 级 + source="reminder:<logId>"（排队模型 §2.6.2）。
      const plan = planReminderActions(t, Date.now());
      usePetStore.getState().pushBubble({
        text: plan.bubbleText,
        level: "critical",
        source: `reminder:${t.log_id}`,
        reminder: { logId: t.log_id },
      });
      if (plan.fireworks) {
        void (async () => {
          try {
            await invoke("reminder_play_fireworks", { logId: t.log_id });
          } catch (e) {
            console.error("[pulsepet] play fireworks failed:", e);
          }
        })();
      }
    });

    // v2 M4（P1-3/TC-M4-11）：exec 结果气泡——独立事件按 M2 critical 入队；
    // 无 reminder 载荷（点宠物即消、无 snooze 按钮、不写 reminder_logs）。
    await listen(TASK_RESULT_EVENT, (event) => {
      const r = parseTaskResult(event.payload);
      if (!r) return;
      usePetStore.getState().pushBubble({
        text: r.text,
        level: "critical",
        source: `task:${r.logId}`,
      });
    });
    console.log("[pulsepet] reminder bridge ready (pet)");
  })();
}
