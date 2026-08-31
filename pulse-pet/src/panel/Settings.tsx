import { useCallback, useEffect, useRef, useState } from "react";
import { getVersion } from "@tauri-apps/api/app";
import pkg from "../../package.json";
import {
  fetchPetOptions,
  selectPet,
  type AtlasMeta,
  type PetOption,
} from "../lib/atlas";
import { isTauriRuntime } from "../lib/token-stats";
import { setPassThrough, PANEL_TAB_EVENT, normalizeTab } from "../lib/interaction";
import {
  composeActionNotice,
  fetchIntegrations,
  focusRefreshAllowed,
  installIntegration,
  uninstallIntegration,
  uiStateOf,
  type IntegrationId,
  type IntegrationStatus,
  type IntegrationUiState,
} from "../lib/integrations";
import {
  setThemePreference,
  useThemeStore,
  type ThemePreference,
} from "../lib/theme";
import { setPluginEnabled, usePluginStore } from "../lib/plugin-store";
import { usePetStore } from "../pet/petStore";
import { setPetSize, type PetSize } from "../lib/size-bridge";
import { fetchToolBroadcast, setToolBroadcast } from "../lib/tool-bubble-bridge";
import { changeLanguage, t, useLangStore, type Lang } from "../lib/i18n";
import { descKeyOf } from "../lib/agents";

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

/** v2 M1 接入管理：状态点四态 → 文案键（§1.7/§1.8）。 */
const INTG_STATE_KEYS: Record<IntegrationUiState, string> = {
  installed: "integrations.installed",
  notInstalled: "integrations.notInstalled",
  stale: "integrations.stale",
  error: "integrations.error",
};

/** §二十（V2-OPEN-ITEMS）：统计源状态行四态 → 文案键（wire state 字符串
 * 映射；未知值兜底 statsNone——Rust 侧字符串枚举防漂移）。 */
const STATS_STATE_KEYS: Record<string, string> = {
  ok: "integrations.statsOk",
  missing: "integrations.statsMissing",
  failed: "integrations.statsFailed",
  none: "integrations.statsNone",
};

