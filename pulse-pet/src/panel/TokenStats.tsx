import { useCallback, useEffect, useMemo, useState } from "react";
import {
  fetchTokenRows,
  formatCost,
  formatTokens,
  localDateStr,
  localDayEndMs,
  localDayStartMs,
  rangeForPreset,
  sumRows,
  type GroupBy,
  type StatsError,
  type TokenRow,
} from "../lib/token-stats";
import {
  computeModelChips,
  computeStackedBars,
  TOOLTIP_ROW_ORDER,
  type ModelKey,
  type StackedBar,
} from "../lib/token-chart";
import { t, useLangStore } from "../lib/i18n";

/**
 * 时间跨度预设（TC-TK-08：today（v2 M3 §3.3，默认）/ 7d / 30d / 自定义）。
 */
type Preset = "today" | "7d" | "30d" | "custom";

/** 统计维度（TC-TK-07：day/week 驱动时序与汇总；session 维度固定给会话列表）。 */
type Dimension = "day" | "week" | "range";

/** 三段语义 → CSS 类（色值 = M2 --chart-output/input/cache token，§3.5）。 */
const SEG_CLASS: Record<string, string> = {
  output: "stack-seg stack-seg-output",
  input: "stack-seg stack-seg-input",
  cacheRead: "stack-seg stack-seg-cache",
};

/** 图例三项（仅说明不可交互——与模型筛选语义隔离，§3.5）。 */
const LEGEND: { key: "output" | "input" | "cacheRead"; label: string }[] = [
  { key: "output", label: "output" },
  { key: "input", label: "input" },
  { key: "cacheRead", label: "cache read" },
];

/** 错误码 → 用户提示（TC-TK-03/04/13；M8 i18n 随当前语言）。 */
function errorHint(err: StatsError): string {
  switch (err.code) {
    case "no-database":
      return t("token.error.noDatabase");
    case "legacy-storage":
      return t("token.error.legacyStorage");
    case "schema-mismatch":
      // 错误 message 自 Rust 带出（已含"请升级 pulse-pet"提示），前端不重复拼接（M3 P3-⑤）
      return t("token.error.schemaMismatch", { msg: err.message });
    default:
      return t("token.error.query", { msg: err.message });
  }
}

/** 首列标题：title 原样（含 `New session*` 回退行）；NULL → session id 前 8 位。 */
function sessionTitle(s: TokenRow): string {
  if (s.title) return s.title;
  return s.session_id ? s.session_id.slice(0, 8) : "—";
}

/** title 属性 tooltip = 完整标题 + session id + 本地时间（TC-M3-08-2）。 */
function sessionTitleTip(s: TokenRow): string {
  const title = s.title ?? "(no title)";
  return `${title}\n${s.session_id ?? ""}\n${formatTime(s.time_updated)}`;
}

/** 项目列：project_name basename；null → global/unknown 回退标签（前端判定）。 */
function projectName(s: TokenRow): string {
  if (s.project_name) return s.project_name;
  // Rust 侧 "/"（global）与 JOIN 未命中均 → project_name=None；by-session 行
  // 保留 project_id，global 行的 id 恒为字面量 "global"（spike S6 实测）
  return s.project_id === "global"
    ? t("token.project.global")
    : t("token.project.unknown");
}

