/**
 * token-chart：自画 SVG 的纯几何计算（TC-TK-09：不引入重依赖库）。
 *
 * 输入数值数组，输出柱状图 rect / 饼图 arc path，与 React 组件解耦便于单测。
 */

export interface BarRect {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface BarOptions {
  width: number;
  height: number;
  pad: number;
  /** 柱宽占每格宽度的比例（0-1，默认 0.6）。 */
  fill?: number;
}

/**
 * 柱状图几何：柱高与最大值成比例，基线在 `height - pad`，柱条在 `[pad, width-pad]`
 * 均分。全零输入返回高度 0 的条（不产生 NaN）。
 */
export function computeBars(values: number[], opts: BarOptions): BarRect[] {
  const { width, height, pad } = opts;
  const fill = opts.fill ?? 0.6;
  const n = values.length;
  if (n === 0) return [];
  const plotW = Math.max(width - 2 * pad, 0);
  const plotH = Math.max(height - 2 * pad, 0);
  const max = Math.max(...values, 0);
  const slot = plotW / n;
  const barW = slot * fill;
  const baseline = pad + plotH;
  return values.map((v, i) => {
    const h = max > 0 ? (Math.max(v, 0) / max) * plotH : 0;
    return {
      x: pad + i * slot + (slot - barW) / 2,
      y: baseline - h,
      w: barW,
      h,
    };
  });
}

export interface PieItem {
  value: number;
  label: string;
}

export interface PieSlice {
  /** SVG path `d`（圆心 (r,r)、半径 r，从 12 点方向顺时针）。 */
  path: string;
  /** 占比 0-100。 */
  percent: number;
  value: number;
  label: string;
}

function arcPath(cx: number, cy: number, r: number, a0: number, a1: number): string {
  // 角度（弧度）→ 坐标；12 点方向为 0，顺时针为正
  const pt = (a: number) => [cx + r * Math.sin(a), cy - r * Math.cos(a)] as const;
  const [x0, y0] = pt(a0);
  const [x1, y1] = pt(a1);
  const largeArc = a1 - a0 > Math.PI ? 1 : 0;
  return `M ${cx} ${cy} L ${x0.toFixed(2)} ${y0.toFixed(2)} A ${r} ${r} 0 ${largeArc} 1 ${x1.toFixed(2)} ${y1.toFixed(2)} Z`;
}

/**
 * 饼图切片：数值 → 占比 + SVG 弧 path。单项 100% 生成两段半圆（完整圆）；
 * 空或全零输入返回空数组。
 */
export function pieSlices(items: PieItem[], r: number): PieSlice[] {
  const positive = items.filter((i) => i.value > 0);
  const total = positive.reduce((acc, i) => acc + i.value, 0);
  if (total <= 0) return [];
  const cx = r;
  const cy = r;
  let angle = 0;
  return positive.map((item) => {
    const sweep = (item.value / total) * Math.PI * 2;
    let path: string;
    if (positive.length === 1) {
      // 完整圆：从圆心出发两段 180° 弧拼合
      const pt = (a: number) =>
        [cx + r * Math.sin(a), cy - r * Math.cos(a)] as const;
      const [x0, y0] = pt(0);
      const [x1, y1] = pt(Math.PI);
      const [x2, y2] = pt(Math.PI * 2);
      const f = (n: number) => n.toFixed(2);
      path =
        `M ${f(cx)} ${f(cy)} L ${f(x0)} ${f(y0)} ` +
        `A ${r} ${r} 0 0 1 ${f(x1)} ${f(y1)} ` +
        `A ${r} ${r} 0 0 1 ${f(x2)} ${f(y2)} Z`;
    } else {
      path = arcPath(cx, cy, r, angle, angle + sweep);
    }
    const slice: PieSlice = {
      path,
      percent: (item.value / total) * 100,
      value: item.value,
      label: item.label,
    };
    angle += sweep;
    return slice;
  });
}
