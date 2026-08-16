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

/** 时间跨度预设（TC-TK-08：7d / 30d / 自定义；边界含当天）。 */
type Preset = "7d" | "30d" | "custom";

/** 统计维度（TC-TK-07：day/week/range 驱动时序与汇总；session 维度固定给会话列表）。 */
type Dimension = "day" | "week" | "range";

const PROJECT_COLORS = [
  "#6366f1",
  "#10b981",
  "#f59e0b",
  "#ef4444",
  "#06b6d4",
  "#8b5cf6",
  "#ec4899",
  "#84cc16",
];

/** 错误码 → 用户提示（TC-TK-03/04/13）。 */
function errorHint(err: StatsError): string {
  switch (err.code) {
    case "no-database":
      return "数据库未运行/未初始化：未检测到 opencode 数据库（opencode.db / opencode-canary.db）。";
    case "legacy-storage":
      return "检测到旧版 opencode 存储格式（storage/session/*.json）：请升级 opencode 后使用。";
    case "schema-mismatch":
      // 错误 message 自 Rust 带出（已含"请升级 pulse-pet"提示），前端不重复拼接（M3 P3-⑤）
      return `opencode.db schema 不兼容（${err.message}）`;
    default:
      return `查询失败：${err.message}`;
  }
}

export default function TokenStats() {
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

  /** 项目分布（TC-TK-09 ③）：跨维度行按 project 聚合 cost。 */
  const projects = useMemo(() => {
    if (!rows) return [] as { label: string; cost: number; tokens: number }[];
    const map = new Map<string, { cost: number; tokens: number }>();
    for (const r of rows) {
      const k = r.project_id ?? "（未知项目）";
      const cur = map.get(k) ?? { cost: 0, tokens: 0 };
      cur.cost += r.cost;
      cur.tokens += r.tokens_input + r.tokens_output + r.tokens_cache_read;
      map.set(k, cur);
    }
    return [...map.entries()]
      .map(([label, v]) => ({ label, ...v }))
      .sort((a, b) => b.cost - a.cost || b.tokens - a.tokens);
  }, [rows]);

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
        <div className="token-seg" role="tablist" aria-label="时间跨度">
          {(["7d", "30d", "custom"] as Preset[]).map((p) => (
            <button
              key={p}
              className={preset === p ? "seg active" : "seg"}
              onClick={() => setPreset(p)}
            >
              {p === "custom" ? "自定义" : p === "7d" ? "近 7 天" : "近 30 天"}
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
              aria-label="起始日期"
            />
            ～
            <input
              type="date"
              value={toStr}
              min={fromStr}
              onChange={(e) => setToStr(e.target.value)}
              aria-label="结束日期"
            />
          </span>
        )}
        <div className="token-seg" role="tablist" aria-label="统计维度">
          {(["day", "week", "range"] as Dimension[]).map((d) => (
            <button
              key={d}
              className={dimension === d ? "seg active" : "seg"}
              onClick={() => setDimension(d)}
            >
              {d === "day" ? "按天" : d === "week" ? "按周" : "整段"}
            </button>
          ))}
        </div>
        <button className="seg" onClick={() => void load()} disabled={loading}>
          {loading ? "查询中…" : "刷新"}
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
          <h3>Token 时序（{dimension === "day" ? "按天" : "按周"}）</h3>
          <TimeBarChart
            data={buckets}
            color="#6366f1"
          />
        </section>
      )}

      <div className="token-columns">
        {/* ③ 项目分布：饼图 + 列表 */}
        {rows && projects.length > 0 && (
          <section className="token-section">
            <h3>项目分布</h3>
            <ProjectPie projects={projects} />
          </section>
        )}

        {/* ④ 会话列表：按 token 降序，可展开详情（TC-TK-09） */}
        {sessions && (
          <section className="token-section">
            <h3>会话（{sortedSessions.length}）</h3>
            {sortedSessions.length === 0 && (
              <p className="token-empty">跨度内无会话记录。</p>
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
                          <dt>更新时间</dt>
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

/** 自画 SVG 柱状图（几何来自纯函数 computeBars）。 */
function TimeBarChart({
  data,
  color,
}: {
  data: { label: string; tokens: number }[];
  color: string;
}) {
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
      aria-label="token 时序柱状图"
    >
      <line
        x1={PAD}
        y1={H - PAD}
        x2={W - PAD}
        y2={H - PAD}
        stroke="#d1d5db"
        strokeWidth="1"
      />
      {bars.map((b, i) => (
        <rect
          key={data[i].label}
          x={b.x}
          y={b.y}
          width={b.w}
          height={b.h}
          fill={color}
          rx="2"
        >
          <title>{`${data[i].label}：${data[i].tokens.toLocaleString()} tokens`}</title>
        </rect>
      ))}
      {/* 首尾标签（中间条 hover title 提供详情） */}
      {data.length > 0 && (
        <text x={PAD} y={H - 4} fontSize="10" fill="#6b7280">
          {data[0].label}
        </text>
      )}
      {data.length > 1 && (
        <text
          x={W - PAD}
          y={H - 4}
          fontSize="10"
          fill="#6b7280"
          textAnchor="end"
        >
          {data[data.length - 1].label}
        </text>
      )}
      {max > 0 && (
        <text x={PAD} y={PAD - 4} fontSize="10" fill="#9ca3af">
          {formatTokens(max)}
        </text>
      )}
    </svg>
  );
}

/** 项目占比饼图 + 列表。 */
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
        aria-label="项目 cost 占比"
      >
        {slices.map((s, i) => (
          <path key={s.label} d={s.path} fill={PROJECT_COLORS[i % PROJECT_COLORS.length]}>
            <title>{`${s.label}：${s.percent.toFixed(1)}%`}</title>
          </path>
        ))}
      </svg>
      <ul className="project-list">
        {projects.map((p, i) => (
          <li key={p.label}>
            <span
              className="project-dot"
              style={{
                background: PROJECT_COLORS[i % PROJECT_COLORS.length],
              }}
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
