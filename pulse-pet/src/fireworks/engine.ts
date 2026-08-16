/**
 * 烟花粒子引擎（DESIGN §5.3，TC-RM-09/10）——纯逻辑、无 DOM，供 vitest 直接单测。
 *
 * - 一发"流光花瓣"烟花：上升段（shell + 拖尾流光粒子）→ 顶部炸裂成
 *   320-440 枚花瓣粒子（HSL 渐变 + 摇曳 + alpha fade）；
 * - 全程粒子数（含流光）峰值 ∈ [300, 500]；
 * - 总时长 ~3.8s，硬上限 5s（isDone 上界，对应 TC-RM-09 "3-5s 内自动 hide"）；
 * - `reset` 支持连播复用（TC-RM-10：不残留上一场粒子）。
 *
 * 渲染（canvas 部分在 Fireworks.tsx）：拖尾用每帧 destination-out 半透明擦除
 * （保持窗口透明，不留残帧），粒子 'lighter' 叠加发光。
 */

/** 帧时间（ms）→ 引擎内部以 60fps 帧为单位步进。 */
export const FRAME_MS = 1000 / 60;
/** 硬上限：超过即判完成（TC-RM-09：3-5s 内必 hide）。 */
export const FIREWORKS_HARD_CAP_MS = 5000;
/** 粒子数目标区间（DESIGN §5.3：~300-500）。 */
export const FIREWORKS_MIN_PARTICLES = 300;
export const FIREWORKS_MAX_PARTICLES = 500;

/** Rust `fireworks://play` payload（逻辑像素坐标，渲染时 ×dpr）。 */
export interface FireworksPlay {
  log_id: number;
  origin_x: number;
  origin_y: number;
  target_x: number;
  target_y: number;
}

export function parseFireworksPlay(payload: unknown): FireworksPlay | null {
  if (typeof payload !== "object" || payload === null) return null;
  const p = payload as Record<string, unknown>;
  const num = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
  if (!num(p.log_id) || !num(p.origin_x) || !num(p.origin_y) || !num(p.target_x) || !num(p.target_y)) {
    return null;
  }
  return {
    log_id: p.log_id,
    origin_x: p.origin_x,
    origin_y: p.origin_y,
    target_x: p.target_x,
    target_y: p.target_y,
  };
}

export type ParticleType = "stream" | "petal";

export interface Particle {
  type: ParticleType;
  x: number;
  y: number;
  vx: number;
  vy: number;
  /** 存活 ms。 */
  age: number;
  maxAge: number;
  hue: number;
  hueDrift: number;
  size: number;
  /** 花瓣摇曳相位。 */
  phase: number;
  wobbleAmp: number;
}

interface Shell {
  x: number;
  y: number;
  vx: number;
  vy: number;
}

/** [a, b) 均匀随机（注入 rand 便于测试确定性）。 */
type Rand = () => number;
const defaultRand: Rand = Math.random;
function range(rand: Rand, a: number, b: number): number {
  return a + rand() * (b - a);
}

export class FireworksEngine {
  private particles: Particle[] = [];
  private shell: Shell | null = null;
  private t = 0;
  private burstDone = false;
  private peak = 0;
  private readonly rand: Rand;
  private play: FireworksPlay;
  private baseHue = 0;

  constructor(play: FireworksPlay, rand: Rand = defaultRand) {
    this.rand = rand;
    this.play = play;
    this.launch();
  }

  /** 新一场（TC-RM-10 复用）：清空一切状态重新发射。 */
  reset(play: FireworksPlay): void {
    this.particles = [];
    this.burstDone = false;
    this.t = 0;
    this.peak = 0;
    this.play = play;
    this.launch();
  }

  private launch(): void {
    this.baseHue = Math.floor(range(this.rand, 0, 360));
    const { origin_x, origin_y, target_x, target_y } = this.play;
    const dx = target_x - origin_x;
    const dy = target_y - origin_y;
    const dist = Math.hypot(dx, dy) || 1;
    // 上升速度（px/帧）：竖直为主 + 朝目标方向的轻微水平分量
    const rise = range(this.rand, 15.0, 18.5);
    const tilt = range(this.rand, 0.5, 1.1);
    this.shell = {
      x: origin_x,
      y: origin_y,
      vx: (dx / dist) * rise * 0.18 * tilt,
      vy: -rise,
    };
  }

