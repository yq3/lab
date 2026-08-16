import { useCallback, useEffect, useState } from "react";
import {
  fetchPetOptions,
  selectPet,
  type AtlasMeta,
  type PetOption,
} from "../lib/atlas";
import { isTauriRuntime } from "../lib/token-stats";

/**
 * 设置页（M5 落地"选择宠物"，DESIGN §6.2 / §10.2，TC-SP-11 + TC-APP-12）：
 * - 下拉列出 内置占位 → `~/.codex/pets/` 扫描 → `~/.petdex/pets/` 扫描（与加载顺序一致）；
 * - 切换立即热替换 webview 帧（Rust 加载 + atlas://changed 事件，无需重启）；
 * - 损坏 / 非标准网格项旁有回退提示（Rust 侧逐项校验结果）；
 * - 选择持久化到 app_state `pet.selected`（重启保留；TC-APP-12）。
 *
 * 「自动（跟随内置占位）」= 清除配置（atlas_select(null)）。
 * 穿透开关等其余设置为 M6（原占位文案中"烟花全局开关"已于 M4 落地提醒页）。
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
      await load();
    } catch (e) {
      setError(`切换宠物失败：${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setSwitching(false);
    }
  };

  if (error && !options) {
    return <p className="panel-placeholder">{error}</p>;
  }

  // 下拉选中值：用户配置 pet（requested）；未配置 = 自动
  const selectedValue = current?.requested ?? "";

  return (
    <section className="panel-settings">
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
        <option value="">自动（默认内置占位）</option>
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

      <h2>其余设置</h2>
      <p className="panel-placeholder">
        点击穿透 / 全局热键 / 右键菜单 — M6；烟花全局开关已在「提醒」页（M4）。
      </p>
    </section>
  );
}
