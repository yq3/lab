/**
 * 气泡文案净化（App 侧兜底；口径与插件 sanitizeText 一致，DESIGN §3.1 / §4.3）。
 *
 * Rust 侧 token 汇报文案本身只由数字格式化生成（白名单模板），但 M2 净化约束
 * （单行、1-140 字符）在展示端再执行一次，双保险防任何上游注入。
 */

/** 气泡自动隐藏时长（DESIGN §5.2：8s）。 */
export const BUBBLE_AUTO_HIDE_MS = 8000;

/** 单行化 + trim + 1-140 截断；空/非法输入返回空串（丢弃，不出气泡）。 */
export function sanitizeBubbleText(text: unknown): string {
  if (typeof text !== "string") return "";
  const s = text.replace(/[\r\n]+/g, " ").trim();
  if (!s) return "";
  return s.length > 140 ? s.slice(0, 140) : s;
}