export default function Settings() {
  const [options, setOptions] = useState<PetOption[] | null>(null);
  const [current, setCurrent] = useState<AtlasMeta | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [switching, setSwitching] = useState(false);
  const [passThroughBusy, setPassThroughBusy] = useState(false);
  /** M6 P2 ②（M7 清偿）：穿透失败单独持有——成功时只清它，不动 atlas 错误横幅。 */
  const [passThroughError, setPassThroughError] = useState<string | null>(null);
  const [langBusy, setLangBusy] = useState(false);
  /** v2 M1 接入管理：doctor 快照 + 操作中的接入 id + 每接入操作错误/成功提示。
   * v2 M2 L2（P3-1）：notice 存 Rust 返回的 **status 对象**（渲染时以当前语言
   * 现拼前缀），语言切换时清空——修复「提示条文案在动作时点语言烘焙、切换
   * 语言后旧提示保持旧语言」。 */
  const [intg, setIntg] = useState<IntegrationStatus[] | null>(null);
  const [intgBusy, setIntgBusy] = useState<IntegrationId | null>(null);
  const [intgErrors, setIntgErrors] = useState<Record<string, string>>({});
  const [intgNotices, setIntgNotices] = useState<Record<string, IntegrationStatus>>({});
  /** issue #19：上次任意 doctor 调用时刻——focus 路径刷新的冷却基准
   *（防「探测闪窗 → 重获焦点 → 再探测」自激励循环；mount/tab/操作后
   * 重拉不受限，见 focusRefreshAllowed）。 */
  const lastDoctorAtRef = useRef<number | null>(null);
  const passThrough = usePetStore((s) => s.passThrough);
  const petSize = usePetStore((s) => s.size); // §十一：档位（同一 store 位驱动 pet 窗与设置页）
  const setPetSizeState = usePetStore((s) => s.setSize);
  const lang = useLangStore((s) => s.lang); // M8 i18n：语言变化时本页文案重渲染
  const themePref = useThemeStore((s) => s.preference); // v2 M2 外观
  const plugins = usePluginStore((s) => s.plugins); // v2 M2 功能管理
  const [themeError, setThemeError] = useState<string | null>(null);
  const [pluginBusy, setPluginBusy] = useState<string | null>(null);
  /** v2 M3（§3.7.2）：工具播报开关（初始显示值经 get 初始化，N13）。 */
  const [toolBroadcast, setToolBroadcastState] = useState<boolean>(true);
  const [toolBroadcastBusy, setToolBroadcastBusy] = useState(false);
  const [toolBroadcastError, setToolBroadcastError] = useState<string | null>(null);
  /** §十一：档位切换 busy / 行级错误（与语言切换同款乐观更新 + 回滚模式）。 */
  const [sizeBusy, setSizeBusy] = useState(false);
  const [sizeError, setSizeError] = useState<string | null>(null);
  /** §十九（2026-08-29）：设置页底部版本信息——初值取 package.json（版本四件套
   * lockstep 同步），Tauri 运行时以 getVersion() 刷新（权威源 = tauri.conf.json，
   * 即真实打包版本）；非 Tauri 预览/取值失败保持 package.json 回退值。 */
  const [appVersion, setAppVersion] = useState<string>(pkg.version);
  useEffect(() => {
    if (!isTauriRuntime()) return;
    getVersion()
      .then(setAppVersion)
      .catch(() => {});
  }, []);

  // L2：语言切换 → 旧语言的 notice（Rust message 无法前端重算）整组清除
  useEffect(() => {
    setIntgNotices({});
  }, [lang]);

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

  /** v2 M1 接入管理刷新（§1.7：进入设置页 + tauri://focus 双触发，doctor
   * message 组装在 Rust 侧随语言变化，故切语言后同样重拉）。 */
  const loadIntegrations = useCallback(async () => {
    if (!isTauriRuntime()) return;
    lastDoctorAtRef.current = Date.now();
    try {
      const list = await fetchIntegrations();
      setIntg(list);
    } catch (e) {
      // doctor 拉取失败：保持已有快照，行级错误提示
      setIntgErrors((prev) => ({
        ...prev,
        __load: e instanceof Error ? e.message : String(e),
      }));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  // v2 M3（N13）：工具播报开关初始显示值经 get 初始化（Rust app_state 为权威）
  useEffect(() => {
    if (!isTauriRuntime()) return;
    fetchToolBroadcast()
      .then(setToolBroadcastState)
      .catch((e) => console.error("[pulsepet] tool broadcast init failed:", e));
  }, []);

  // 接入管理刷新：挂载 + 语言切换（doctor message 在 Rust 侧随语言组装）。
  // focus/tab 双触发见下方自动刷新 effect（与 load 同一触发源）。
  useEffect(() => {
    void loadIntegrations();
  }, [loadIntegrations, lang]);

  /**
   * v0.1.3 四-1（TC-APP-14）：宠物下拉自动刷新。面板窗口为隐藏/显示复用，
   * 停在「设置」tab 时重新打开面板不会重挂载组件 → 下拉看不到新导入素材。
   * 双触发重新 load()：
   * - `tauri://focus`（onFocusChanged）：面板重新可见（重开必触发）；
   * - `panel://tab`（目标=settings）：宠物右键菜单「设置…」直达时。
   * 使 README「放好即出现」承诺无条件成立（不再需要切 tab 强制重挂载）。
   */
  useEffect(() => {
    if (!isTauriRuntime()) return;
    const unlisteners: Array<() => void> = [];
    void (async () => {
      try {
        const { listen } = await import("@tauri-apps/api/event");
        const { getCurrentWindow } = await import("@tauri-apps/api/window");
        unlisteners.push(
          await getCurrentWindow().onFocusChanged(({ payload: focused }) => {
            if (focused) {
              void load();
              // issue #19：focus 路径受冷却约束——3s 内已有 doctor 调用则跳过，
              // 掐断「node 探测闪窗 → 重获焦点 → 再探测」的自激励循环
              if (focusRefreshAllowed(lastDoctorAtRef.current, Date.now())) {
                void loadIntegrations();
              }
            }
          }),
        );
        unlisteners.push(
          await listen(PANEL_TAB_EVENT, (event) => {
            if (normalizeTab((event.payload as { tab?: unknown })?.tab) === "settings") {
              void load();
              void loadIntegrations();
            }
          }),
        );
      } catch (e) {
        console.error("[pulsepet] settings auto-refresh listener failed:", e);
      }
    })();
    return () => unlisteners.forEach((u) => u());
  }, [load, loadIntegrations]);

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

  /** M8：语言切换（本地立即生效 + Rust 持久化 + 托盘/标题/三窗口同步）。
   * P3-1（R1 审查）：invoke 失败回滚本地 store（与 A4"写失败不静默"一致）——
   * 失败时 Rust 侧未持久化/未广播，panel 若保持新语言会与 pet/fireworks
   * 及重启后的旧语言不一致。 */
  const onLanguage = async (next: Lang) => {
    if (next === lang) return;
    setLangBusy(true);
    const prev = lang;
    try {
      await changeLanguage(next);
    } catch (e) {
      console.error("[pulsepet] change language failed:", e);
      useLangStore.getState().setLang(prev); // 回滚
      // v0.1.3 三-1：语言切换失败不再复用穿透语义的 settings.passFail
      setError(t("settings.languageFail", { msg: e instanceof Error ? e.message : String(e) }));
    } finally {
      setLangBusy(false);
    }
  };

  /**
   * §十一：大小三档切换——本地乐观更新（pet 窗经 Rust `pet://size` 广播同步
   * 同一值），invoke 失败回滚（Rust 侧未持久化/未广播，panel 若保持新档位
   * 会与 pet 窗及重启后的旧档位不一致——照 onLanguage 回滚口径）。
   */
  const onSize = async (next: PetSize) => {
    if (next === petSize || sizeBusy) return;
    setSizeBusy(true);
    setSizeError(null);
    const prev = petSize;
    setPetSizeState(next);
    try {
      await setPetSize(next);
    } catch (e) {
      setPetSizeState(prev); // 回滚
      setSizeError(t("settings.sizeFail", { msg: e instanceof Error ? e.message : String(e) }));
    } finally {
      setSizeBusy(false);
    }
  };

  /** v2 M1 接入管理动作（安装/重装/卸载）：完成后刷新 doctor；结果双向可见——
   * 失败行级错误条（intgErrors）；成功行级提示条（intgNotices，存 status
   * 对象、渲染时以当前语言现拼——L2 修复，TC-INT-07-5 / tester P2-1）。 */
  const onIntegrationAction = async (id: IntegrationId, action: "install" | "uninstall") => {
    setIntgBusy(id);
    // 新操作清掉该行旧结果（错误与提示都属上一动作）
    setIntgErrors((prev) => {
      const next = { ...prev };
      delete next[id];
      return next;
    });
    setIntgNotices((prev) => {
      const next = { ...prev };
      delete next[id];
      return next;
    });
    try {
      const status = action === "install"
        ? await installIntegration(id)
        : await uninstallIntegration(id);
      if (composeActionNotice(t("integrations.actionDone"), status)) {
        setIntgNotices((prev) => ({ ...prev, [id]: status }));
      }
    } catch (e) {
      setIntgErrors((prev) => ({
        ...prev,
        [id]: t("integrations.fail", { msg: e instanceof Error ? e.message : String(e) }),
      }));
    } finally {
      setIntgBusy(null);
      await loadIntegrations();
    }
  };

  /** v2 M2 外观：主题三档切换（本地立即生效 + Rust 持久化 + ui://theme 广播；
   * 失败回滚由 setThemePreference 内处理并抛出——此处展示错误）。 */
  const onTheme = async (next: ThemePreference) => {
    if (next === themePref) return;
    setThemeError(null);
    try {
      await setThemePreference(next);
    } catch (e) {
      setThemeError(
        t("settings.themeFail", { msg: e instanceof Error ? e.message : String(e) }),
      );
    }
  };

  /** v2 M3（§3.7.2）：工具播报开关——set 持久化 + Rust 定向 pet 窗广播（即时
   * 静默/恢复无需重启）；本地乐观更新，失败回滚并提示。 */
  const onToolBroadcast = async (enabled: boolean) => {
    setToolBroadcastBusy(true);
    setToolBroadcastError(null);
    try {
      await setToolBroadcast(enabled);
      setToolBroadcastState(enabled);
    } catch (e) {
      setToolBroadcastError(
        t("settings.toolBroadcastFail", {
          msg: e instanceof Error ? e.message : String(e),
        }),
      );
    } finally {
      setToolBroadcastBusy(false);
    }
  };

  /** v2 M2 功能管理：插件开关（Rust 写列 + 调度器 reload；本 store 重拉驱动
   * tab 栏/徽标联动）。 */
  const onPluginToggle = async (id: string, enabled: boolean) => {
    setPluginBusy(id);
    try {
      await setPluginEnabled(id, enabled);
    } catch (e) {
      console.error("[pulsepet] set plugin enabled failed:", e);
    } finally {
      setPluginBusy(null);
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

      {/* 回退提示（TC-SP-05/09/11③）：当前加载与用户选择不一致时说明原因。
          §十二 二轮微调（2026-08-28）：「当前渲染」信息行移除（settings.current/
          fellBack 键清退）——回退可见性由本 notice 横幅 + 下拉 requestedMissing
          占位项承担 */}
      {current?.notice && <p className="settings-notice">⚠️ {current.notice}</p>}

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

      {/* §十一（V2-OPEN-ITEMS）：大小三档；§十二 F6（2026-08-28）：分段控件改
          下拉（照语言/宠物选择形态）；切换即时生效 + 重启保留；184/220/280
          逻辑像素，内置猫锚定中档 */}
      {sizeError && <p className="settings-error">⚠️ {sizeError}</p>}
      <label className="settings-pet-label" htmlFor="size-select">
        {t("settings.size")}
      </label>
      <select
        id="size-select"
        value={petSize}
        disabled={sizeBusy || !isTauriRuntime()}
        onChange={(e) => void onSize(e.target.value as PetSize)}
      >
        {(["small", "medium", "large"] as PetSize[]).map((v) => (
          <option key={v} value={v}>
            {t(
              v === "small"
                ? "settings.sizeSmall"
                : v === "medium"
                  ? "settings.sizeMedium"
                  : "settings.sizeLarge",
            )}
          </option>
        ))}
      </select>

      {/* §十二 F6（2026-08-28）：交互与工具播报合并一区（原两个 h2 区），
          照功能管理 todo 插件卡片行形态（intg-row + 右侧开关带已启用/已停用） */}
      <h2>{t("settings.sectionInteraction")}</h2>
      {passThroughError && <p className="settings-error">⚠️ {passThroughError}</p>}
      {toolBroadcastError && <p className="settings-error">⚠️ {toolBroadcastError}</p>}
      <div className="intg-list">
        {/* 二轮续（2026-08-28）：粗体名独占一行 + 描述另起一行（原同行横排改两行） */}
        <div className="intg-row plugin-row">
          <div className="intg-row-head">
            <span className="intg-name">{t("settings.passThrough")}</span>
            <span className="intg-row-actions">
              <label
                className="reminder-check compact"
                title={passThrough ? t("reminders.enabledOn") : t("reminders.enabledOff")}
              >
                <input
                  type="checkbox"
                  checked={passThrough}
                  disabled={passThroughBusy || !isTauriRuntime()}
                  onChange={(e) => void onPassThrough(e.target.checked)}
                />
                {passThrough ? t("todo.plugin.enabled") : t("todo.plugin.disabled")}
              </label>
            </span>
          </div>
          <p className="intg-desc">{t("settings.passThroughDesc")}</p>
        </div>
        <div className="intg-row plugin-row">
          <div className="intg-row-head">
            <span className="intg-name">{t("settings.toolBroadcast")}</span>
            <span className="intg-row-actions">
              <label
                className="reminder-check compact"
                title={toolBroadcast ? t("reminders.enabledOn") : t("reminders.enabledOff")}
              >
                <input
                  type="checkbox"
                  checked={toolBroadcast}
                  disabled={toolBroadcastBusy || !isTauriRuntime()}
                  onChange={(e) => void onToolBroadcast(e.target.checked)}
                />
                {toolBroadcast ? t("todo.plugin.enabled") : t("todo.plugin.disabled")}
              </label>
            </span>
          </div>
          <p className="intg-desc">{t("settings.toolBroadcastDesc")}</p>
        </div>
      </div>
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

      {/* v2 M2：外观（主题三档；§十二 F6：改下拉；二轮微调 2026-08-28：删
          「界面主题」label，themeHint 小字上移至 label 位）；panel 窗专属，TC-UI-01 */}
      <h2>{t("settings.theme")}</h2>
      {themeError && <p className="settings-error">⚠️ {themeError}</p>}
      {/* 二轮微调：hint 上移替代 label 位；审查 P3-8：转 <label> 关联 select（a11y）。
          三轮回归修复：label 样式类改 settings-pet-label（与其他下拉标签同族
          ——ink-soft 12px；原误挂 settings-current 脚注级 ink-faint 导致同字号
          不同灰）；settings-current 回归纯脚注（热键/管理提示/备份提示） */}
      <label className="settings-pet-label" htmlFor="theme-select">
        {t("settings.themeHint")}
      </label>
      <select
        id="theme-select"
        value={themePref}
        onChange={(e) => void onTheme(e.target.value as ThemePreference)}
      >
        {(["auto", "light", "dark"] as ThemePreference[]).map((v) => (
          <option key={v} value={v}>
            {t(
              v === "auto"
                ? "settings.themeAuto"
                : v === "light"
                  ? "settings.themeLight"
                  : "settings.themeDark",
            )}
          </option>
        ))}
      </select>

      {/* v2 M2：功能管理（插件启停 = feature flag，TC-UI-07）；核心三 tab 不在列 */}
      <h2>{t("plugins.manage")}</h2>
      <p className="settings-current">{t("plugins.manageHint")}</p>
      <div className="intg-list">
        {(plugins ?? []).map((p) => (
          <div className="intg-row plugin-row" key={p.id}>
            <div className="intg-row-head">
              <span className="intg-name">{p.name}</span>
              <span className="intg-state-label">v{p.version}</span>
              <span className="intg-row-actions">
                <label
                  className="reminder-check compact"
                  title={t("plugins.manageToggle", { name: p.name })}
                >
                  <input
                    type="checkbox"
                    checked={p.enabled}
                    disabled={pluginBusy === p.id}
                    onChange={(e) => void onPluginToggle(p.id, e.target.checked)}
                  />
                  {p.enabled ? t("todo.plugin.enabled") : t("todo.plugin.disabled")}
                </label>
              </span>
            </div>
          </div>
        ))}
      </div>

      {/* v2 M1：接入管理（V2-DESIGN §1.7，TC-INT-09） */}
      <h2>{t("integrations.title")}</h2>
      {intgErrors.__load && <p className="settings-error">⚠️ {intgErrors.__load}</p>}
      <div className="intg-list">
        {(intg ?? []).map((s) => {
          const ui = uiStateOf(s);
          const busy = intgBusy === s.id;
          // v2 registry（§6.2）：nameKey 三元 → descKeyOf 查表；未知 id
          // 原名兜底（原三元 else→claudeDesc 会给第三卡显示错名，§4 #10）
          const nameKey = descKeyOf(s.id);
          // P3-6（task-pulsepet-v2-polish #2）：单次计算——此前条件判断与渲染
          // 各调一次 composeActionNotice，重复拼串
          const actionNotice =
            intgNotices[s.id] &&
            composeActionNotice(t("integrations.actionDone"), intgNotices[s.id]);
          return (
            <div className="intg-row" key={s.id}>
              <div className="intg-row-head">
                <span className={ui === "notInstalled" ? "intg-dot" : `intg-dot intg-dot-${ui}`} />
                <span className="intg-name">{nameKey ? t(nameKey) : s.id}</span>
                <span className="intg-state-label">
                  {t(INTG_STATE_KEYS[ui])} · v{s.version}
                </span>
                <span className="intg-row-actions">
                  {busy && <span className="intg-spinner" aria-label={t("integrations.installing")} />}
                  {ui === "notInstalled" && (
                    <button disabled={busy || !isTauriRuntime()} onClick={() => void onIntegrationAction(s.id as IntegrationId, "install")}>
                      {t("integrations.install")}
                    </button>
                  )}
                  {(ui === "stale" || ui === "error") && (
                    <button disabled={busy || !isTauriRuntime()} onClick={() => void onIntegrationAction(s.id as IntegrationId, "install")}>
                      {t("integrations.reinstall")}
                    </button>
                  )}
                  {(ui === "installed" || ui === "stale") && (
                    <button disabled={busy || !isTauriRuntime()} onClick={() => void onIntegrationAction(s.id as IntegrationId, "uninstall")}>
                      {t("integrations.uninstall")}
                    </button>
                  )}
                </span>
              </div>
              <p className="intg-path">{s.configPath}</p>
              <p className="intg-message">{s.message}</p>
              {/* §二十（V2-OPEN-ITEMS）：统计源状态行——统计链被动发现式读取的
                  三态呈现（正常 / 未检测到数据 / 异常 / 无统计源）；hover title =
                  路径 + Missing 原因 / Failed 错误摘要（Rust stats_status_of 组装）。
                  与 Token 页 sourceNote 脚注互为闭环。 */}
              <p
                className="intg-message"
                title={[s.stats?.path, s.stats?.detail].filter(Boolean).join(" · ") || undefined}
              >
                {t("integrations.statsRow", {
                  state: t(STATS_STATE_KEYS[s.stats?.state ?? "none"] ?? "integrations.statsNone"),
                })}
              </p>
              {actionNotice && (
                <p className="intg-row-notice">✅ {actionNotice}</p>
              )}
              {intgErrors[s.id] && <p className="intg-row-error">⚠️ {intgErrors[s.id]}</p>}
            </div>
          );
        })}
      </div>
      {/* §十八（2026-08-29 用户问询，三轮改版）：接入列表下方"接入说明"三行
          编号脚注（备份 / 会话生效时机 / 卸载顺序）——插件装在用户配置目录，
          App 卸载不会自动清理；opencode/CC 均在会话进程启动时加载插件，
          卸载后已运行中的会话保持原样（README 卸载插件节同款提示） */}
      <p className="settings-current settings-notes">{t("integrations.notes")}</p>

      {/* §十九（2026-08-29）：设置页最底部版本信息——与其他区块同款分节形态
          （h2 标题 + settings-current 小字），版本源见 appVersion 注释 */}
      <h2>{t("settings.versionTitle")}</h2>
      <p className="settings-current">{appVersion}</p>
    </section>
  );
}
