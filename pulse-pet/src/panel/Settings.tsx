import { useCallback, useEffect, useState } from "react";
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
  installIntegration,
  uninstallIntegration,
  uiStateOf,
  type IntegrationId,
  type IntegrationStatus,
  type IntegrationUiState,
} from "../lib/integrations";
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

/** v2 M1 接入管理：状态点四态 → 文案键（§1.7/§1.8）。 */
const INTG_STATE_KEYS: Record<IntegrationUiState, string> = {
  installed: "integrations.installed",
  notInstalled: "integrations.notInstalled",
  stale: "integrations.stale",
  error: "integrations.error",
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
  /** v2 M1 接入管理：doctor 快照 + 操作中的接入 id + 每接入操作错误/成功提示。 */
  const [intg, setIntg] = useState<IntegrationStatus[] | null>(null);
  const [intgBusy, setIntgBusy] = useState<IntegrationId | null>(null);
  const [intgErrors, setIntgErrors] = useState<Record<string, string>>({});
  /** tester P2-1（TC-INT-07-5）：操作返回 message 的行内成功提示——claude-code
   * 卸载/重装的「建议新开 CC 会话」提示在 doctor 重拉里没有，必须单独展示；
   * 持续展示至该行下一次操作（提示是可执行建议，不做一闪而过的 toast）。 */
  const [intgNotices, setIntgNotices] = useState<Record<string, string>>({});
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

  /** v2 M1 接入管理刷新（§1.7：进入设置页 + tauri://focus 双触发，doctor
   * message 组装在 Rust 侧随语言变化，故切语言后同样重拉）。 */
  const loadIntegrations = useCallback(async () => {
    if (!isTauriRuntime()) return;
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
              void loadIntegrations();
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

  /** v2 M1 接入管理动作（安装/重装/卸载）：完成后刷新 doctor；结果双向可见——
   * 失败行级错误条（intgErrors）；成功行级提示条（intgNotices，展示 Rust
   * 返回的 message 全文，含 claude-code 卸载的「建议新开 CC 会话」提示，
   * TC-INT-07-5 / tester P2-1）。 */
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
      const notice = composeActionNotice(t("integrations.actionDone"), status);
      if (notice) {
        setIntgNotices((prev) => ({ ...prev, [id]: notice }));
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

      {/* v2 M1：接入管理（V2-DESIGN §1.7，TC-INT-09） */}
      <h2>{t("integrations.title")}</h2>
      {intgErrors.__load && <p className="settings-error">⚠️ {intgErrors.__load}</p>}
      <div className="intg-list">
        {(intg ?? []).map((s) => {
          const ui = uiStateOf(s);
          const busy = intgBusy === s.id;
          const nameKey = s.id === "opencode" ? "integrations.opencodeDesc" : "integrations.claudeDesc";
          return (
            <div className="intg-row" key={s.id}>
              <div className="intg-row-head">
                <span className={ui === "notInstalled" ? "intg-dot" : `intg-dot intg-dot-${ui}`} />
                <span className="intg-name">{t(nameKey)}</span>
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
              {intgNotices[s.id] && (
                <p className="intg-row-notice">✅ {intgNotices[s.id]}</p>
              )}
              {intgErrors[s.id] && <p className="intg-row-error">⚠️ {intgErrors[s.id]}</p>}
              <p className="intg-note">{t("integrations.backupNote")}</p>
            </div>
          );
        })}
      </div>
    </section>
  );
}
