/**
 * atlas：M5 atlas 元数据解析与 Rust 命令封装（DESIGN §6.2，TC-SP-04~11）。
 *
 * - `parseAtlasMeta` / `makeAtlasPixels` / `parsePetOptions` 为纯函数（vitest
 *   可裸跑）；Rust DTO 用 camelCase（serde rename_all）。
 * - RGBA 图块由 Rust 解码后整块二进制下发（`atlas_pixels` 返回 raw bytes →
 *   webview invoke 得 ArrayBuffer），前端不做 webp/png 解码（TC-SP-04）。
 * - invoke 封装走动态 import + 运行时探测（与 token-stats.ts 同模式）。
 */

import { isTauriRuntime } from "./token-stats";
import { t } from "./i18n";

export type AtlasSource = "builtin" | "codex" | "petdex";

export interface AtlasMeta {
  /** 用户配置（app_state `pet.selected`）的 id；null = 自动。 */
  requested: string | null;
  currentId: string;
  currentSource: AtlasSource;
  cols: number;
  rows: number;
  frameW: number;
  frameH: number;
  /** 回退提示（TC-SP-05/09：损坏 / 非标准网格 / 未找到）。 */
  notice: string | null;
}

export interface AtlasPixels {
  cols: number;
  rows: number;
  frameW: number;
  frameH: number;
  rgba: Uint8Array;
}

export interface PetOption {
  id: string;
  displayName: string;
  source: AtlasSource;
  ok: boolean;
  problem: string | null;
}

function isAtlasSource(v: unknown): v is AtlasSource {
  return v === "builtin" || v === "codex" || v === "petdex";
}

/** 从 Rust DTO 解析 atlas 元数据（非法 → null）。 */
export function parseAtlasMeta(p: unknown): AtlasMeta | null {
  if (typeof p !== "object" || p === null) return null;
  const o = p as Record<string, unknown>;
  const { requested, currentId, currentSource, cols, rows, frameW, frameH, notice } = o;
  if (typeof currentId !== "string" || !isAtlasSource(currentSource)) return null;
  const nums = [cols, rows, frameW, frameH];
  for (const n of nums) {
    if (typeof n !== "number" || !Number.isInteger(n) || n <= 0) return null;
  }
  if (requested != null && typeof requested !== "string") return null;
  if (notice != null && typeof notice !== "string") return null;
  return {
    requested: (requested as string | null) ?? null,
    currentId,
    currentSource,
    cols: cols as number,
    rows: rows as number,
    frameW: frameW as number,
    frameH: frameH as number,
    notice: (notice as string | null) ?? null,
  };
}

/** 校验 RGBA 字节数与网格一致（不符 → null，防越界切帧）。 */
export function makeAtlasPixels(
  meta: AtlasMeta,
  bytes: Uint8Array | ArrayBuffer,
): AtlasPixels | null {
  const rgba = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  const expect = meta.cols * meta.rows * meta.frameW * meta.frameH * 4;
  if (rgba.byteLength !== expect) return null;
  return {
    cols: meta.cols,
    rows: meta.rows,
    frameW: meta.frameW,
    frameH: meta.frameH,
    rgba,
  };
}

/** 解析面板下拉列表（非法 → null；单项非法整体拒收，保持 Rust DTO 契约严格）。 */
export function parsePetOptions(p: unknown): PetOption[] | null {
  if (!Array.isArray(p)) return null;
  const out: PetOption[] = [];
  for (const item of p) {
    if (typeof item !== "object" || item === null) return null;
    const o = item as Record<string, unknown>;
    if (typeof o.id !== "string" || typeof o.displayName !== "string") return null;
    if (!isAtlasSource(o.source)) return null;
    if (typeof o.ok !== "boolean") return null;
    if (o.problem != null && typeof o.problem !== "string") return null;
    out.push({
      id: o.id,
      displayName: o.displayName,
      source: o.source,
      ok: o.ok,
      problem: (o.problem as string | null) ?? null,
    });
  }
  return out;
}

// ---- Rust 命令封装（仅 Tauri 运行时可用）----

/** 当前 atlas 元数据（含回退 notice）。 */
export async function fetchAtlasMeta(): Promise<AtlasMeta> {
  if (!isTauriRuntime()) throw new Error(t("atlas.needApp"));
  const { invoke } = await import("@tauri-apps/api/core");
  const raw = await invoke<unknown>("atlas_meta");
  const meta = parseAtlasMeta(raw);
  if (!meta) throw new Error("atlas_meta 返回非法数据");
  return meta;
}

/** 当前 atlas RGBA 整块（raw bytes → ArrayBuffer）。 */
export async function fetchAtlasPixels(meta: AtlasMeta): Promise<AtlasPixels> {
  if (!isTauriRuntime()) throw new Error(t("atlas.needApp"));
  const { invoke } = await import("@tauri-apps/api/core");
  const raw = await invoke<ArrayBuffer>("atlas_pixels");
  const pixels = makeAtlasPixels(meta, raw);
  if (!pixels) throw new Error("atlas_pixels 尺寸与 meta 不符");
  return pixels;
}

/** 面板"选择宠物"下拉数据。 */
export async function fetchPetOptions(): Promise<PetOption[]> {
  if (!isTauriRuntime()) throw new Error(t("atlas.needApp"));
  const { invoke } = await import("@tauri-apps/api/core");
  const raw = await invoke<unknown>("atlas_list_pets");
  const list = parsePetOptions(raw);
  if (!list) throw new Error("atlas_list_pets 返回非法数据");
  return list;
}

/** 选择宠物（null = 恢复自动，默认 blinking-kitty）；返回加载结果 meta（失败时已回退内置占位）。 */
export async function selectPet(id: string | null): Promise<AtlasMeta> {
  if (!isTauriRuntime()) throw new Error(t("atlas.needApp"));
  const { invoke } = await import("@tauri-apps/api/core");
  const raw = await invoke<unknown>("atlas_select", { id });
  const meta = parseAtlasMeta(raw);
  if (!meta) throw new Error("atlas_select 返回非法数据");
  return meta;
}
