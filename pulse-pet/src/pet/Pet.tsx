import PetCanvas from "./PetCanvas";
import Bubble from "./Bubble";

export default function Pet() {
  return (
    <div className="pet-root">
      <Bubble />
      <PetCanvas />
    </div>
  );
}
