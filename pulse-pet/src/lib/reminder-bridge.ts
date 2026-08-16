/**
 * reminder-bridge：M4 提醒事件桥（pet 窗口侧），DESIGN §5.1/§5.2/§5.3。
 *
 * Rust 调度器到点广播 `reminder://trigger`（payload 见 parseReminderTrigger）：
 * - 气泡路径（默认）：净化文案 → petStore.showReminderBubble（8s 自动消失回报
 *   'auto'；点击宠物确认回报 'bubble'，由本模块注册的 reporter invoke 回 Rust）；
 * - 烟花路径（use_fireworks 或全局开关开，TC-RM-11 的 OR 语义）：invoke
 *   `reminder_play_fireworks`，由 Rust 定位发射点并编排 fireworks 窗口
 *   （TC-RM-09/10；dismissed_via='fireworks' 由 Rust 在播完 hide 时写）。
 *
 * 仅 pet 路由注册（fireworks 窗口自己的 play/ready 在 Fireworks.tsx 内接线，
 * panel 不消费触发事件）；非 Tauri 环境（vitest/浏览器 dev）静默返回。
 * 纯函数解析在 lib/reminders.ts（parseReminderTrigger 已单测）。
 */

import { setReminderReporter, usePetStore } from "../pet/petStore";
import { parseReminderTrigger, sanitizeReminderText, usesFireworks } from "./reminders";

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

    // 气泡消失方式回报（petStore 侧无 Tauri 依赖，经此注入）
    setReminderReporter((logId: number, via: "bubble" | "auto") => {
      void (async () => {
        try {
          if (via === "bubble") {
            await invoke("reminders_ack", { logId });
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
      if (usesFireworks(t)) {
        void (async () => {
          try {
            await invoke("reminder_play_fireworks", { logId: t.log_id });
          } catch (e) {
            console.error("[pulsepet] play fireworks failed:", e);
          }
        })();
      } else {
        // 气泡路径：文案净化（TC-RM-15）后展示；store 内部再走基础净化兜底
        usePetStore.getState().showReminderBubble(sanitizeReminderText(t.label), t.log_id);
      }
    });
    console.log("[pulsepet] reminder bridge ready (pet)");
  })();
}
