import { usePetStore } from "./petStore";
import { t } from "../lib/i18n";
import { bubbleAgentBadge } from "../lib/bubble-queue";

/**
 * 宠物气泡（v2 M2 排队模型下的显示位，V2-DESIGN §2.6.3）：
 * - 文案经 petStore.pushBubble 净化（单行 1-140）；current 条目按级别 dwell
 *   自动离场（bubble-queue 内核驱动）；
 * - 视觉走「宠物世界」固定色（`--pet-world-*`，不随主题）：暖白底 + 2px
 *   墨边 + 2px 2px 0 硬阴影 + 像素尖角（45° 旋转小方块）；
 * - critical 级左侧 4px 蜜橘色条（可交互暗示——点宠物确认）；至多两行
 *   （-webkit-line-clamp，v2 打磨轮 #4：idle 汇报「 · 今日 X」追加段在
 *   208px 单行省略下不可见，改两行后完整可见；短文案仍单行）。
 * - v2 M4（TC-M4-13）：critical 且有 reminder 载荷时右侧 snooze 按钮
 *   「稍后 10 分钟」——hover 浮现不喧宾（208px 单行气泡内用 ⏱ 10min 短标 +
 *   title 完整语义），点击 invoke reminders_snooze 气泡即消；点宠物仍 =
 *   确认（两动作并存）。exec 结果气泡无 reminder 载荷，天然不显示按钮。
 * - v2 M6（V2-DESIGN §6.2，TC-M6-03-4）：条目携带 agent 时渲染前置等宽
 *   徽标 `[oc] `/`[cc] `/`[task] `（技术名不翻译；缺省不渲染——提醒气泡
 *   无徽标，回归项）。徽标形态（气泡 [oc]）与 M5 会话列表（无括号 oc 列
 *   徽标）刻意不同，勿顺手统一（P3-2）。
 */
export default function Bubble() {
  const bubble = usePetStore((s) => s.bubble);
  const snooze = usePetStore((s) => s.snoozeReminderBubble);
  const cur = bubble.current;
  if (!cur) return null;
  const showSnooze = cur.level === "critical" && cur.reminder != null;
  const badge = bubbleAgentBadge(cur.agent);
  return (
    <div
      className={`pet-bubble level-${cur.level}${showSnooze ? " snoozable" : ""}`}
      role="status"
      key={cur.id}
    >
      {badge && <span className="pet-bubble-agent">[{badge}]</span>}
      {cur.text}
      {showSnooze && (
        <button
          type="button"
          className="pet-bubble-snooze"
          title={t("tasks.snooze")}
          aria-label={t("tasks.snooze")}
          onClick={(e) => {
            e.stopPropagation(); // 不触碰 canvas 点击语义（点宠物仍 = 确认）
            snooze();
          }}
        >
          ⏱ 10min
        </button>
      )}
    </div>
  );
}
