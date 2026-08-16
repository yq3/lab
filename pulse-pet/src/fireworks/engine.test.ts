import { describe, expect, it } from "vitest";
import {
  FIREWORKS_HARD_CAP_MS,
  FIREWORKS_MAX_PARTICLES,
  FIREWORKS_MIN_PARTICLES,
  FireworksEngine,
  FRAME_MS,
  parseFireworksPlay,
  type FireworksPlay,
} from "./engine";

const PLAY: FireworksPlay = {
  log_id: 3,
  origin_x: 640,
  origin_y: 800,
  target_x: 700,
  target_y: 300,
};

/** 以 60fps 步进直到完成（带防死循环上界）。 */
function runToEnd(engine: FireworksEngine): number {
  let frames = 0;
  while (!engine.isDone() && frames < 60 * 10) {
    engine.step(FRAME_MS);
    frames += 1;
  }
  return frames;
}

describe("FireworksEngine（TC-RM-09 可断言逻辑层）", () => {
  it("上升段后炸裂，峰值粒子数在 300-500 区间", () => {
    const engine = new FireworksEngine(PLAY);
    // 确定性随机也行，但默认 Math.random 下界/上界由构造保证——多跑几轮稳定区间
    for (let round = 0; round < 5; round++) {
      const e = round === 0 ? engine : new FireworksEngine(PLAY);
      runToEnd(e);
      expect(e.hasBurst).toBe(true);
      expect(e.peakCount).toBeGreaterThanOrEqual(FIREWORKS_MIN_PARTICLES);
      expect(e.peakCount).toBeLessThanOrEqual(FIREWORKS_MAX_PARTICLES);
    }
  });

  it("总时长落在 2.5s-5s（对应窗口 3-5s 内自动 hide 的上界）", () => {
    const e = new FireworksEngine(PLAY);
    runToEnd(e);
    expect(e.elapsed).toBeGreaterThanOrEqual(2500);
    expect(e.elapsed).toBeLessThanOrEqual(FIREWORKS_HARD_CAP_MS);
  });

  it("完成后粒子清空（无残留帧的引擎侧条件）", () => {
    const e = new FireworksEngine(PLAY);
    runToEnd(e);
    expect(e.particleCount).toBe(0);
    expect(e.isDone()).toBe(true);
  });

  it("发射点来自 payload（宠物位置为发射点）", () => {
    const e = new FireworksEngine(PLAY);
    // 未步进时无粒子；步进 1 帧后流光粒子应出现在发射点附近
    // （上升速度 15-18.5 px/帧，首帧位移即在此量级）
    e.step(FRAME_MS);
    const ps = e.getParticles();
    expect(ps.length).toBeGreaterThan(0);
    for (const p of ps) {
      expect(Math.abs(p.x - PLAY.origin_x)).toBeLessThan(5);
      expect(Math.abs(p.y - PLAY.origin_y)).toBeLessThan(25);
    }
  });

  it("reset 后可复用：清空旧粒子、重新完整播放（TC-RM-10）", () => {
    const e = new FireworksEngine(PLAY);
    runToEnd(e);
    expect(e.isDone()).toBe(true);
    const play2 = { ...PLAY, log_id: 4, origin_x: 100, origin_y: 500 };
    e.reset(play2);
    expect(e.particleCount).toBe(0); // 不残留上一场
    expect(e.isDone()).toBe(false);
    const frames = runToEnd(e);
    expect(frames).toBeGreaterThan(0);
    expect(e.hasBurst).toBe(true);
    expect(e.peakCount).toBeGreaterThanOrEqual(FIREWORKS_MIN_PARTICLES);
    expect(e.peakCount).toBeLessThanOrEqual(FIREWORKS_MAX_PARTICLES);
  });

  it("异常大步长（切后台回来）不炸、不超上限", () => {
    const e = new FireworksEngine(PLAY);
    e.step(400); // 单步 400ms
    e.step(2000); // 单步 2s
    expect(e.particleCount).toBeLessThanOrEqual(FIREWORKS_MAX_PARTICLES + 5);
    runToEnd(e);
    expect(e.isDone()).toBe(true);
  });
});

describe("parseFireworksPlay", () => {
  it("合法 payload 解析", () => {
    expect(parseFireworksPlay(PLAY)).toEqual(PLAY);
  });

  it("缺字段/类型错 → null", () => {
    expect(parseFireworksPlay(null)).toBeNull();
    expect(parseFireworksPlay("x")).toBeNull();
    expect(parseFireworksPlay({ ...PLAY, log_id: "3" })).toBeNull();
    expect(parseFireworksPlay({ origin_x: 1, origin_y: 2, target_x: 3, target_y: 4 })).toBeNull();
    expect(parseFireworksPlay({ ...PLAY, target_x: Number.NaN })).toBeNull();
  });
});
