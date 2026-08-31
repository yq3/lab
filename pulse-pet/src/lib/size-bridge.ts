/**
 * size-bridge：宠物大小三档（V2-OPEN-ITEMS §十一）TS 侧封装。
 *
 * 档位唯一权威在 Rust（`src-tauri/src/pet_size.rs`，持久化 app_state
 * `pet.size`）；本模块提供：
 * - 档位类型 / 逻辑像素表（PET_SIZES 与 Rust `logical_of` **锁步**，两侧
 *   注释互钉——改任一侧必须同步另一侧）；
 * - 事件名常量 + 载荷解析（`pet://size`，设置页切换后 Rust 广播）；
 * - invoke 封装（动态 import + isTauriRuntime 守卫，vitest/node 可裸跑）；
 * - `initSizeBridge`：启动查询 + 事件订阅 → petStore（pet/panel 都跑，
 *   panel 的设置页分段控件依赖同一状态位）。
 */

import { isTauriRuntime } from "./token-stats";
import { usePetStore } from "../pet/petStore";

/** Rust 广播档位变化的 Tauri event 名。 */
export const SIZE_EVENT = "pet://size";

/** 档位 id（与 Rust `parse_size` 的合法值集合一致）。 */
export type PetSize = "small" | "medium" | "large";

/**
 * 档位 → pet 窗口/canvas 逻辑像素。与 Rust `pet_size.rs` 的 `logical_of`
 * 锁步（184 = 右键菜单实测外宽 176px 不裁剪的下限，§11.4）。
 */
export const PET_SIZES: Record<PetSize, number> = {
  small: 184,
  medium: 220,
  large: 280,
};

export function isPetSize(v: unknown): v is PetSize {
  return v === "small" || v === "medium" || v === "large";
}

/** 解析 `pet://size` 载荷 `{size, logical}`；非法 → null（不误更新状态）。 */
export function parseSizePayload(payload: unknown): PetSize | null {
  if (typeof payload === "object" && payload !== null && "size" in payload) {
    const v = (payload as { size: unknown }).size;
    if (isPetSize(v)) return v;
  }
  return null;
}

/** 查询当前档位（Rust 唯一权威；null = 未设置 → 前端回退 medium）。 */
export async function fetchPetSize(): Promise<PetSize | null> {
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<PetSize | null>("pet_get_size");
}

/** 设置档位（Rust 侧应用窗口 set_size + 持久化 + `pet://size` 广播）。 */
export async function setPetSize(size: PetSize): Promise<void> {
  const { invoke } = await import("@tauri-apps/api/core");
  await invoke("pet_set_size", { size });
}

/**
 * 启动桥接：查询当前档位 + 订阅变化事件 → petStore。
 * pet / panel 路由都初始化（panel 设置页分段控件依赖同一状态位）。
 * 非 Tauri 环境（vitest / 纯浏览器 dev）直接返回。
 */
export async function initSizeBridge(): Promise<void> {
  if (typeof window === "undefined") return;
  if (!isTauriRuntime()) return;
  try {
    const saved = await fetchPetSize();
    if (isPetSize(saved)) usePetStore.getState().setSize(saved);
  } catch (e) {
    console.error("[pulsepet] pet size query failed:", e);
  }
  const { listen } = await import("@tauri-apps/api/event");
  await listen(SIZE_EVENT, (event) => {
    const v = parseSizePayload(event.payload);
    if (v !== null) usePetStore.getState().setSize(v);
  });
}
