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
import { computeBars, pieSlices } from "../lib/token-chart";
import { t, useLangStore } from "../lib/i18n";

/** 时间跨度预设（TC-TK-08：7d / 30d / 自定义；边界含当天）。 */
type Preset = "7d" | "30d" | "custom";

/** 统计维度（TC-TK-07：day/week/range 驱动时序与汇总；session 维度固定给会话列表）。 */
type Dimension = "day" | "week" | "range";

/**
 * v2 M2：图表色 token 化（--chart-output/input/cache 三段循环；R8 硬编码
 * 色清零——SVG attribute 不支持 var()，色值走 CSS 类，见 global.css）。
 * M3 砍饼图改堆叠柱图后由三段语义直接对应。
 */
const CHART_CLASSES = ["pie-c0", "pie-c1", "pie-c2"] as const;

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

export default function TokenStats() {
  const lang = useLangStore((s) => s.lang); // M8 i18n：语言变化时本页文案重渲染（projects useMemo 也依赖）
  const [preset, setPreset] = useState<Preset>("7d");
  const [fromStr, setFromStr] = useState(() => localDateStr());
  const [toStr, setToStr] = useState(() => localDateStr());
  const [dimension, setDimension] = useState<Dimension>("day");
  const [rows, setRows] = useState<TokenRow[] | null>(null);
  const [sessions, setSessions] = useState<TokenRow[] | null>(null);
  const [error, setError] = useState<StatsError | null>(null);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);

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

  const kpi = useMemo(() => sumRows(rows ?? []), [rows]);

  /** 时序桶：day/week 维度按 day 标签聚合 tokens；range 维度不画柱图。 */
  const buckets = useMemo(() => {
    if (!rows || dimension === "range") return [] as { label: string; tokens: number }[];
    const map = new Map<string, number>();
    for (const r of rows) {
      const k = r.day ?? "—";
      map.set(k, (map.get(k) ?? 0) + r.tokens_input + r.tokens_output + r.tokens_cache_read);
    }
    return [...map.entries()]
      .map(([label, tokens]) => ({ label, tokens }))
      .sort((a, b) => a.label.localeCompare(b.label));
  }, [rows, dimension]);

  /** 项目分布（TC-TK-09 ③）：跨维度行按 project 聚合 cost。
   * P3-2（R1 审查）：依赖补 lang——"（未知项目）"标签随语言切换即时刷新。 */
  const projects = useMemo(() => {
    if (!rows) return [] as { label: string; cost: number; tokens: number }[];
    const map = new Map<string, { cost: number; tokens: number }>();
    for (const r of rows) {
      const k = r.project_id ?? t("token.project.unknown");
      const cur = map.get(k) ?? { cost: 0, tokens: 0 };
      cur.cost += r.cost;
      cur.tokens += r.tokens_input + r.tokens_output + r.tokens_cache_read;
      map.set(k, cur);
    }
    return [...map.entries()]
      .map(([label, v]) => ({ label, ...v }))
      .sort((a, b) => b.cost - a.cost || b.tokens - a.tokens);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- t 依赖 lang（store 订阅触发组件重渲染）
  }, [rows, lang]);

  const sortedSessions = useMemo(() => {
    if (!sessions) return [] as TokenRow[];
    return [...sessions].sort(
      (a, b) =>
        b.tokens_input + b.tokens_output + b.tokens_cache_read -
        (a.tokens_input + a.tokens_output + a.tokens_cache_read),
    );
  }, [sessions]);

  return (
    <div className="token-stats">
      {/* 控制条：跨度 + 维度 + 刷新 */}
      <div className="token-controls">
        <div className="token-seg" role="tablist" aria-label={t("token.aria.range")}>
          {(["7d", "30d", "custom"] as Preset[]).map((p) => (
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

      {/* ① KPI 卡（TC-TK-09） */}
      {rows && (
        <div className="token-kpis">
          <div className="kpi">
            <div className="kpi-value">{formatTokens(kpi.input)}</div>
            <div className="kpi-label">input tokens</div>
          </div>
          <div className="kpi">
            <div className="kpi-value">{formatTokens(kpi.output)}</div>
            <div className="kpi-label">output tokens</div>
          </div>
          <div className="kpi">
            <div className="kpi-value">{formatTokens(kpi.cacheRead)}</div>
            <div className="kpi-label">cache read</div>
          </div>
          <div className="kpi">
            <div className="kpi-value">{formatCost(kpi.cost)}</div>
            <div className="kpi-label">cost</div>
          </div>
        </div>
      )}

      {/* ② 时序图：自画 SVG 柱状图（TC-TK-09：不引入重依赖库） */}
      {rows && dimension !== "range" && buckets.length > 0 && (
        <section className="token-section">
          {/* P2-1（R1 审查）：i18n 化时误删的标题补回——token.chart.title 双语 */}
          <h3>
            {t("token.chart.title", {
              dim: dimension === "day" ? t("token.dim.day") : t("token.dim.week"),
            })}
          </h3>
          <TimeBarChart data={buckets} />
        </section>
      )}

      <div className="token-columns">
        {/* ③ 项目分布：饼图 + 列表 */}
        {rows && projects.length > 0 && (
          <section className="token-section">
            <h3>{t("token.pie.title")}</h3>
            <ProjectPie projects={projects} />
          </section>
        )}

        {/* ④ 会话列表：按 token 降序，可展开详情（TC-TK-09） */}
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
                      <span className="session-id" title={s.session_id ?? ""}>
                        {shortId(s.session_id)}
                      </span>
                      <span className="session-project">{s.project_id ?? "—"}</span>
                      <span className="session-tokens">{formatTokens(total)}</span>
                      <span className="session-cost">{formatCost(s.cost)}</span>
                      <span className="session-caret">{open ? "▾" : "▸"}</span>
                    </button>
                    {open && (
                      <dl className="session-detail">
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
    </div>
  );
}

/** 自画 SVG 柱状图（几何来自纯函数 computeBars；色值走 CSS 类 = chart token）。 */
function TimeBarChart({ data }: { data: { label: string; tokens: number }[] }) {
  const W = 640;
  const H = 180;
  const PAD = 18;
  const bars = computeBars(
    data.map((d) => d.tokens),
    { width: W, height: H, pad: PAD },
  );
  const max = Math.max(...data.map((d) => d.tokens), 0);
  return (
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
      {bars.map((b, i) => (
        <rect
          key={data[i].label}
          className="bar-fill"
          x={b.x}
          y={b.y}
          width={b.w}
          height={b.h}
        >
          <title>{t("token.chart.bar", { label: data[i].label, n: data[i].tokens.toLocaleString() })}</title>
        </rect>
      ))}
      {/* 首尾标签（中间条 hover title 提供详情） */}
      {data.length > 0 && (
        <text className="chart-label" x={PAD} y={H - 4} fontSize="10">
          {data[0].label}
        </text>
      )}
      {data.length > 1 && (
        <text
          className="chart-label"
          x={W - PAD}
          y={H - 4}
          fontSize="10"
          textAnchor="end"
        >
          {data[data.length - 1].label}
        </text>
      )}
      {max > 0 && (
        <text className="chart-label faint" x={PAD} y={PAD - 4} fontSize="10">
          {formatTokens(max)}
        </text>
      )}
    </svg>
  );
}

/** 项目占比饼图 + 列表（色 = chart token 三段循环，M3 砍饼图）。 */
function ProjectPie({
  projects,
}: {
  projects: { label: string; cost: number; tokens: number }[];
}) {
  const R = 60;
  const slices = pieSlices(
    projects.map((p) => ({ value: p.cost > 0 ? p.cost : p.tokens, label: p.label })),
    R,
  );
  return (
    <div className="project-pie">
      <svg
        width={R * 2}
        height={R * 2}
        viewBox={`0 0 ${R * 2} ${R * 2}`}
        role="img"
        aria-label={t("token.pie.aria")}
      >
        {slices.map((s, i) => (
          <path key={s.label} className={CHART_CLASSES[i % CHART_CLASSES.length]} d={s.path}>
            <title>{t("token.pie.slice", { label: s.label, pct: s.percent.toFixed(1) })}</title>
          </path>
        ))}
      </svg>
      <ul className="project-list">
        {projects.map((p, i) => (
          <li key={p.label}>
            <span
              className={`project-dot ${CHART_CLASSES[i % CHART_CLASSES.length]}`}
            />
            <span className="project-name" title={p.label}>
              {p.label}
            </span>
            <span className="project-pct">
              {(
                (slices.find((s) => s.label === p.label)?.percent ?? 0)
              ).toFixed(1)}
              %
            </span>
            <span className="project-cost">{formatCost(p.cost)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function shortId(id: string | null): string {
  if (!id) return "—";
  return id.length > 14 ? `${id.slice(0, 14)}…` : id;
}

function formatTime(ms: number | null): string {
  if (ms == null) return "—";
  const d = new Date(ms);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}
