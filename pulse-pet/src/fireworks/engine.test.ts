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

  it("炸裂点=传入的目标点（屏幕中轴+0.3 屏高，DESIGN §5.3 用户定案）", () => {
    for (const target of [
      { x: 735, y: 286.8 }, // 单显示器：中轴 + 0.3 屏高（2940×1912 dpr2）
      { x: 100, y: 100 }, // 任意目标（如另一显示器的绽放点）
    ]) {
      const e = new FireworksEngine({ ...PLAY, target_x: target.x, target_y: target.y });
      // 逐帧步进到炸裂
      let guard = 0;
      while (!e.hasBurst && guard++ < 600) e.step(FRAME_MS);
      expect(e.hasBurst).toBe(true);
      expect(e.getBurstPoint()).toEqual({ x: target.x, y: target.y });
      // 炸裂帧的花瓣粒子都从目标点出发（此刻位移 ≤ 数帧速度）
      const ps = e.getParticles().filter((p) => p.type === "petal");
      expect(ps.length).toBeGreaterThanOrEqual(320);
      for (const p of ps) {
        expect(Math.abs(p.x - target.x)).toBeLessThanOrEqual(60);
        expect(Math.abs(p.y - target.y)).toBeLessThanOrEqual(60);
      }
    }
  });

  it("发射点来自 payload：上升段流光出现在发射点附近（弹道起始段）", () => {
    const e = new FireworksEngine(PLAY);
    // 步进 1 帧：shell 沿弹道前进 ~5%（easeOutQuad 起始快），流光粒子在起始段附近
    e.step(FRAME_MS);
    const ps = e.getParticles();
    expect(ps.length).toBeGreaterThan(0);
    for (const p of ps) {
      expect(Math.abs(p.x - PLAY.origin_x)).toBeLessThan(45);
      expect(Math.abs(p.y - PLAY.origin_y)).toBeLessThan(45);
    }
    // 未到达前不炸裂
    expect(e.hasBurst).toBe(false);
    expect(e.getBurstPoint()).toBeNull();
  });

  it("发射点=目标点（宠物恰在屏幕中心）也能正常炸裂", () => {
    const e = new FireworksEngine({
      ...PLAY,
      origin_x: PLAY.target_x,
      origin_y: PLAY.target_y,
    });
    runToEnd(e);
    expect(e.getBurstPoint()).toEqual({ x: PLAY.target_x, y: PLAY.target_y });
    expect(e.isDone()).toBe(true);
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
