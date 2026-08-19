/**
 * todo-bridge：M7 Todo 完成联动事件桥（pet 窗口侧），DESIGN §8.3，TC-TD-04/05。
 *
 * Rust `todo_complete` 完成任务后广播 `todo://completed`（payload 见
 * parseTodoCompleted）：
 * - 任何完成 → 宠物播放 waving 动画（petStore.startCelebration，约 3s 后
 *   自动回退原状态）+ 气泡"干得漂亮 🎉"；
 * - 今日全清（最后一个今日任务完成）→ 气泡改为"今日完成 N 项"（N 按本地
 *   自然日 completed_at 统计，Rust 侧算好）；jumping 二级庆祝 v1 不做。
 *
 * 走 Tauri event（§8.3：不引入新通道）；仅 pet 路由注册；非 Tauri 环境
 * （vitest/浏览器 dev）静默返回。气泡顶替旧提醒气泡时由 petStore 按
 * 'auto' 回报旧 log（M4 P2 ④ 完成联动打断路径已覆盖）。
 */

import { usePetStore } from "../pet/petStore";
import { celebrationText, parseTodoCompleted } from "./todos";

export function initTodoBridge(): void {
  if (typeof window === "undefined") return;
  if (!(window as unknown as { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__) {
    return;
  }
  // 路由门控：仅 pet 窗口消费（与 reminder-bridge 同口径）
  const hash = window.location.hash ?? "";
  if (!(hash.includes("pet") || hash === "" || hash === "#" || hash === "#/")) {
    return;
  }

  void (async () => {
    const { listen } = await import("@tauri-apps/api/event");
    await listen("todo://completed", (event) => {
      const e = parseTodoCompleted(event.payload);
      if (!e) return;
      // waving 覆盖 + 气泡（全清文案优先；showBubble 内部净化）
      usePetStore.getState().startCelebration();
      usePetStore.getState().showBubble(celebrationText(e));
    });
    console.log("[pulsepet] todo bridge ready (pet)");
  })();
}
