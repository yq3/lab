import { useCallback, useEffect, useState } from "react";
import {
  fetchPetOptions,
  selectPet,
  type AtlasMeta,
  type PetOption,
} from "../lib/atlas";
import { isTauriRuntime } from "../lib/token-stats";
import { setPassThrough } from "../lib/interaction";
import { usePetStore } from "../pet/petStore";
import { changeLanguage, t, useLangStore, type Lang } from "../lib/i18n";

/**
 * 设置页（M5 落地"选择宠物"，DESIGN §6.2 / §10.2，TC-SP-11/12 + TC-APP-12）：
 * - 下拉列出 内置分组（blinking-kitty / wagging-doggy）→ `~/.codex/pets/` 扫描 →
 *   `~/.petdex/pets/` 扫描（与加载顺序一致）；
 * - 切换立即热替换 webview 帧（Rust 加载 + atlas://changed 事件，无需重启）；
 * - 损坏 / 非标准网格项旁有回退提示（Rust 侧逐项校验结果）；
 * - 选择持久化到 app_state `pet.selected`（重启保留；TC-APP-12）。
 *
 * M6 落地"点击穿透"开关（TC-APP-12 / TC-APP-07）：状态权威在 Rust
 * （app_state `pet.pass_through`），热键/托盘切换经 `pulsepet://pass-through`
 * 事件同步到本开关。「自动」= 清除配置（atlas_select(null)），默认加载内置
 * 小猫 blinking-kitty。
 *
 * M8 落地语言切换（DESIGN §10 "国际化 en/zh"）：入口在本页；选择持久化
 * app_state `ui.language`（Rust ui_set_language：全局位 + 托盘菜单重建 +
 * panel 标题 + `ui://language` 三窗口广播）；默认语言跟随系统（无持久化时）。
 */

function sourceLabel(source: string): string {
  if (source === "builtin") return t("settings.source.builtin");
  if (source === "codex") return "~/.codex/pets";
  if (source === "petdex") return "~/.petdex/pets";
  return source;
}