  /** 推进一帧（dtMs 毫秒）。 */
  step(dtMs: number): void {
    const dt = Math.max(0, Math.min(dtMs, 100)) / FRAME_MS;
    this.t += dtMs;
    const GRAV = 0.32; // px/帧²

    if (!this.burstDone && this.shell) {
      const s = this.shell;
      s.x += s.vx * dt;
      s.y += s.vy * dt;
      s.vy += GRAV * dt;
      // 流光拖尾：每帧 1-2 枚短命亮星（密度受控：峰值粒子数留 ≤500 余量）
      const n = 1 + Math.floor(this.rand() * 2);
      for (let i = 0; i < n; i++) {
        this.particles.push({
          type: "stream",
          x: s.x + range(this.rand, -1.5, 1.5),
          y: s.y + range(this.rand, -1.5, 1.5),
          vx: range(this.rand, -0.35, 0.35),
          vy: range(this.rand, 0.3, 1.1),
          age: 0,
          maxAge: range(this.rand, 200, 460),
          hue: this.baseHue + range(this.rand, -14, 14),
          hueDrift: 0,
          size: range(this.rand, 0.9, 1.7),
          phase: 0,
          wobbleAmp: 0,
        });
      }
      // 接近顶点（垂直速度衰减殆尽）或超时保险 → 炸裂
      if (s.vy >= -0.65 || this.t > 1400) {
        this.burst();
      }
    }

    for (let i = this.particles.length - 1; i >= 0; i--) {
      const p = this.particles[i];
      p.age += dtMs;
      if (p.age >= p.maxAge) {
        this.particles.splice(i, 1);
        continue;
      }
      const drag = p.type === "petal" ? 0.982 : 0.96;
      const g = p.type === "petal" ? GRAV * 0.42 : GRAV * 0.8;
      p.vx *= Math.pow(drag, dt);
      p.vy = p.vy * Math.pow(drag, dt) + g * dt;
      // 花瓣摇曳（正弦横摆，"流光花瓣"质感）
      if (p.type === "petal") {
        p.vx += Math.sin((p.age / 1000) * 6 + p.phase) * p.wobbleAmp * dt;
      }
      p.x += p.vx * dt;
      p.y += p.vy * dt;
      p.hue += p.hueDrift * dt;
    }
    if (this.particles.length > this.peak) {
      this.peak = this.particles.length;
    }
  }

  private burst(): void {
    this.burstDone = true;
    const s = this.shell;
    this.shell = null;
    if (!s) return;
    // 花瓣粒子 320-420：叠加未熄灭的流光后峰值仍 <500
    const n = 320 + Math.floor(this.rand() * 100);
    for (let i = 0; i < n; i++) {
      const angle = this.rand() * Math.PI * 2;
      const speed = range(this.rand, 1.0, 6.6);
      const petal = this.rand() < 0.65; // 2/3 花瓣形（更慢更飘），1/3 亮星
      this.particles.push({
        type: "petal",
        x: s.x,
        y: s.y,
        vx: Math.cos(angle) * speed * (petal ? 0.62 : 1),
        vy: Math.sin(angle) * speed * (petal ? 0.62 : 1),
        age: 0,
        maxAge: range(this.rand, petal ? 1900 : 1500, petal ? 3100 : 2400),
        hue: this.baseHue + range(this.rand, -26, 26),
        hueDrift: range(this.rand, -16, 16),
        size: petal ? range(this.rand, 1.6, 2.8) : range(this.rand, 1.0, 1.8),
        phase: this.rand() * Math.PI * 2,
        wobbleAmp: petal ? range(this.rand, 0.02, 0.09) : 0,
      });
    }
  }

  /** 完成判定：炸裂完且粒子全灭，或超硬上限（5s 上界，TC-RM-09）。 */
  isDone(): boolean {
    return this.t >= FIREWORKS_HARD_CAP_MS || (this.burstDone && this.particles.length === 0);
  }

  /** 当前存活粒子数。 */
  get particleCount(): number {
    return this.particles.length;
  }

  /** 全程粒子数峰值（含流光；验收 ~300-500）。 */
  get peakCount(): number {
    return this.peak;
  }

  /** 已播放时长（ms）。 */
  get elapsed(): number {
    return this.t;
  }

  /** 是否已炸裂。 */
  get hasBurst(): boolean {
    return this.burstDone;
  }

  /** 当前场次的 reminder_log id（播放结束回报 `fireworks_finished` 用）。 */
  getPlayLogId(): number {
    return this.play.log_id;
  }

  /** 只读粒子视图（渲染层消费）。 */
  getParticles(): readonly Particle[] {
    return this.particles;
  }
}
