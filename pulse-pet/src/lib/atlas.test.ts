import { describe, expect, it } from "vitest";

import {
  makeAtlasPixels,
  parseAtlasMeta,
  parsePetOptions,
  type AtlasMeta,
} from "./atlas";

/** M5 atlas TS 侧纯函数：meta/下拉列表解析（Rust DTO camelCase 字段）。 */

const OK_META: AtlasMeta = {
  requested: "kitty",
  currentId: "kitty",
  currentSource: "codex",
  cols: 8,
  rows: 9,
  frameW: 192,
  frameH: 208,
  notice: null,
  idle: null,
};

describe("parseAtlasMeta", () => {
  it("合法 payload 解析", () => {
    expect(
      parseAtlasMeta({
        requested: "kitty",
        currentId: "kitty",
        currentSource: "codex",
        cols: 8,
        rows: 9,
        frameW: 192,
        frameH: 208,
        notice: null,
      }),
    ).toEqual(OK_META);
  });

  it("v2 8×11 也可解析（1536×2288）", () => {
    const m = parseAtlasMeta({
      requested: null,
      currentId: "builtin",
      currentSource: "builtin",
      cols: 8,
      rows: 11,
      frameW: 192,
      frameH: 208,
      notice: "提示文案",
    });
    expect(m?.rows).toBe(11);
    expect(m?.notice).toBe("提示文案");
  });

  it("非法 payload → null（缺字段 / 非法网格 / 非法来源）", () => {
    expect(parseAtlasMeta(null)).toBeNull();
    expect(parseAtlasMeta("x")).toBeNull();
    expect(parseAtlasMeta({})).toBeNull();
    expect(parseAtlasMeta({ ...OK_META, cols: "8" })).toBeNull();
    expect(parseAtlasMeta({ ...OK_META, cols: 0 })).toBeNull();
    expect(parseAtlasMeta({ ...OK_META, frameW: 0 })).toBeNull();
    expect(parseAtlasMeta({ ...OK_META, currentSource: "unknown" })).toBeNull();
  });

  it("§十一：idle 度量解析（合法对象 / 缺省 null / 非法 → null）", () => {
    expect(parseAtlasMeta({ ...OK_META, idle: { x: 56, y: 48, w: 88, h: 108 } })?.idle).toEqual({
      x: 56,
      y: 48,
      w: 88,
      h: 108,
    });
    // 缺省 / null → null（旧 DTO / 全透明兜底，渲染层回退全帧适配）
    expect(parseAtlasMeta(OK_META)?.idle).toBeNull();
    expect(parseAtlasMeta({ ...OK_META, idle: null })?.idle).toBeNull();
    // 非法：零尺寸 / 负坐标 / 非整数 / 缺字段
    expect(parseAtlasMeta({ ...OK_META, idle: { x: 0, y: 0, w: 0, h: 10 } })?.idle).toBeNull();
    expect(parseAtlasMeta({ ...OK_META, idle: { x: -1, y: 0, w: 10, h: 10 } })?.idle).toBeNull();
    expect(parseAtlasMeta({ ...OK_META, idle: { x: 1.5, y: 0, w: 10, h: 10 } })?.idle).toBeNull();
    expect(parseAtlasMeta({ ...OK_META, idle: { x: 0, y: 0, w: 10 } })?.idle).toBeNull();
    expect(parseAtlasMeta({ ...OK_META, idle: "big" })?.idle).toBeNull();
  });
});

describe("makeAtlasPixels：RGBA 字节校验", () => {
  it("字节数 = cols×rows×frameW×frameH×4 时通过", () => {
    const tiny: AtlasMeta = { ...OK_META, cols: 8, rows: 9, frameW: 192, frameH: 208 };
    const bytes = new Uint8Array(8 * 9 * 192 * 208 * 4);
    const p = makeAtlasPixels(tiny, bytes);
    expect(p).not.toBeNull();
    expect(p?.rgba).toBe(bytes);
    expect(p?.cols).toBe(8);
  });

  it("字节数不符 → null（拒载防越界切帧）", () => {
    const bytes = new Uint8Array(100);
    expect(makeAtlasPixels(OK_META, bytes)).toBeNull();
  });

  it("接受 ArrayBuffer 输入（invoke 返回形态）", () => {
    const ab = new ArrayBuffer(8 * 9 * 192 * 208 * 4);
    const p = makeAtlasPixels(OK_META, ab);
    expect(p?.rgba.byteLength).toBe(ab.byteLength);
  });
});

describe("parsePetOptions：面板下拉数据", () => {
  it("解析列表 + 顺序保持（内置 → codex → petdex）", () => {
    const list = parsePetOptions([
      { id: "builtin", displayName: "内置占位小猫", source: "builtin", ok: true, problem: null },
      { id: "kitty", displayName: "小猫", source: "codex", ok: true, problem: null },
      { id: "boba", displayName: "波霸", source: "petdex", ok: false, problem: "损坏" },
    ]);
    expect(list).toHaveLength(3);
    expect(list?.[0].id).toBe("builtin");
    expect(list?.[2].ok).toBe(false);
    expect(list?.[2].problem).toBe("损坏");
  });

  it("非法项过滤 / 非数组 → null", () => {
    expect(parsePetOptions(null)).toBeNull();
    expect(parsePetOptions("x")).toBeNull();
    expect(parsePetOptions([{ id: 1 }])).toBeNull();
  });
});
