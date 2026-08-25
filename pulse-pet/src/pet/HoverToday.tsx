import { useEffect, useRef, useState } from "react";
import { usePetStore } from "./petStore";
import { useLangStore, t } from "../lib/i18n";
import { formatTokens, type TodayStats } from "../lib/token-stats";
import { fetchTodayStatsCached } from "./todayToken";

/**
 * v2 M3（§3.4 ②，TC-M3-10）：悬停宠物今日汇总卡。
 *
 * - **500ms 防抖**：`hoverEntered`（PetCanvas pointerenter/leave 写 store）→
 *   定时器到点显示；移开**立即**取消/隐藏（SCOPE §5.10：进入防抖、离开即时）；
 * - 显示期间 `setHoverPaused(true)` 冻结队列推进与当前气泡 dwell；卡片
 *   **视觉替换**气泡位（宠物上方贴顶居中，底层 current 不销毁——z-index 覆盖）；
 * - **与右键菜单互斥（后开者胜）**：菜单打开（contextMenu 非 null）→ 卡片隐藏
 *   且 `setHoverPaused(false)` 解除冻结（N4）；菜单开着时防抖到点不显示；
 * - **穿透切换兜底（N14）**：`passThrough` 变 true（store 位由既有
 *   `pulsepet://pass-through` 广播驱动）→ 取消计时器/隐藏/解除冻结；切回不自动恢复；
 * - 全零数据照常显示 0（诚实呈现）；错误态一行「暂无数据」（i18n）；
 * - 数据经 30s 缓存（`pet/todayToken`，与右键菜单共享）。
 */
export default function HoverToday() {
  // M8 i18n：语言变化时卡片文案重渲染（t() 读 store）
  useLangStore((s) => s.lang);
  const hoverEntered = usePetStore((s) => s.hoverEntered);
  const passThrough = usePetStore((s) => s.passThrough);
  const contextMenu = usePetStore((s) => s.contextMenu);
  const setHoverPaused = usePetStore((s) => s.setHoverPaused);

  const [shown, setShown] = useState(false);
  const [stats, setStats] = useState<TodayStats | null>(null);
  const [error, setError] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearTimer = () => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  };

  /** 隐藏卡片 + 解除冻结（移开/菜单打开/穿透开启共用收尾）。
   * setHoverPaused(false) 幂等——未冻结时 bubble-queue 返回原状态。 */
  const hideAndUnpause = () => {
    clearTimer();
    setShown(false);
    setHoverPaused(false);
  };

  // 进入防抖 500ms；离开立即取消/隐藏（若已显示则解除冻结）
  useEffect(() => {
    if (passThrough || contextMenu) return; // 不可达/互斥态不武装
    if (hoverEntered) {
      clearTimer();
      timerRef.current = setTimeout(() => {
        setShown(true);
        setHoverPaused(true); // 冻结队列推进 + 当前气泡 dwell
        // 显示时拉数据（30s 缓存内零查询）
        fetchTodayStatsCached()
          .then((s) => {
            setStats(s);
            setError(false);
          })
          .catch(() => {
            setStats(null);
            setError(true); // 悬停层显示「暂无数据」，不闪错误码
          });
      }, 500);
    } else {
      hideAndUnpause(); // 离开即时
    }
    return clearTimer;
    // eslint-disable-next-line react-hooks/exhaustive-deps -- setHoverPaused 引用稳定（zustand）；hideAndUnpause 为闭包内联语义
  }, [hoverEntered, passThrough, contextMenu]);

  // N4：右键菜单打开 → 悬停卡隐藏 + 冻结解除（后开者胜）
  useEffect(() => {
    if (contextMenu) hideAndUnpause();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [contextMenu]);

  // N14：穿透开启 → 取消计时器/隐藏/解除冻结（切回不自动恢复）
  useEffect(() => {
    if (passThrough) hideAndUnpause();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [passThrough]);

  if (!shown || passThrough) return null;

  const total = stats ? stats.input + stats.output + stats.cache_read : 0;
  return (
    <div className="hover-today" role="status">
      {error ? (
        // 错误态一行「暂无数据」（i18n；不闪错误码）
        <span className="hover-today-error">{t("token.todayUnavailable")}</span>
      ) : stats ? (
        <>
          <div className="hover-today-title">{t("token.preset.today")}</div>
          <div className="hover-today-total">{formatTokens(total)}</div>
          <div className="hover-today-rows">
            <span className="hover-today-row">
              <span>input</span>
              <span>{formatTokens(stats.input)}</span>
            </span>
            <span className="hover-today-row">
              <span>output</span>
              <span>{formatTokens(stats.output)}</span>
            </span>
            <span className="hover-today-row">
              <span>cache read</span>
              <span>{formatTokens(stats.cache_read)}</span>
            </span>
          </div>
        </>
      ) : (
        // 数据加载中：数字位以 … 占位（卡片结构稳定不跳变）
        <>
          <div className="hover-today-title">{t("token.preset.today")}</div>
          <div className="hover-today-total">…</div>
        </>
      )}
    </div>
  );
}
