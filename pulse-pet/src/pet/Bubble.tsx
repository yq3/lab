import { usePetStore } from "./petStore";

/**
 * 宠物气泡（M3：token 会话汇报"本期用了 Xk input / Yk output / $ Z"；
 * M4 起复用于提醒文案）。文案经 petStore.showBubble 净化（单行 1-140），
 * 8s 自动消失；渲染为单行、超宽省略，不出现任何原始路径/URL/代码片段。
 */
export default function Bubble() {
  const bubble = usePetStore((s) => s.bubble);
  if (!bubble) return null;
  return (
    <div className="pet-bubble" role="status" key={bubble.id}>
      {bubble.text}
    </div>
  );
}
