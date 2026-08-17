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
 */

const SOURCE_LABELS: Record<string, string> = {
  builtin: "内置",
  codex: "~/.codex/pets",
  petdex: "~/.petdex/pets",
};

export default function Settings() {
  const [options, setOptions] = useState<PetOption[] | null>(null);
  const [current, setCurrent] = useState<AtlasMeta | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [switching, setSwitching] = useState(false);
  const [passThroughBusy, setPassThroughBusy] = useState(false);
  const passThrough = usePetStore((s) => s.passThrough);

  const load = useCallback(async () => {
    if (!isTauriRuntime()) {
      setError("设置需要在 PulsePet App（Tauri）内使用");
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
      setError(`读取宠物列表失败：${e instanceof Error ? e.message : String(e)}`);
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
      setError(`切换宠物失败：${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setSwitching(false);
    }
  };

  const onPassThrough = async (enabled: boolean) => {
    setPassThroughBusy(true);
    try {
      await setPassThrough(enabled); // Rust 应用窗口 + 持久化 + 广播事件同步本开关
      setError(null);
    } catch (e) {
      setError(`切换穿透失败：${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setPassThroughBusy(false);
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
      <h2>宠物</h2>
      <label className="settings-pet-label" htmlFor="pet-select">
        选择宠物（切换立即生效；重启保留）
      </label>
      <select
        id="pet-select"
        value={selectedValue}
        disabled={switching || !options}
        onChange={(e) => void onSwitch(e.target.value)}
      >
        <option value="">自动（默认 blinking-kitty）</option>
        {requestedMissing && (
          <option value={selectedValue} disabled>
            {selectedValue} — 素材损坏或不存在，已回退
          </option>
        )}
        {options?.map((o) => (
          <option key={`${o.source}:${o.id}`} value={o.id} disabled={!o.ok}>
            {o.displayName}（{SOURCE_LABELS[o.source] ?? o.source}）
            {o.ok ? "" : " — 素材损坏/非标准，不可选"}
          </option>
        ))}
      </select>

      {/* 回退提示（TC-SP-05/09/11③）：当前加载与用户选择不一致时说明原因 */}
      {current?.notice && <p className="settings-notice">⚠️ {current.notice}</p>}
      {current && (
        <p className="settings-current">
          当前渲染：{current.currentId}（来源 {SOURCE_LABELS[current.currentSource] ?? current.currentSource}，
          {current.cols}×{current.rows} 网格，单帧 {current.frameW}×{current.frameH}）
          {current.requested && current.requested !== current.currentId && (
            <>，已从「{current.requested}」回退</>
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

      <h2>交互</h2>
      <label className="settings-check">
        <input
          type="checkbox"
          checked={passThrough}
          disabled={passThroughBusy || !isTauriRuntime()}
          onChange={(e) => void onPassThrough(e.target.checked)}
        />
        <span>
          点击穿透（纯展示模式）：开启后鼠标事件透出——宠物不可拖拽、右键菜单不可达，
          动画照常播放；可经全局热键 ⌘/Ctrl+Shift+Alt+P 或托盘菜单「切换交互模式」切回。
        </span>
      </label>
      <p className="settings-hotkey-hint">
        全局热键：⌘/Ctrl+Shift+P 唤起/隐藏面板；⌘/Ctrl+Shift+Alt+P 切换穿透；
        {import.meta.env.DEV ? " ⌘/Ctrl+Shift+Alt+F 调试烟花（仅开发构建）。" : ""}
      </p>
    </section>
  );
}
