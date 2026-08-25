import { usePetStore } from "./petStore";

/**
 * 宠物气泡（v2 M2 排队模型下的显示位，V2-DESIGN §2.6.3）：
 * - 文案经 petStore.pushBubble 净化（单行 1-140）；current 条目按级别 dwell
 *   自动离场（bubble-queue 内核驱动）；
 * - 视觉走「宠物世界」固定色（`--pet-world-*`，不随主题）：暖白底 + 2px
 *   墨边 + 2px 2px 0 硬阴影 + 像素尖角（45° 旋转小方块）；
 * - critical 级左侧 4px 蜜橘色条（可交互暗示——点宠物确认）；单行省略。
 */
export default function Bubble() {
  const bubble = usePetStore((s) => s.bubble);
  const cur = bubble.current;
  if (!cur) return null;
  return (
    <div
      className={`pet-bubble level-${cur.level}`}
      role="status"
      key={cur.id}
    >
      {cur.text}
    </div>
  );
}