export default function TokenStats() {
  // M8 i18n：语言变化时本页文案重渲染（projects 等 i18n 标签 useMemo 依赖）
  useLangStore((s) => s.lang);
  const [preset, setPreset] = useState<Preset>("today"); // v2 M3：默认今日（原 7d）
  const [fromStr, setFromStr] = useState(() => localDateStr());
  const [toStr, setToStr] = useState(() => localDateStr());
  const [dimension, setDimension] = useState<Dimension>("day");
  const [rows, setRows] = useState<TokenRow[] | null>(null);
  const [sessions, setSessions] = useState<TokenRow[] | null>(null);
  const [error, setError] = useState<StatsError | null>(null);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);
  /** 模型筛选（作用域仅柱图，SCOPE E；null 键 = 「未知模型」桶）。 */
  const [selectedModels, setSelectedModels] = useState<Set<ModelKey> | null>(null);

  // 跨度计算：预设含当天；自定义从/至均为整天边界（含当天）
  const range = useMemo(() => {
    if (preset === "custom") {
      const fromMs = Math.min(localDayStartMs(fromStr), localDayStartMs(toStr));
      const toMs = Math.max(localDayEndMs(fromStr), localDayEndMs(toStr));
      return { fromMs, toMs };
    }
    return rangeForPreset(preset);
  }, [preset, fromStr, toStr]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      // 时序/汇总维度 + 固定 session 维度（会话列表，TC-TK-09 ④）
      const [dim, sess] = await Promise.all([
        fetchTokenRows(range.fromMs, range.toMs, dimension as GroupBy),
        fetchTokenRows(range.fromMs, range.toMs, "session"),
      ]);
      setRows(dim);
      setSessions(sess);
      setError(null);
    } catch (e) {
      setError(e as StatsError);
      setRows(null);
      setSessions(null);
    } finally {
      setLoading(false);
    }
  }, [range.fromMs, range.toMs, dimension]);

  useEffect(() => {
    void load();
  }, [load]);

  // 数据/维度切换 → 模型筛选重置为全勾（新跨度 chip 集合变化）
  useEffect(() => {
    setSelectedModels(null);
  }, [rows, dimension]);

  const kpi = useMemo(() => sumRows(rows ?? []), [rows]);

  /** 模型 chip 清单（distinct model_id 按总量降序；range 维无筛选区）。 */
  const chips = useMemo(() => computeModelChips(rows ?? []), [rows]);

  const effectiveSelected = useMemo<ReadonlySet<ModelKey>>(
    () => selectedModels ?? new Set(chips.map((c) => c.key)),
    [selectedModels, chips],
  );

  const bars = useMemo(
    () =>
      dimension === "range"
        ? []
        : computeStackedBars(rows ?? [], effectiveSelected, {
            width: 640,
            height: 190,
            pad: 18,
          }),
    [rows, dimension, effectiveSelected],
  );

  const sortedSessions = useMemo(() => {
    if (!sessions) return [] as TokenRow[];
    return [...sessions].sort(
      (a, b) =>
        b.tokens_input + b.tokens_output + b.tokens_cache_read -
        (a.tokens_input + a.tokens_output + a.tokens_cache_read),
    );
  }, [sessions]);

  const toggleModel = (key: ModelKey) => {
    setSelectedModels(symmetricToggle(effectiveSelected, key));
  };

  return (
    <div className="token-stats">
      {/* 控制条：跨度 + 维度 + 刷新（v2 M3：首位「今日」+ 默认今日，§3.3） */}
      <div className="token-controls">
        <div className="token-seg" role="tablist" aria-label={t("token.aria.range")}>
          {(["today", "7d", "30d", "custom"] as Preset[]).map((p) => (
            <button
              key={p}
              className={preset === p ? "seg active" : "seg"}
              onClick={() => setPreset(p)}
            >
              {t(`token.preset.${p}`)}
            </button>
          ))}
        </div>
        {preset === "custom" && (
          <span className="token-dates">
            <input
              type="date"
              value={fromStr}
              max={toStr}
              onChange={(e) => setFromStr(e.target.value)}
              aria-label={t("token.aria.from")}
            />
            ～
            <input
              type="date"
              value={toStr}
              min={fromStr}
              onChange={(e) => setToStr(e.target.value)}
              aria-label={t("token.aria.to")}
            />
          </span>
        )}
        <div className="token-seg" role="tablist" aria-label={t("token.aria.dim")}>
          {(["day", "week", "range"] as Dimension[]).map((d) => (
            <button
              key={d}
              className={dimension === d ? "seg active" : "seg"}
              onClick={() => setDimension(d)}
            >
              {t(`token.dim.${d}`)}
            </button>
          ))}
        </div>
        <button className="seg" onClick={() => void load()} disabled={loading}>
          {loading ? t("token.loading") : t("token.refresh")}
        </button>
      </div>

      {/* 错误态（TC-TK-03/04/13：不崩溃，给出可行动提示） */}
      {error && <div className="token-error">{errorHint(error)}</div>}

      {/* ① KPI 四卡（用户 2026-08-25 裁定修订：总量 / cache read / input /
          output——cost 卡移除，cache read 升独立第二卡，首卡无副行小字；
          cost 数据仍在会话详情中展示） */}
      {rows && (
        <div className="token-kpis">
          <div className="kpi kpi-total">
            <div className="kpi-value">{formatTokens(kpi.total)}</div>
            <div className="kpi-label">{t("token.kpi.total")}</div>
          </div>
          <div className="kpi">
            <div className="kpi-value">{formatTokens(kpi.cacheRead)}</div>
            <div className="kpi-label">cache read</div>
          </div>
          <div className="kpi">
            <div className="kpi-value">{formatTokens(kpi.input)}</div>
            <div className="kpi-label">input tokens</div>
          </div>
          <div className="kpi">
            <div className="kpi-value">{formatTokens(kpi.output)}</div>
            <div className="kpi-label">output tokens</div>
          </div>
        </div>
      )}

      {/* ② 堆叠柱图 + 模型筛选（day/week 维度；range 维无柱图——隐藏柱图与
          筛选区，仅 KPI + 会话列表，§3.5） */}
      {rows && dimension !== "range" && (
        <section className="token-section">
          <h3>
            {t("token.chart.title", {
              dim: dimension === "day" ? t("token.dim.day") : t("token.dim.week"),
            })}
          </h3>

          {/* 筛选 chip 行：可容纳多组筛选的容器（filter-row；M5 时 agent 组作为
              第二组插入同一容器——预留位只落结构，不渲染空组，§3.5/P1-2） */}
          <div className="filter-row">
            <div className="filter-group" role="group" aria-label={t("token.col.model")}>
              {chips.map((c) => (
                <label key={String(c.key)} className="model-chip" title={c.key ?? t("token.model.unknown")}>
                  <input
                    type="checkbox"
                    checked={effectiveSelected.has(c.key)}
                    onChange={() => toggleModel(c.key)}
                  />
                  <span className="model-chip-name">{c.key ?? t("token.model.unknown")}</span>
                  <span className="model-chip-total">{formatTokens(c.total)}</span>
                </label>
              ))}
            </div>
          </div>

          {effectiveSelected.size === 0 ? (
            <p className="token-empty">{t("token.chart.noModels")}</p>
          ) : bars.length === 0 ? (
            <p className="token-empty">{t("token.sessions.empty")}</p>
          ) : (
            <StackedBarChart bars={bars} />
          )}

          {/* 图例三项：仅说明不可交互（与模型筛选语义隔离） */}
          <div className="chart-legend" aria-hidden="true">
            {LEGEND.map((l) => (
              <span key={l.key} className="legend-item">
                <span className={`legend-dot legend-${l.key}`} />
                {l.label}
              </span>
            ))}
          </div>
        </section>
      )}

      {/* ③ 会话列表：全宽（v2 M3 砍饼图双栏，§3.6） */}
      {sessions && (
        <section className="token-section">
          <h3>{t("token.sessions.title", { n: sortedSessions.length })}</h3>
          {sortedSessions.length === 0 && (
            <p className="token-empty">{t("token.sessions.empty")}</p>
          )}
          <ul className="token-sessions">
            {sortedSessions.map((s) => {
              const total = s.tokens_input + s.tokens_output + s.tokens_cache_read;
              const open = expanded === s.session_id;
              return (
                <li key={s.session_id}>
                  <button
                    className="session-row"
                    onClick={() => setExpanded(open ? null : s.session_id)}
                  >
                    <span className="session-title" title={sessionTitleTip(s)}>
                      {sessionTitle(s)}
                    </span>
                    <span className="session-project">{projectName(s)}</span>
                    <span className="session-tokens">{formatTokens(total)}</span>
                    <span className="session-cost">{formatCost(s.cost)}</span>
                    <span className="session-caret">{open ? "▾" : "▸"}</span>
                  </button>
                  {open && (
                    <dl className="session-detail">
                      {/* v2 M3：展开详情追加「模型」行（model_id；None → 未知模型） */}
                      <div className="detail-wide">
                        <dt>{t("token.col.model")}</dt>
                        <dd>{s.model_id ?? t("token.model.unknown")}</dd>
                      </div>
                      <div>
                        <dt>input</dt>
                        <dd>{s.tokens_input.toLocaleString()}</dd>
                      </div>
                      <div>
                        <dt>output</dt>
                        <dd>{s.tokens_output.toLocaleString()}</dd>
                      </div>
                      <div>
                        <dt>reasoning</dt>
                        <dd>{s.tokens_reasoning.toLocaleString()}</dd>
                      </div>
                      <div>
                        <dt>cache read</dt>
                        <dd>{s.tokens_cache_read.toLocaleString()}</dd>
                      </div>
                      <div>
                        <dt>cache write</dt>
                        <dd>{s.tokens_cache_write.toLocaleString()}</dd>
                      </div>
                      <div>
                        <dt>cost</dt>
                        <dd>{formatCost(s.cost)}</dd>
                      </div>
                      <div className="detail-wide">
                        <dt>{t("token.sessions.updated")}</dt>
                        <dd>{formatTime(s.time_updated)}</dd>
                      </div>
                    </dl>
                  )}
                </li>
              );
            })}
          </ul>
        </section>
      )}
    </div>
  );
}

