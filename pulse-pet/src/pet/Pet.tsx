import PetCanvas from "./PetCanvas";
import Bubble from "./Bubble";
import PetMenu from "./PetMenu";
import { usePetStore } from "./petStore";
import { PET_SIZES } from "../lib/size-bridge";

export default function Pet() {
  // §十一（V2-OPEN-ITEMS）：档位 → --pet-size CSS 变量（.pet-root/.pet-canvas
  // 尺寸与气泡 max-width 的 100% 基准；PetCanvas 的 canvas 内联尺寸独立于此）
  const size = usePetStore((s) => s.size);
  const rootStyle = { "--pet-size": `${PET_SIZES[size]}px` } as React.CSSProperties;
  return (
    <div className="pet-root" style={rootStyle}>
      <Bubble />
      <PetCanvas />
      {/* M6 右键菜单（TC-WIN-03）：穿透态下不会打开（store 双保险）。
          v2 M3 主动层悬停卡已按用户 2026-08-25 裁定移除（三层降两层）。 */}
      <PetMenu />
    </div>
  );
}
