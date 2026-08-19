import { useEffect, useRef, useState } from "react";
import { usePetStore } from "./petStore";
import { buildPetMenuItems, clampMenuPosition } from "../lib/pet-menu";
import { openPanel, setPassThrough, togglePetVisible } from "../lib/interaction";
import { useLangStore } from "../lib/i18n";

/**
 * M6 宠物右键菜单（TC-WIN-03）：非穿透态右键宠物弹出。
 *
 * - 菜单项见 `lib/pet-menu.ts`（设置… / 切换交互模式（穿透：开/关）/ 隐藏宠物）；
 * - 窗口仅 220×220 → 菜单 clamp 在窗口内（挂载后按实际尺寸重算）；
 * - 点击菜单项执行动作并关闭；点击外部 / 窗口失焦 / Escape 关闭；
 * - 穿透态下 contextmenu 事件透出，本组件根本不会被打开（TC-WIN-04）；
 * - M8 i18n：菜单项文案随语言（订阅 useLangStore）。
 */
export default function PetMenu() {
  const pos = usePetStore((s) => s.contextMenu);
  const passThrough = usePetStore((s) => s.passThrough);
  const close = usePetStore((s) => s.closeContextMenu);
  useLangStore((s) => s.lang); // M8 i18n：语言变化时菜单项文案重渲染

  const ref = useRef<HTMLDivElement>(null);
  // 首帧用估算尺寸 clamp，挂载测量后按实际尺寸重算
  const [style, setStyle] = useState(() =>
    pos ? clampMenuPosition(pos.x, pos.y, 220, 176, 104) : { x: 0, y: 0 },
  );

  useEffect(() => {
    if (!pos || !ref.current) return;
    const el = ref.current;
    setStyle(
      clampMenuPosition(
        pos.x,
        pos.y,
        220,
        el.offsetWidth || 176,
        el.offsetHeight || 104,
      ),
    );
  }, [pos]);

  useEffect(() => {
    // R3 P1：pointerdown 走**冒泡**阶段（不传 capture）——React root 在 #root、
    // document 之下，canvas 的 React onPointerDown 先执行并快照菜单开态，
    // 本 handler 随后才关菜单；capture 会把快照读成 null，导致"点画布关菜单"
    // 误轮换一次宠物状态（committer R1 P1）。
    const onDown = (e: PointerEvent) => {
      if (ref.current && e.target instanceof Node && !ref.current.contains(e.target)) {
        close();
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    const onBlur = () => close();
    document.addEventListener("pointerdown", onDown);
    document.addEventListener("keydown", onKey);
    window.addEventListener("blur", onBlur);
    return () => {
      document.removeEventListener("pointerdown", onDown);
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("blur", onBlur);
    };
  }, [close]);

  if (!pos || passThrough) return null;

  const act = (id: string) => {
    close();
    void (async () => {
      try {
        if (id === "settings") {
          await openPanel("settings");
        } else if (id === "toggle-pass-through") {
          await setPassThrough(!passThrough);
        } else if (id === "hide-pet") {
          await togglePetVisible();
        }
      } catch (e) {
        console.error("[pulsepet] pet menu action failed:", e);
      }
    })();
  };

  return (
    <div ref={ref} className="pet-menu" style={{ left: style.x, top: style.y }} role="menu">
      {buildPetMenuItems(passThrough).map((item) => (
        <button
          key={item.id}
          role="menuitem"
          className="pet-menu-item"
          onClick={() => act(item.id)}
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}