export default function Settings() {
  const [options, setOptions] = useState<PetOption[] | null>(null);
  const [current, setCurrent] = useState<AtlasMeta | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [switching, setSwitching] = useState(false);
  const [passThroughBusy, setPassThroughBusy] = useState(false);
  /** M6 P2 ②（M7 清偿）：穿透失败单独持有——成功时只清它，不动 atlas 错误横幅。 */
  const [passThroughError, setPassThroughError] = useState<string | null>(null);
  const [langBusy, setLangBusy] = useState(false);
  const passThrough = usePetStore((s) => s.passThrough);
  const lang = useLangStore((s) => s.lang); // M8 i18n：语言变化时本页文案重渲染

  const load = useCallback(async () => {
    if (!isTauriRuntime()) {
      setError(t("settings.needApp"));
      return;
    }
    try {
      const { fetchAtlasMeta } = await import("../lib/atlas");
      const [opts, meta] = await Promise.all([fetchPetOptions(), fetchAtlasMeta()]);
      setOptions(opts);
      setCurrent(meta);
      setError(null);
    } catch (e) {
      // P2-④（M5 移交，M6 清偿）：读取失败也要渲染错误（此前仅 options 为空时
      // 提前 return，列表加载失败时错误横幅被吞）；已加载的列表保持展示。
      setError(t("settings.loadFail", { msg: e instanceof Error ? e.message : String(e) }));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const onSwitch = async (value: string) => {
    setSwitching(true);
    try {
      const meta = await selectPet(value === "" ? null : value);
      setCurrent(meta);
      setError(null);
      await load();
    } catch (e) {
      setError(t("settings.switchFail", { msg: e instanceof Error ? e.message : String(e) }));
    } finally {
      setSwitching(false);
    }
  };

  const onPassThrough = async (enabled: boolean) => {
    setPassThroughBusy(true);
    try {
      await setPassThrough(enabled); // Rust 应用窗口 + 持久化 + 广播事件同步本开关
      // M6 P2 ②（M7 清偿）：只清穿透相关错误；atlas 横幅（error）保持原样
      setPassThroughError(null);
    } catch (e) {
      setPassThroughError(
        t("settings.passFail", { msg: e instanceof Error ? e.message : String(e) }),
      );
    } finally {
      setPassThroughBusy(false);
    }
  };

  /** M8：语言切换（本地立即生效 + Rust 持久化 + 托盘/标题/三窗口同步）。 */
  const onLanguage = async (next: Lang) => {
    if (next === lang) return;
    setLangBusy(true);
    try {
      await changeLanguage(next);
    } catch (e) {
      console.error("[pulsepet] change language failed:", e);
    } finally {
      setLangBusy(false);
    }
  };

  // 下拉选中值：用户配置 pet（requested）；未配置 = 自动
  const selectedValue = current?.requested ?? "";
  // P2-④（M5 移交，M6 清偿）：requested 指向的项不在可选列表（如目录被删）
  // 时，补一个显式的 disabled 占位 option，避免 select value 落在不存在的
  // option 上（浏览器会静默显示第一项，造成"值与显示不一致"）。
  const requestedMissing =
    selectedValue !== "" && options !== null && !options.some((o) => o.id === selectedValue);

  return (
    <section className="panel-settings">
      {error && <p className="settings-error">⚠️ {error}</p>}
      <h2>{t("settings.pet")}</h2>
      <label className="settings-pet-label" htmlFor="pet-select">
        {t("settings.petLabel")}
      </label>
      <select
        id="pet-select"
        value={selectedValue}
        disabled={switching || !options}
        onChange={(e) => void onSwitch(e.target.value)}
      >
        <option value="">{t("settings.autoOption")}</option>
        {requestedMissing && (
          <option value={selectedValue} disabled>
            {t("settings.missingOption", { id: selectedValue })}
          </option>
        )}
        {options?.map((o) => (
          <option key={`${o.source}:${o.id}`} value={o.id} disabled={!o.ok}>
            {o.displayName}（{sourceLabel(o.source)}）
            {o.ok ? "" : t("settings.brokenOption")}
          </option>
        ))}
      </select>

      {/* 回退提示（TC-SP-05/09/11③）：当前加载与用户选择不一致时说明原因 */}
      {current?.notice && <p className="settings-notice">⚠️ {current.notice}</p>}
      {current && (
        <p className="settings-current">
          {t("settings.current", {
            id: current.currentId,
            source: sourceLabel(current.currentSource),
            cols: current.cols,
            rows: current.rows,
            fw: current.frameW,
            fh: current.frameH,
          })}
          {current.requested && current.requested !== current.currentId && (
            <>{t("settings.fellBack", { id: current.requested })}</>
          )}
        </p>
      )}

      {/* 损坏 / 非标准素材明细（下拉项旁的回退提示，TC-SP-11③） */}
      {options?.some((o) => !o.ok) && (
        <ul className="settings-problems">
          {options
            .filter((o) => !o.ok)
            .map((o) => (
              <li key={`p:${o.source}:${o.id}`}>{o.problem}</li>
            ))}
        </ul>
      )}

      <h2>{t("settings.interaction")}</h2>
      {/* M6 P2 ②：穿透错误独立展示（不再借用全局 error 位，避免连带清 atlas 横幅） */}
      {passThroughError && <p className="settings-error">⚠️ {passThroughError}</p>}
      <label className="settings-check">
        <input
          type="checkbox"
          checked={passThrough}
          disabled={passThroughBusy || !isTauriRuntime()}
          onChange={(e) => void onPassThrough(e.target.checked)}
        />
        <span>{t("settings.passThrough")}</span>
      </label>
      <p className="settings-hotkey-hint">
        {t("settings.hotkeys")}
        {import.meta.env.DEV ? t("settings.hotkeys.debug") : ""}
      </p>

      {/* M8：语言切换（v1 双语 zh/en） */}
      <h2>{t("settings.language")}</h2>
      <label className="settings-pet-label" htmlFor="lang-select">
        {t("settings.languageHint")}
      </label>
      <select
        id="lang-select"
        value={lang}
        disabled={langBusy}
        onChange={(e) => void onLanguage(e.target.value as Lang)}
      >
        <option value="zh">{t("settings.languageZh")}</option>
        <option value="en">{t("settings.languageEn")}</option>
      </select>
    </section>
  );
}
