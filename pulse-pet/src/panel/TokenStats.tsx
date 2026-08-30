import { useCallback, useEffect, useMemo, useState } from "react";
import {
  dayLabelsBetween,
  fetchTokenRows,
  formatCost,
  formatTokens,
  isTauriRuntime,
  localDateStr,
  resolveQueryRange,
  sumRows,
  type GroupBy,
  type StatsError,
  type TokenRow,
} from "../lib/token-stats";
import { badgeOf, hasCostOf, specOf } from "../lib/agents";
import {
  agentsWithRows,
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

/** v2 M5（TC-M5-07）：例程会话识别——M4 spawn 的 `opencode run --title
 *  "pulsepet 例程: …"`（前缀匹配；title 保留已由 TC-M4-08 实测确认，R8）。 */
function isRoutineSession(s: TokenRow): boolean {
  return (s.title ?? "").startsWith("pulsepet 例程:");
}

/** v2 registry（agent-registry §6.2）：会话行 agent 徽标查表——**未知 id
 *  显原名**（消静默错误 ②：原三元 else→oc 会把新 agent 会话行错标 oc）；
 *  text 走 badgeOf（P2 钉 1 直接覆盖消费点）、title 走 i18n 全名，
 *  未知 id 原名兜底。 */
function agentBadgeOf(s: TokenRow): { text: string; title: string } {
  const spec = specOf(s.agent);
  return { text: badgeOf(s.agent), title: spec ? t(spec.labelKey) : s.agent };
}

/** v2 M5 R2（TC-M5-04-1）：agent tab 显示名（i18n 全名；未知 agent 原样）。 */
function agentLabel(agent: string): string {
  const spec = specOf(agent);
  return spec ? t(spec.labelKey) : agent;
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
  /**
   * v2 M5 R2（TC-M5-04，方案 A）：agent 维度 tab 单选（两级筛选第一级）——
   * null = 「全部」（恒显，默认选中）＝ 双源混合全量；具体 agent = 单选。
   * 替代 R1 的 agent 复选框第二组（维度混杂偏差修正）。作用域仅柱图。
   */
  const [agentTab, setAgentTab] = useState<string | null>(null);
  /**
   * v2 M5（C1/N-4）→ P3 口径 A′（agent-registry §6.4）：degraded 细横幅收窄为
   * 「主源 opencode **Failed**（在但坏）× 其余源有数据」（Missing 不触发），
   * 仅 panel 顶部细条提示。
   */
  const [degraded, setDegraded] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      // v2 M4 R3（tester R2 P2 修复）：查询窗口**每次 load 重算**——此前 range
      // 在挂载时 useMemo 定格（面板 hide/show 不重挂载），活跃会话 time_updated
      // 越过定格 toMs 后被整体排除且 Refresh 不可追回；preset 的 to 随调用时刻
      // 前进，custom（用户指定区间）整天边界语义不变（resolveQueryRange）。
      const range = resolveQueryRange(preset, fromStr, toStr);
      // 时序/汇总维度 + 固定 session 维度（会话列表，TC-TK-09 ④）；
      // v2 M5：返回体 {rows, degraded} 包装
      const [dim, sess] = await Promise.all([
        fetchTokenRows(range.fromMs, range.toMs, dimension as GroupBy),
        fetchTokenRows(range.fromMs, range.toMs, "session"),
      ]);
      setRows(dim.rows);
      setSessions(sess.rows);
      setDegraded(dim.degraded ?? sess.degraded);
      setError(null);
    } catch (e) {
      setError(e as StatsError);
      setRows(null);
      setSessions(null);
      setDegraded(null);
    } finally {
      setLoading(false);
    }
  }, [preset, fromStr, toStr, dimension]);

  useEffect(() => {
    void load();
  }, [load]);

  /**
   * v2 M4 并入修复（M3 移交 P2，TC-M3-11/12）：面板 Token 页数据定格——
   * load 仅挂载执行 + panel visible:false 隐藏创建即挂载 → 长运行 App 首开
   * 面板数据为启动时刻快照。仿 Settings.tsx tauri://focus 双触发：面板重新
   * 可见（重开必触发）时刷新——「今日」默认跨度下首开即近实时值。
   */
  useEffect(() => {
    if (!isTauriRuntime()) return;
    let unlisten: (() => void) | undefined;
    let alive = true;
    void import("@tauri-apps/api/window")
      .then(({ getCurrentWindow }) =>
        getCurrentWindow().onFocusChanged(({ payload: focused }) => {
          if (focused) void load();
        }),
      )
      .then((un) => {
        if (alive) unlisten = un;
        else un();
      })
      .catch((e) => console.error("[pulsepet] token focus refresh bind failed:", e));
    return () => {
      alive = false;
      unlisten?.();
    };
  }, [load]);

  // 数据/维度切换 → 模型筛选重置为全勾（新跨度 chip 集合变化）；数据刷新后
  // 当前选中 agent 已无数据 → 回落「全部」（TC-M5-04-1/2，v2 M5 R2）。
  // agentTab 只读不依赖：回落判定是 rows 变化的伴随效应，非触发源。
  useEffect(() => {
    setSelectedModels(null);
    if (agentTab !== null && !agentsWithRows(rows ?? []).includes(agentTab)) {
      setAgentTab(null);
    }
  }, [rows, dimension]);

  const kpi = useMemo(() => sumRows(rows ?? []), [rows]);

  /** v2 M5 R2（TC-M5-04-1）：agent tab 选项 = 仅有数据的 agent（无数据不渲染；
   *  「全部」恒显由渲染层并列补上，仅一个 agent 有数据时仍并列）。 */
  const agents = useMemo(() => agentsWithRows(rows ?? []), [rows]);

  /**
   * 模型 chip 清单（联动收窄，TC-M5-04-2）：「全部」→ 所有 agent 的模型并集；
   * 选中具体 agent → 仅该 agent 有数据的模型。distinct model_id 按总量降序。
   */
  const chips = useMemo(
    () =>
      computeModelChips(
        rows ?? [],
        agentTab === null ? undefined : new Set([agentTab]),
      ),
    [rows, agentTab],
  );

  const effectiveSelected = useMemo<ReadonlySet<ModelKey>>(
    () => selectedModels ?? new Set(chips.map((c) => c.key)),
    [selectedModels, chips],
  );

  /**
   * §十二 F2（2026-08-28）：day 维度补零柱的窗口日标签——day 粒度下 to 随
   * 时刻漂移不影响标签集合，独立 memo（load 内仍每次重算查询窗口，M4 R3
   * 语义不变）。周维度不传（1-2 根周柱不补）。
   * 审查 P2-1：deps 含 rows——跨午夜驻留后 Refresh 时 load 产出新 rows 触发
   * 重算，标签窗口跟随前进（否则 preset/deps 三项不变 → 陈旧窗口多出乱序
   * 零柱：7d 8 柱 / 今日 2 柱，违背 §12.2 验收承诺；切 preset/重挂载自愈
   * 不算兜底）。
   */
  const chartDayLabels = useMemo(() => {
    if (dimension !== "day") return undefined;
    const r = resolveQueryRange(preset, fromStr, toStr);
    return dayLabelsBetween(r.fromMs, r.toMs);
  }, [dimension, preset, fromStr, toStr, rows]);

  const bars = useMemo(
    () =>
      dimension === "range"
        ? []
        : computeStackedBars(rows ?? [], effectiveSelected, {
            width: 640,
            height: 190,
            pad: 18,
            // §十二 F2：≤7 天窗口逐日补零（今日=1 柱、7d 恒 7 柱；函数侧
            // >7 枚自动忽略——30d/custom 维持"有数据才出柱"）
            expectedLabels: chartDayLabels,
            // v2 M5 R2：agent 维度 tab 单选（作用域仅柱图，E 口径）——具体
            // agent = 单元素集 /「全部」= 不传（N12 钉子：不传 = 不过滤全量）
            agentFilter: agentTab === null ? undefined : new Set([agentTab]),
          }),
    [rows, dimension, effectiveSelected, agentTab, chartDayLabels],
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

  /**
   * v2 M5 R2（TC-M5-04-2）：agent tab 单选（null = 「全部」）；切换时模型勾选
   * 重置为全选（不保留跨 tab 隐性勾选——chips 随 tab 联动收窄）。
   */
  const selectAgent = (agent: string | null) => {
    setAgentTab(agent);
    setSelectedModels(null);
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

      {/* v2 M5（C1/N-4）→ P3 口径 A′：degraded 细横幅——主源 opencode Failed
          （在但坏）× 其余源有数据时仅 panel 顶部细条提示，不遮蔽内容；
          pet 侧三层不呈现（宠物不打扰） */}
      {!error && degraded && (
        <div className="token-degraded" title={degraded}>
          {t("token.degraded")}
        </div>
      )}

      {/* ① KPI 四卡（用户 2026-08-25 裁定修订：总量 / cache read / input /
          output——cost 卡移除，cache read 升独立第二卡，首卡无副行小字；
          cost 数据仍在会话详情中展示） */}
      {rows && (
        <>
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
          {/* §十二 F3（2026-08-28）：费用口径标注移除（用户裁定）——cost 数据
              仍在会话列表/详情展示 */}
        </>
      )}

      {/* ② 堆叠柱图 + 筛选（day/week 维度；range 维无柱图——隐藏柱图与
          筛选区（含 agent tab），仅 KPI + 会话列表，§3.5） */}
      {rows && dimension !== "range" && (
        <section className="token-section">
          {/* v2 M5 R2（TC-M5-04-1）：标题行 = h3 左 + agent 维度 tab 右
              （两级筛选第一级；分段单选交互照抄 Settings theme-seg） */}
          <div className="token-chart-head">
            <h3>
              {t("token.chart.title", {
                dim: dimension === "day" ? t("token.dim.day") : t("token.dim.week"),
              })}
            </h3>
            <div
              className="token-seg agent-seg"
              role="radiogroup"
              aria-label={t("token.aria.agent")}
            >
              {/* 「全部」恒显、默认选中；仅一个 agent 有数据时仍并列（语义稳定） */}
              <button
                role="radio"
                aria-checked={agentTab === null}
                className={agentTab === null ? "seg active" : "seg"}
                onClick={() => selectAgent(null)}
              >
                {t("token.agent.all")}
              </button>
              {agents.map((a) => (
                <button
                  key={a}
                  role="radio"
                  aria-checked={agentTab === a}
                  className={agentTab === a ? "seg active" : "seg"}
                  onClick={() => selectAgent(a)}
                >
                  {agentLabel(a)}
                </button>
              ))}
            </div>
          </div>

          {/* 筛选 chip 行：模型复选框（两级筛选第二级，随 agent tab 联动收窄
              ——选中具体 agent → 仅该 agent 有数据的模型，「全部」→ 双源并集） */}
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
            // 模型空集空态（M3 口径不变；agent 单选 tab 恒有一项选中——
            // agent 空集不可达，noAgents 分支随 R2 单选交互移除）
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
                    {/* v2 M5：agent 标识微列（oc / cc 等宽小字徽标，i18n title 全名） */}
                    <span
                      className="session-agent"
                      title={agentBadgeOf(s).title}
                    >
                      {agentBadgeOf(s).text}
                    </span>
                    <span className="session-title" title={sessionTitleTip(s)}>
                      {/* v2 M5（TC-M5-07）：例程会话 ⚡ 徽标（零 schema 改动） */}
                      {isRoutineSession(s) && (
                        <span className="session-task-badge" title={t("token.taskBadge")}>
                          ⚡
                        </span>
                      )}
                      {sessionTitle(s)}
                    </span>
                    <span className="session-project">{projectName(s)}</span>
                    <span className="session-tokens">{formatTokens(total)}</span>
                    {/* v2 registry：无费用数据源的 agent（CC 数据层恒 0，S4 口径）
                        行 cost 列 `—`——查表 hasCostOf（§6.2） */}
                    <span className="session-cost">
                      {!hasCostOf(s.agent) ? "—" : formatCost(s.cost)}
                    </span>
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
                        {/* v2 registry：同会话行——`!hasCostOf` 查表（CC 恒 0 → —） */}
                        <dd>{!hasCostOf(s.agent) ? "—" : formatCost(s.cost)}</dd>
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
      {/* §二十（V2-OPEN-ITEMS）：Token 页底部统计链被动性质说明 + 状态查看
          入口导向接入卡（与接入卡统计源状态行互为闭环；文案 2026-08-30
          用户逐轮裁定逐字定稿）。 */}
      <p className="settings-current">{t("token.sourceNote")}</p>
    </div>
  );
}

/** 勾选切换纯逻辑（不可变更新；模型筛选用——v2-m5 R2 后 agent 维度已改
 *  为恒全集展示，不再消费本函数，勿据旧注释恢复调用）。 */
function symmetricToggle<T>(set: ReadonlySet<T>, key: T): Set<T> {
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
        {/* 横坐标标签（§十二 F2）：n≤7 每柱一枚、与柱中心线对齐
            （textAnchor=middle，x=柱中心）；n>7 维持首尾两枚（原行为） */}
        {bars.length > 7 ? (
          <>
            <text className="chart-label" x={PAD} y={H - 4} fontSize="10">
              {bars[0].label}
            </text>
            <text
              className="chart-label"
              x={W - PAD}
              y={H - 4}
              fontSize="10"
              textAnchor="end"
            >
              {bars[bars.length - 1].label}
            </text>
          </>
        ) : (
          bars.map((b) => (
            <text
              key={b.label}
              className="chart-label"
              x={b.x + b.w / 2}
              y={H - 4}
              fontSize="10"
              textAnchor="middle"
            >
              {b.label}
            </text>
          ))
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
