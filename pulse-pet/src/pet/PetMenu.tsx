import { useEffect, useRef, useState } from "react";
import { usePetStore } from "./petStore";
import { buildPetMenuItems, clampMenuPosition } from "../lib/pet-menu";
import { openPanel, setPassThrough, togglePetVisible } from "../lib/interaction";
import { PET_SIZES } from "../lib/size-bridge";
import { t, useLangStore } from "../lib/i18n";
import { fetchTodayStatsCached, todayTokenStateOf } from "./todayToken";
import type { TodayTokenState } from "../lib/pet-menu";

/**
 * M6 宠物右键菜单（TC-WIN-03）：非穿透态右键宠物弹出。
 *
 * - 菜单项见 `lib/pet-menu.ts`（今日 token（v2 M3 入口层）/ 设置… /
 *   切换交互模式（穿透：开/关）/ 隐藏宠物）；
 * - 菜单是窗口内 DOM 浮层，clamp 在窗口可视区内（挂载后按实际尺寸重算；4 项
 *   menuH 估值 104→130，§3.4 ③；v2 打磨轮 #12：实测重算改挂
 *   ResizeObserver，agent 分布子行动态出现/语言切换变高时自适应）；
 * - 点击菜单项执行动作并关闭；点击外部 / 窗口失焦 / Escape 关闭；
 * - 穿透态下 contextmenu 事件透出，本组件根本不会被打开（TC-WIN-04）；
 * - M8 i18n：菜单项文案随语言（订阅 useLangStore）。
 *
 * v2 M3（§3.4 ③）：菜单打开时 invoke `token_stats_today`（30s 缓存，
 * todayToken 模块）→「今日 token」三态信息项；点击 → openPanel("token")
 *（面板默认即今日，无缝衔接详情）。信息项 info 标记 → 分隔线样式。
 *（主动层悬停卡已按用户 2026-08-25 裁定移除——三层降两层，本菜单与面板、
 *  被动层 idle 追加段构成两层快捷查看。）
 */
export default function PetMenu() {
  const pos = usePetStore((s) => s.contextMenu);
  const passThrough = usePetStore((s) => s.passThrough);
  const close = usePetStore((s) => s.closeContextMenu);
  const size = usePetStore((s) => s.size); // §十一：档位 = clamp 的窗口尺寸
  useLangStore((s) => s.lang); // M8 i18n：语言变化时菜单项文案重渲染

  const [todayToken, setTodayToken] = useState<TodayTokenState>({ status: "loading" });

  const ref = useRef<HTMLDivElement>(null);
  const winSize = PET_SIZES[size];
  // 首帧用估算尺寸 clamp，挂载测量后按实际尺寸重算（M3：4 项 menuH 130）
  const [style, setStyle] = useState(() =>
    pos ? clampMenuPosition(pos.x, pos.y, winSize, 176, 130) : { x: 0, y: 0 },
  );

  // v2 打磨轮 #12（P3-①）：clamp 改 ResizeObserver——原 deps 仅 [pos]，首帧
  // 估值 130 不含「今日 token」的 agent 分布子行（双 agent 日菜单增高 ~14px，
  // 贴下缘时底项被裁）；token 数据/语言切换等任何高度变化源都会触发实测
  // 重算（observe 挂上即回调一次，首帧估值随即被实测修正），无需逐一枚举
  // 依赖（对比 deps 加 todayToken 的方案：语言切换变高仍漏）。
  // §十一：窗口尺寸（winSize）入 deps——档位切换时菜单开着也要按新窗口重算。
  useEffect(() => {
    if (!pos || !ref.current) return;
    const el = ref.current;
    const reclamp = () => {
      setStyle(
        clampMenuPosition(
          pos.x,
          pos.y,
          winSize,
          el.offsetWidth || 176,
          el.offsetHeight || 130,
        ),
      );
    };
    reclamp();
    const ro = new ResizeObserver(reclamp);
    ro.observe(el);
    return () => ro.disconnect();
  }, [pos, winSize]);

  // v2 M3：菜单打开即拉今日 token（30s 缓存；错误 → error 态显示 —）
  useEffect(() => {
    if (!pos) return;
    let alive = true;
    setTodayToken({ status: "loading" });
    fetchTodayStatsCached()
      .then((s) => {
        if (alive) setTodayToken(todayTokenStateOf(s));
      })
      .catch(() => {
        if (alive) setTodayToken({ status: "error" });
      });
    return () => {
      alive = false;
    };
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
        if (id === "today-token") {
          // v2 M3 入口层：直达 Token 页（面板默认今日，§3.3）
          await openPanel("token");
        } else if (id === "settings") {
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
      {buildPetMenuItems(passThrough, todayToken).map((item) => (
        <button
          key={item.id}
          role="menuitem"
          className={item.info ? "pet-menu-item pet-menu-info" : "pet-menu-item"}
          onClick={() => act(item.id)}
          title={item.sub ? t("token.hoverAgent") : undefined}
        >
          {item.label}
          {item.sub && <span className="pet-menu-sub">{item.sub}</span>}
        </button>
      ))}
    </div>
  );
}
