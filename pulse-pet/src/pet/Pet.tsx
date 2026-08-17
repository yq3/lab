import PetCanvas from "./PetCanvas";
import Bubble from "./Bubble";
import PetMenu from "./PetMenu";

export default function Pet() {
  return (
    <div className="pet-root">
      <Bubble />
      <PetCanvas />
      {/* M6 右键菜单（TC-WIN-03）：穿透态下不会打开（store 双保险） */}
      <PetMenu />
    </div>
  );
}
