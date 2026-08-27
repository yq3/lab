/**
 * 气泡多行显示 CSS 钉子（task-pulsepet-v2-polish #4）。
 *
 * 背景：idle 汇报「… · 今日 X」追加段（Rust build_cc_idle_report 拼接，
 * TC-M3-09-1 措辞逐字钉住）+ `[cc] ` 徽标在 208px 单行省略气泡内被截断
 * 不可见。定案（playwright 实测三轮后的最终口径，见 global.css 注释）：
 * - 弃 nowrap/ellipsis 与 -webkit-line-clamp（box 布局下 absolute 盒
 *   left:50% 居中法的 shrink-to-fit 塌成 110px 窄柱）；
 * - `width: max-content` + `max-width: 208px`：短文案收窄单行、长文案
 *   208px 折行（idle 汇报 ~476px 需三行，「· 今日 X」落第三行完整可见）；
 * - `max-height: 70px` 三行截断（文案措辞钉字不可精简，三行是尾段可见
 *   的最小行数）；超三行直接裁掉无省略号（极端 140 字符文案，可接受）。
 *
 * vitest 为 node 环境无 DOM 布局，本测试以「规则文本存在性」钉住多行
 * 口径，渲染行为另由 playwright 实测佐证（见任务报告）；防后续 CSS
 * 重构静默回退到单行省略。
 */
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { describe, expect, it } from "vitest";

/** 定位 global.css：vitest 的 import.meta.url 是相对 root 的虚拟路径，
 *  优先按文件自身位置推（IDE 单跑/未来 runner），回退 process.cwd()
 *  （npm test 恒在 pulse-pet/ 下执行）。 */
function locateCss(): string {
  const byFile = join(dirname(fileURLToPath(import.meta.url)), "../../styles/global.css");
  if (existsSync(byFile)) return byFile;
  const byCwd = join(process.cwd(), "src/styles/global.css");
  if (existsSync(byCwd)) return byCwd;
  throw new Error(`global.css not found: tried ${byFile} and ${byCwd}`);
}
const css = readFileSync(locateCss(), "utf8");

/** 抽取指定选择器规则块（含大括号体；找不到则空串）。 */
function ruleOf(selector: string): string {
  const idx = css.indexOf(selector);
  if (idx === -1) return "";
  const start = css.indexOf("{", idx);
  const end = css.indexOf("}", start);
  return start === -1 || end === -1 ? "" : css.slice(start + 1, end);
}

describe("pet-bubble 多行显示（v2 打磨轮 #4）", () => {
  const bubble = ruleOf(".pet-bubble");

  it(".pet-bubble 规则存在", () => {
    expect(bubble).not.toBe("");
  });

  it("多行折行：white-space: normal", () => {
    expect(bubble).toContain("white-space: normal");
  });

  it("测宽修复：width max-content + max-width 208（防 left:50% 下 shrink-to-fit 塌窄柱）", () => {
    expect(bubble).toContain("width: max-content");
    expect(bubble).toContain("max-width: 208px");
  });

  it("至多三行截断：max-height: 70px（「· 今日 X」第三行完整可见的最小行数）", () => {
    expect(bubble).toContain("max-height: 70px");
  });

  it("已撤单行省略口径（nowrap / text-overflow 不在气泡规则内）", () => {
    expect(bubble).not.toContain("nowrap");
    expect(bubble).not.toContain("text-overflow");
  });

  it("agent 徽标自身仍防断行（.pet-bubble-agent 保留 nowrap）", () => {
    const agent = ruleOf(".pet-bubble-agent");
    expect(agent).toContain("white-space: nowrap");
  });
});