/** 勾选切换纯逻辑（不可变更新）。 */
function symmetricToggle(set: ReadonlySet<ModelKey>, key: ModelKey): Set<ModelKey> {
  const next = new Set(set);
  if (next.has(key)) next.delete(key);
  else next.add(key);
  return next;
}

/**
 * 堆叠柱状图（几何来自 computeStackedBars；HTML tooltip = 日期 + 三值 +
 * 占比 + 总量；图例在组件外仅说明）。悬浮 tooltip 用受控 state（非 <title>，
 * §3.5「自定义 HTML tooltip」）。
 */
function StackedBarChart({ bars }: { bars: StackedBar[] }) {
  const W = 640;
  const H = 190;
  const PAD = 18;
  const [tip, setTip] = useState<{ bar: StackedBar; x: number; y: number } | null>(null);
  const max = Math.max(...bars.map((b) => b.total), 0);

  const nameOf: Record<string, string> = {
    output: "output",
    input: "input",
    cacheRead: "cache read",
  };

  return (
    <div className="stack-chart-wrap">
      <svg
        className="token-chart"
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label={t("token.chart.aria")}
      >
        <line
          className="chart-axis"
          x1={PAD}
          y1={H - PAD}
          x2={W - PAD}
          y2={H - PAD}
          strokeWidth="1"
        />
        {bars.map((b) => (
          <g
            key={b.label}
            onMouseEnter={() => setTip({ bar: b, x: b.x + b.w / 2, y: b.segs[2].y })}
            onMouseLeave={() => setTip(null)}
          >
            {b.segs.map((s) => (
              <rect
                key={s.key}
                className={SEG_CLASS[s.key]}
                x={b.x}
                y={s.y}
                width={b.w}
                height={s.h}
              />
            ))}
          </g>
        ))}
        {/* 首尾标签 */}
        {bars.length > 0 && (
          <text className="chart-label" x={PAD} y={H - 4} fontSize="10">
            {bars[0].label}
          </text>
        )}
        {bars.length > 1 && (
          <text
            className="chart-label"
            x={W - PAD}
            y={H - 4}
            fontSize="10"
            textAnchor="end"
          >
            {bars[bars.length - 1].label}
          </text>
        )}
        {max > 0 && (
          <text className="chart-label faint" x={PAD} y={PAD - 4} fontSize="10">
            {formatTokens(max)}
          </text>
        )}
      </svg>
      {tip && (
        <div
          className="chart-tip"
          style={{
            left: `${Math.min(Math.max((tip.x / W) * 100, 8), 92)}%`,
            top: `${Math.max((tip.y / H) * 100 - 4, 2)}%`,
          }}
        >
          <div className="chart-tip-title">
            {t("token.chart.tip", { label: tip.bar.label, total: formatTokens(tip.bar.total) })}
          </div>
          {/* 三项数值行自上而下 cache read → input → output（用户 2026-08-25
              裁定修订；与柱内堆叠顺序独立——TOOLTIP_ROW_ORDER 钉住） */}
          {TOOLTIP_ROW_ORDER.map((k) => {
            const v =
              k === "output" ? tip.bar.output : k === "input" ? tip.bar.input : tip.bar.cacheRead;
            const pct = tip.bar.total > 0 ? (v / tip.bar.total) * 100 : 0;
            return (
              <div key={k} className="chart-tip-row">
                {t("token.chart.tipRow", {
                  name: nameOf[k],
                  n: v.toLocaleString(),
                  pct: pct.toFixed(1),
                })}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function formatTime(ms: number | null): string {
  if (ms == null) return "—";
  const d = new Date(ms);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}
