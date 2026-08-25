import PetCanvas from "./PetCanvas";
import Bubble from "./Bubble";
import PetMenu from "./PetMenu";
import HoverToday from "./HoverToday";

export default function Pet() {
  return (
    <div className="pet-root">
      {/* 悬停卡（v2 M3 §3.4 ②）：视觉替换气泡位（z-index 覆盖，底层 current 不销毁） */}
      <HoverToday />
      <Bubble />
      <PetCanvas />
      {/* M6 右键菜单（TC-WIN-03）：穿透态下不会打开（store 双保险） */}
      <PetMenu />
    </div>
  );
}
