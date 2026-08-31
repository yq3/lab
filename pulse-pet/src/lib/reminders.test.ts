import { describe, expect, it } from "vitest";
import {
  actionBadge,
  actionBadgeTitle,
  execBadge,
  execFromParams,
  execParamsJson,
  formatInterval,
  formatWindow,
  hasSmartQuotes,
  isCrossMidnight,
  kindLabel,
  parseReminderTrigger,
  parseWeekdays,
  planReminderActions,
  renderTaskSummary,
  ruleToForm,
  normalizeSmartQuotes,
  sanitizeReminderText,
  scheduleSummary,
  usesFireworks,
  validateExecParams,
  validateReminderInput,
  weekdaysToJson,
  type ExecFormState,
  type ReminderInput,
  type ReminderRule,
  type ReminderTrigger,
} from "./reminders";
import { parseTaskResult } from "./reminder-bridge";

function input(overrides: Partial<ReminderInput> = {}): ReminderInput {
  return {
    kind: "hydration",
    label: "该喝水啦 💧",
    interval_minutes: 30,
    start_time: null,
    end_time: null,
    enabled: true,
    use_fireworks: false,
    ...overrides,
  };
}

/** v2 M4 字段尾巴（struct 展开用）。 */
const m4Fields = {
  action_type: "notify" as const,
  action_params: null,
  schedule_kind: "interval" as const,
  schedule_at: null,
  schedule_weekdays: null,
  snooze_until: null,
  last_skipped_at: null,
};

describe("sanitizeReminderText：提醒文案净化（TC-RM-15）", () => {
  it("普通文案原样保留（含 emoji）", () => {
    expect(sanitizeReminderText("该喝水啦 💧")).toBe("该喝水啦 💧");
    expect(sanitizeReminderText("休息一下 ☕")).toBe("休息一下 ☕");
  });

  it("HTML/script 标记不解释、不执行——作为纯文本保留", () => {
    const out = sanitizeReminderText("<script>alert(1)</script> 喝水");
    expect(out).toBe("<script>alert(1)</script> 喝水");
  });

  it("markdown 链接与 URL 被置换为占位符（不展示原始链接）", () => {
    expect(sanitizeReminderText("看 http://evil.com/x?a=1 文档")).toBe("看 ［链接］ 文档");
    expect(sanitizeReminderText("见 https://x.io/p 吗")).toBe("见 ［链接］ 吗");
    expect(sanitizeReminderText("去 www.example.com 看看")).toBe("去 ［链接］ 看看");
    // markdown 链接语法：URL 部分被置换，标记本身保留为纯文本
    expect(sanitizeReminderText("[点我](https://evil.com)")).toBe("[点我](［链接］)");
  });

  it("原始路径不展示（POSIX / ~ / Windows）", () => {
    expect(sanitizeReminderText("检查 /Users/me/.ssh/id_rsa 文件")).toBe("检查 ［路径］ 文件");
    expect(sanitizeReminderText("看 ~/notes/todo.md 了吗")).toBe("看 ［路径］ 了吗");
    expect(sanitizeReminderText("打开 C:\\Users\\me\\secret.txt 看看")).toBe("打开 ［路径］ 看看");
    // 普通分数表达不受影响（斜杠前非空白）
    expect(sanitizeReminderText("喝 3/4 杯水")).toBe("喝 3/4 杯水");
  });

  it("secret 样式 token 被置换", () => {
    expect(sanitizeReminderText("key sk-abc123456789xyz 记得删")).toBe("key ［密钥］ 记得删");
    expect(sanitizeReminderText("token ghp_" + "a".repeat(30) + " 环境变量")).toBe(
      "token ［密钥］ 环境变量",
    );
  });

  it("多行单行化 + 超长截断（复用 M3 基础净化）", () => {
    expect(sanitizeReminderText("a\nb\nc")).toBe("a b c");
    expect(sanitizeReminderText("x".repeat(200)).length).toBe(140);
  });

  it("空/非字符串 → 空串（丢弃不出气泡）", () => {
    expect(sanitizeReminderText("")).toBe("");
    expect(sanitizeReminderText("   ")).toBe("");
    expect(sanitizeReminderText(123)).toBe("");
    expect(sanitizeReminderText(null)).toBe("");
  });
});

describe("validateReminderInput：表单校验（与 Rust 同口径）", () => {
  it("合法输入通过", () => {
    expect(validateReminderInput(input())).toBeNull();
    expect(
      validateReminderInput(input({ kind: "custom", label: "站起来走走 🚶", interval_minutes: 90 })),
    ).toBeNull();
  });

  it("文案空/超长拒绝", () => {
    expect(validateReminderInput(input({ label: "  " }))).toMatch(/文案/);
    expect(validateReminderInput(input({ label: "x".repeat(141) }))).toMatch(/文案/);
  });

  it("间隔越界拒绝（非 todo 至少 1 分钟）", () => {
    expect(validateReminderInput(input({ interval_minutes: 0 }))).toMatch(/间隔/);
    expect(validateReminderInput(input({ interval_minutes: 1441 }))).toMatch(/间隔/);
    expect(validateReminderInput(input({ interval_minutes: 1440 }))).toBeNull();
  });

  it("HH:MM 格式与范围校验（对齐 Rust parse_hhmm）", () => {
    expect(validateReminderInput(input({ start_time: "25:00" }))).toMatch(/起始/);
    expect(validateReminderInput(input({ end_time: "9点" }))).toMatch(/结束/);
    expect(validateReminderInput(input({ end_time: "09:60" }))).toMatch(/结束/);
    expect(validateReminderInput(input({ start_time: "09:00", end_time: "18:00" }))).toBeNull();
  });

  it("P2-2（R1 审查）：en 模式校验串纯英文——字段名本地化不混搭", () => {
    // 越界（timeRange）与格式（timeFormat）两分支的字段名 start/end 均本地化
    expect(validateReminderInput(input({ start_time: "25:00" }), "en")).toBe(
      "start time out of range (00:00-23:59)",
    );
    expect(validateReminderInput(input({ end_time: "9点" }), "en")).toBe(
      "end time should be HH:MM",
    );
    const todoBadAbs = input({
      kind: "todo",
      label: "x",
      interval_minutes: 0,
      start_time: "15:25",
    });
    expect(validateReminderInput(todoBadAbs, "en")).toBe(
      "start should be YYYY-MM-DDTHH:MM (derived todo)",
    );
    // zh 侧字段名保持中文（既有行为不回归）
    expect(validateReminderInput(input({ end_time: "9点" }))).toMatch(/结束/);
  });
});

describe("parseReminderTrigger / usesFireworks（TC-RM-11 OR 语义）", () => {
  const valid = {
    id: 1,
    kind: "hydration",
    label: "该喝水啦 💧",
    use_fireworks: false,
    fireworks_global: false,
    log_id: 9,
  };

  it("合法 payload 解析", () => {
    // M7：解析结果补 todo_due_ms（可选字段缺省 null）
    expect(parseReminderTrigger(valid)).toEqual({ ...valid, todo_due_ms: null });
  });

  it("缺字段/类型不对 → null（静默忽略）", () => {
    expect(parseReminderTrigger(null)).toBeNull();
    expect(parseReminderTrigger("x")).toBeNull();
    expect(parseReminderTrigger({ ...valid, id: "1" })).toBeNull();
    expect(parseReminderTrigger({ ...valid, log_id: Number.NaN })).toBeNull();
    expect(parseReminderTrigger({ ...valid, label: 5 })).toBeNull();
    expect(parseReminderTrigger({ ...valid, use_fireworks: 1 })).toBeNull();
  });

  it("烟花判定：单条勾选或全局开关任一为真", () => {
    expect(usesFireworks({ use_fireworks: false, fireworks_global: false })).toBe(false);
    expect(usesFireworks({ use_fireworks: true, fireworks_global: false })).toBe(true);
    expect(usesFireworks({ use_fireworks: false, fireworks_global: true })).toBe(true);
    expect(usesFireworks({ use_fireworks: true, fireworks_global: true })).toBe(true);
  });
});

describe("planReminderActions：烟花+气泡叠加编排（v0.1.3 四-5，TC-RM-17）", () => {
  const trig = (over: Partial<ReminderTrigger> = {}): ReminderTrigger => ({
    id: 1,
    kind: "hydration",
    label: "该喝水啦 💧",
    use_fireworks: false,
    fireworks_global: false,
    log_id: 9,
    todo_due_ms: null,
    ...over,
  });
  const NOW = 1_700_000_000_000;

  it("烟花开启：气泡文案照常产出（叠加不替代，TC-RM-17-1）", () => {
    const plan = planReminderActions(trig({ use_fireworks: true }), NOW);
    expect(plan).toEqual({ bubbleText: "该喝水啦 💧", fireworks: true });
    const plan2 = planReminderActions(trig({ fireworks_global: true }), NOW);
    expect(plan2).toEqual({ bubbleText: "该喝水啦 💧", fireworks: true });
  });

  it("烟花关闭：与 v1 纯气泡路径一致（TC-RM-17-2）", () => {
    expect(planReminderActions(trig(), NOW)).toEqual({
      bubbleText: "该喝水啦 💧",
      fireworks: false,
    });
  });

  it("todo 派生提醒：构造「还有 X 分钟」文案且烟花与否不影响文案（TC-RM-17-3）", () => {
    const due = NOW + 30 * 60_000; // 30 分钟后
    const a = planReminderActions(trig({ kind: "todo", todo_due_ms: due }), NOW);
    expect(a.bubbleText).toBe("还有 30 分钟要完成「该喝水啦 💧」");
    expect(a.fireworks).toBe(false);
    const b = planReminderActions(
      trig({ kind: "todo", todo_due_ms: due, use_fireworks: true }),
      NOW,
    );
    expect(b.bubbleText).toBe(a.bubbleText);
    expect(b.fireworks).toBe(true);
    // due 缺失 → 回退纯 label
    expect(planReminderActions(trig({ kind: "todo", todo_due_ms: null }), NOW).bubbleText).toBe(
      "该喝水啦 💧",
    );
  });

  it("文案经净化（TC-RM-15 口径）：URL/路径/secret 置换后再入 plan", () => {
    const plan = planReminderActions(
      trig({ label: "看 http://evil.com/x 和 /etc/passwd" }),
      NOW,
    );
    expect(plan.bubbleText).toBe("看 ［链接］ 和 ［路径］");
  });
});

describe("展示辅助", () => {
  it("formatWindow / isCrossMidnight（TC-RM-06 语义在 UI 的呈现）", () => {
    expect(formatWindow(null, null)).toBe("全天");
    expect(formatWindow("09:00", null)).toBe("09:00 起");
    expect(formatWindow(null, "18:00")).toBe("至 18:00");
    expect(formatWindow("09:00", "18:00")).toBe("09:00-18:00");
    expect(formatWindow("22:00", "06:00")).toBe("22:00-06:00（跨午夜）");
    expect(isCrossMidnight("22:00", "06:00")).toBe(true);
    expect(isCrossMidnight("09:00", "18:00")).toBe(false);
    expect(isCrossMidnight("09:00", null)).toBe(false);
  });

  it("formatInterval", () => {
    expect(formatInterval(0)).toBe("单次");
    expect(formatInterval(30)).toBe("每 30 分钟");
    expect(formatInterval(60)).toBe("每 1 小时");
    expect(formatInterval(120)).toBe("每 2 小时");
  });

  it("kindLabel", () => {
    expect(kindLabel("hydration")).toBe("喝水");
    expect(kindLabel("rest")).toBe("休息");
    expect(kindLabel("custom")).toBe("自定义");
    expect(kindLabel("todo")).toBe("待办");
    expect(kindLabel("unknown")).toBe("unknown");
  });
});

describe("M7：todo 派生规则的表单保真（M4 P2 ② 清偿，TC-TD 章节）", () => {
  const todoRule: ReminderRule = {
    id: 7,
    kind: "todo",
    label: "交报告",
    interval_minutes: 0,
    start_time: "2026-08-18T15:25",
    end_time: null,
    enabled: true,
    use_fireworks: false,
    last_triggered_at: null,
    source_todo_id: 3,
    todo_due_at: "2026-08-18T15:30",
    created_at: "2026-08-17T10:00:00.000+08:00",
    ...m4Fields,
  };

  it("ruleToForm：todo 规则不再降级 custom——kind/interval=0/绝对 start_time 原样保留", () => {
    const f = ruleToForm(todoRule);
    expect(f.kind).toBe("todo");
    expect(f.interval_minutes).toBe(0);
    expect(f.start_time).toBe("2026-08-18T15:25");
    // 快捷开关路径（enabled patch）往返不破坏语义
    expect(ruleToForm({ ...todoRule, enabled: false }).kind).toBe("todo");
  });

  it("validateReminderInput：todo kind 恒 interval=0；绝对时刻格式校验", () => {
    expect(validateReminderInput(ruleToForm(todoRule))).toBeNull();
    expect(
      validateReminderInput({ ...ruleToForm(todoRule), interval_minutes: 30 }),
    ).toMatch(/todo/);
    expect(
      validateReminderInput({ ...ruleToForm(todoRule), interval_minutes: 0 }),
    ).toBeNull();
    // todo 的 start_time 是绝对时刻：HH:MM 反而拒绝
    expect(
      validateReminderInput({ ...ruleToForm(todoRule), start_time: "15:25" }),
    ).toMatch(/起始/);
  });

  it("parseReminderTrigger：todo_due_ms 可选字段（缺失 → null，携带 → 透传）", () => {
    const valid = {
      id: 1,
      kind: "todo",
      label: "交报告",
      use_fireworks: false,
      fireworks_global: false,
      log_id: 9,
    };
    expect(parseReminderTrigger(valid)).toEqual({ ...valid, todo_due_ms: null });
    expect(
      parseReminderTrigger({ ...valid, todo_due_ms: 1787038200000 }),
    ).toEqual({ ...valid, todo_due_ms: 1787038200000 });
    expect(parseReminderTrigger({ ...valid, todo_due_ms: "x" })).toEqual({
      ...valid,
      todo_due_ms: null,
    });
  });
});

describe("M8 i18n：展示辅助随语言", () => {
  it("kindLabel / formatInterval / formatWindow en 变体", () => {
    expect(kindLabel("hydration", "en")).toBe("Hydration");
    expect(kindLabel("todo", "en")).toBe("Todo");
    expect(kindLabel("unknown-kind", "en")).toBe("unknown-kind");
    expect(formatInterval(0, "en")).toBe("Once");
    expect(formatInterval(60, "en")).toBe("Every 1 h");
    expect(formatInterval(90, "en")).toBe("Every 90 min");
    expect(formatWindow(null, null, "en")).toBe("All day");
    expect(formatWindow("09:00", "18:00", "en")).toBe("09:00-18:00");
    expect(formatWindow("22:00", "06:00", "en")).toBe("22:00-06:00 (cross-midnight)");
    expect(formatWindow("09:00", null, "en")).toBe("From 09:00");
    expect(formatWindow(null, "18:00", "en")).toBe("Until 18:00");
  });
});

// ===========================================================================
// v2 M4：动作/调度泛化（TC-M4-02/07/08/11 前端面）
// ===========================================================================

describe("v2 M4：validateReminderInput 动作/调度校验（与 Rust normalize 同规则）", () => {
  it("v1 载荷（不带新字段）→ notify/interval 行为不变", () => {
    expect(validateReminderInput(input())).toBeNull();
    expect(validateReminderInput(input({ interval_minutes: 0 }))).toMatch(/间隔/);
  });

  it("daily：HH:MM 必填 + weekdays 校验；interval/窗口字段不校验（Rust 重置）", () => {
    const daily = input({
      kind: "custom",
      interval_minutes: 0,
      schedule_kind: "daily",
      schedule_at: "09:00",
    });
    expect(validateReminderInput(daily)).toBeNull();
    expect(
      validateReminderInput({ ...daily, schedule_at: null }),
    ).toMatch(/时刻/);
    expect(validateReminderInput({ ...daily, schedule_at: "25:00" })).toMatch(/时刻/);
    expect(
      validateReminderInput({ ...daily, schedule_weekdays: "[1,8]" }),
    ).toMatch(/星期/);
    expect(
      validateReminderInput({ ...daily, schedule_weekdays: "not json" }),
    ).toMatch(/星期/);
    // 非法 schedule_kind / action_type
    expect(
      validateReminderInput({ ...daily, schedule_kind: "weekly" as never }),
    ).toMatch(/调度/);
    expect(
      validateReminderInput({ ...daily, action_type: "webhook" as never }),
    ).toMatch(/动作/);
  });

  it("once：YYYY-MM-DDTHH:MM + 未来时刻（防创建即意外执行）", () => {
    const once = input({
      kind: "custom",
      interval_minutes: 0,
      schedule_kind: "once",
      schedule_at: "2030-01-01T09:00",
    });
    expect(validateReminderInput(once)).toBeNull();
    expect(validateReminderInput({ ...once, schedule_at: "2020-01-01T09:00" })).toMatch(
      /未来/,
    );
    expect(validateReminderInput({ ...once, schedule_at: "09:00" })).toMatch(
      /YYYY-MM-DDTHH:MM/,
    );
  });

  it("exec：action_params 必填 JSON + command/timeout/opencode_auto 校验", () => {
    const exec = input({
      kind: "custom",
      interval_minutes: 0,
      schedule_kind: "once",
      schedule_at: "2030-01-01T09:00",
      action_type: "exec",
      action_params: '{"command":"echo hi"}',
    });
    expect(validateReminderInput(exec)).toBeNull();
    // params 缺失 / JSON 失败（TC-M4-01-4 前端口径）
    expect(validateReminderInput({ ...exec, action_params: null })).toMatch(/action_params/);
    expect(validateReminderInput({ ...exec, action_params: "{not json" })).toMatch(
      /action_params/,
    );
    // command 空/超长
    expect(
      validateReminderInput({ ...exec, action_params: '{"command":"  "}' }),
    ).toMatch(/命令/);
    expect(
      validateReminderInput({
        ...exec,
        action_params: `{"command":"${"x".repeat(2001)}"}`,
      }),
    ).toMatch(/命令/);
    // timeout 1-120；opencode_auto bool
    expect(
      validateReminderInput({ ...exec, action_params: '{"command":"ls","timeout_minutes":0}' }),
    ).toMatch(/超时/);
    expect(
      validateReminderInput({
        ...exec,
        action_params: '{"command":"ls","timeout_minutes":121}',
      }),
    ).toMatch(/超时/);
    expect(
      validateReminderInput({
        ...exec,
        action_params: '{"command":"ls","opencode_auto":"yes"}',
      }),
    ).toMatch(/布尔/);
    // exec + interval：窗口不校验（Rust 清空）
    const execInterval = input({
      kind: "custom",
      interval_minutes: 30,
      action_type: "exec",
      action_params: '{"command":"ls"}',
      start_time: "25:00", // 遗留窗口脏数据——exec 不消费
    });
    expect(validateReminderInput(execInterval)).toBeNull();
  });
});

describe("v2 M4：ruleToForm 往返保真（快捷开关不丢 exec/定点语义）", () => {
  const execRule: ReminderRule = {
    id: 9,
    kind: "custom",
    label: "数 md 文件",
    interval_minutes: 0,
    start_time: null,
    end_time: null,
    enabled: true,
    use_fireworks: false,
    last_triggered_at: null,
    source_todo_id: null,
    todo_due_at: null,
    created_at: "2026-08-25T10:00:00.000+08:00",
    action_type: "exec",
    action_params: '{"command":"ls *.md | wc -l","timeout_minutes":10}',
    schedule_kind: "daily",
    schedule_at: "09:00",
    schedule_weekdays: "[1,3,5]",
    snooze_until: null,
    last_skipped_at: null,
  };

  it("新字段全量带回（enabled patch 后提交仍是 exec/daily）", () => {
    const f = ruleToForm(execRule);
    expect(f.action_type).toBe("exec");
    expect(f.schedule_kind).toBe("daily");
    expect(f.schedule_at).toBe("09:00");
    expect(f.schedule_weekdays).toBe("[1,3,5]");
    expect(f.action_params).toContain("wc -l");
    expect(validateReminderInput(f)).toBeNull();
  });
});

describe("v2 M4：动作徽标 + 调度摘要（§4.7 列表行）", () => {
  it("actionBadge：🔔 notify / ⚡ exec / 📋 todo（§十二 F10：💧→🔔）", () => {
    expect(actionBadge({ kind: "custom", action_type: "notify" })).toBe("🔔");
    expect(actionBadge({ kind: "custom", action_type: "exec" })).toBe("⚡");
    expect(actionBadge({ kind: "todo", action_type: "notify" })).toBe("📋");
    // §十二 F10 审查 P3-1：历史行（无 kind 字段）共用 execBadge 助手
    expect(execBadge("exec")).toBe("⚡");
    expect(execBadge("notify")).toBe("🔔");
    expect(actionBadgeTitle({ kind: "custom", action_type: "exec" })).toContain("执行命令");
  });

  it("scheduleSummary：interval 带窗 / 每天 / 周过滤 / 一次", () => {
    const base = {
      kind: "custom" as const,
      interval_minutes: 30,
      start_time: null,
      end_time: null,
      schedule_kind: "interval" as const,
      schedule_at: null,
      schedule_weekdays: null,
    };
    expect(scheduleSummary(base)).toBe("每 30 分钟");
    expect(
      scheduleSummary({ ...base, start_time: "09:00", end_time: "18:00" }),
    ).toBe("每 30 分钟 · 09:00-18:00");
    expect(
      scheduleSummary({
        ...base,
        interval_minutes: 0,
        schedule_kind: "daily",
        schedule_at: "09:00",
      }),
    ).toBe("每天 09:00");
    expect(
      scheduleSummary({
        ...base,
        interval_minutes: 0,
        schedule_kind: "daily",
        schedule_at: "09:00",
        schedule_weekdays: "[3,5]",
      }),
    ).toBe("周三、五 09:00");
    expect(
      scheduleSummary({
        ...base,
        interval_minutes: 0,
        schedule_kind: "once",
        schedule_at: "2026-08-25T21:00",
      }),
    ).toBe("一次 · 08-25 21:00");
    // en 变体
    expect(
      scheduleSummary(
        {
          ...base,
          interval_minutes: 0,
          schedule_kind: "daily",
          schedule_at: "09:00",
        },
        "en",
      ),
    ).toBe("Daily 09:00");
  });

  it("parseWeekdays / weekdaysToJson 往返（空 = 每天 → null）", () => {
    expect(parseWeekdays(null)).toEqual([]);
    expect(parseWeekdays("[]")).toEqual([]);
    expect(parseWeekdays("[1,3,5]")).toEqual([1, 3, 5]);
    expect(parseWeekdays("bad")).toEqual([]);
    expect(weekdaysToJson([])).toBeNull();
    expect(weekdaysToJson([5, 3, 3])).toBe("[3,5]");
  });
});

describe("V2-OPEN-ITEMS §二十三：弯引号检测/修正纯函数（build 逐字钉已随 Part B 迁至 routine-templates.test.ts）", () => {
  it("仅 ‘’“” 四字符归一 / 检测", () => {
    // 2026-08-30 修订：弯引号在单引号串内是合法字面量——**内容不做归一**
    //（原「拼装归一」属无收益内容改写，撤销）；结构引号恒由模板产 ASCII，
    // 安全由 shellQuote 保证。ASCII 内容引号走标准转义（保留内容非替换）。
    // 一键修正专用：仅 ‘’“” 四字符视为「本应是引号」（修复 IME 误替结构引号）
    expect(normalizeSmartQuotes("‘a’“b”")).toBe(`'a'"b"`);
    expect(hasSmartQuotes("ok’")).toBe(true);
    expect(hasSmartQuotes("ok'")).toBe(false);
    expect(hasSmartQuotes("opencode run --title 'x' 'y'")).toBe(false);
  });
});

describe("Part B：exec 表单态持久化（execParamsJson/execFromParams 迁自 Tasks.tsx + 泛化 tpl_agent/tpl_flags）", () => {
  const st = (over: Partial<ExecFormState> = {}): ExecFormState => ({
    command: "echo hi",
    cwd: "",
    timeoutMinutes: 10,
    tplInstruction: "",
    tplAgent: "opencode",
    tplFlags: {},
    ...over,
  });

  it("execParamsJson：新格式 tpl_agent + tpl_flags（opencode_auto 不再写出；空 cwd 不写、trim 后写）", () => {
    const p = JSON.parse(execParamsJson(st({ tplAgent: "claude-code", tplFlags: { skipPerms: true } })));
    expect(p).toEqual({
      command: "echo hi",
      timeout_minutes: 10,
      tpl_agent: "claude-code",
      tpl_flags: { skipPerms: true },
    });
    expect(execParamsJson(st({ cwd: " /tmp " }))).toContain('"cwd":"/tmp"');
  });

  it("execFromParams 兜底四态（routine-exec.md §3.3）", () => {
    // ① tpl_agent 缺失 + opencode_auto true → opencode + {auto:true}
    expect(execFromParams('{"command":"c","opencode_auto":true}').tplFlags).toEqual({ auto: true });
    // ② tpl_agent 存在 → opencode_auto 忽略（新格式恒不同时写出，并存仅手改数据）
    const b = execFromParams('{"command":"c","tpl_agent":"claude-code","opencode_auto":true}');
    expect(b.tplAgent).toBe("claude-code");
    expect(b.tplFlags).toEqual({});
    // ②' tpl_flags 缺失/非对象 → {}；值非布尔 → 整包 {}（读侧宽松）
    expect(execFromParams('{"command":"c","tpl_agent":"opencode"}').tplFlags).toEqual({});
    expect(execFromParams('{"command":"c","tpl_agent":"opencode","tpl_flags":[1]}').tplFlags).toEqual({});
    expect(
      execFromParams('{"command":"c","tpl_agent":"opencode","tpl_flags":{"auto":"yes"}}').tplFlags,
    ).toEqual({});
    // ③ 未知 tpl_agent → 回落默认 opencode，flags 照常解析、command 不动
    const c = execFromParams('{"command":"c","tpl_agent":"future-agent","tpl_flags":{"x":true}}');
    expect(c.tplAgent).toBe("opencode");
    expect(c.tplFlags).toEqual({ x: true });
    expect(c.command).toBe("c");
    // ④ 均无 / opencode_auto:false → 默认态
    expect(execFromParams('{"command":"c"}').tplAgent).toBe("opencode");
    expect(execFromParams('{"command":"c"}').tplFlags).toEqual({});
    expect(execFromParams('{"command":"c","opencode_auto":false}').tplFlags).toEqual({});
  });

  it("matchOf 反推：command 前缀形态优先决定 tplAgent（重拼只看 command）", () => {
    expect(execFromParams(`{"command":"claude -p 'x'"}`).tplAgent).toBe("claude-code");
    expect(execFromParams(`{"command":"opencode run --title 't' 'i'"}`).tplAgent).toBe("opencode");
    // 手写命令不匹配任何模板 → 存的 tpl_agent（有效）或默认 opencode
    expect(execFromParams('{"command":"echo hi","tpl_agent":"claude-code"}').tplAgent).toBe("claude-code");
    expect(execFromParams('{"command":"echo hi"}').tplAgent).toBe("opencode");
  });

  it("往返 + 非法 JSON / 超范围 timeout 回退", () => {
    expect(execFromParams(execParamsJson(st({ tplFlags: { auto: true } })))).toEqual(
      st({ tplFlags: { auto: true } }),
    );
    expect(execFromParams(null)).toEqual(st({ command: "" }));
    expect(execFromParams("{bad").tplAgent).toBe("opencode");
    expect(execFromParams('{"command":"c","timeout_minutes":999}').timeoutMinutes).toBe(10);
  });

  it("validateExecParams 预检新键（与 Rust 同规则）", () => {
    expect(
      validateExecParams({ command: "ls", tpl_agent: "opencode", tpl_flags: { auto: true } }),
    ).toBeNull();
    expect(validateExecParams({ command: "ls", tpl_flags: "x" })).toMatch(/tpl_flags/);
    expect(validateExecParams({ command: "ls", tpl_flags: { auto: "yes" } })).toMatch(/tpl_flags/);
    expect(validateExecParams({ command: "ls", tpl_agent: 5 })).toMatch(/tpl_agent/);
  });
});

describe("v2 M4：renderTaskSummary 模板键渲染（P3-3，与 Rust 同口径）", () => {
  it("zh/en 双语 + timeout 参数化键 + failed 退出码", () => {
    expect(renderTaskSummary("task.summary.ok")).toBe("任务完成");
    expect(renderTaskSummary("task.summary.failed", 3)).toBe("失败（退出码 3）");
    expect(renderTaskSummary("task.summary.failed", null)).toBe("失败");
    expect(renderTaskSummary("task.summary.timeout:10")).toBe("超时（10 分钟）被终止");
    expect(renderTaskSummary("task.summary.missed")).toBe("错过补跑窗（15 分钟）");
    expect(renderTaskSummary("task.summary.interrupted")).toBe("App 退出中断");
    expect(renderTaskSummary("task.summary.ok", undefined, "en")).toBe("Task finished");
    expect(renderTaskSummary("task.summary.failed", 3, "en")).toBe("Failed (exit code 3)");
    expect(renderTaskSummary("task.summary.timeout:1", undefined, "en")).toBe(
      "Timed out (terminated after 1 min)",
    );
    // 未知键原样（可观测不静默）
    expect(renderTaskSummary("task.summary.unknown")).toBe("task.summary.unknown");
  });
});

describe("v2 M4：task-result 事件解析（P1-3，TC-M4-11）", () => {
  it("合法 payload 解析；字段缺失/类型不对 → null", () => {
    // v2 M6（TC-M6-03-1）：解析结果显式携带 agent（Rust 恒发 "task"；
    // 旧载荷缺字段容错默认 "task"）
    expect(parseTaskResult({ text: "任务：任务完成", logId: 3, status: "ok" })).toEqual({
      text: "任务：任务完成",
      logId: 3,
      status: "ok",
      agent: "task",
    });
    expect(parseTaskResult(null)).toBeNull();
    expect(parseTaskResult({ text: "", logId: 1, status: "ok" })).toBeNull();
    expect(parseTaskResult({ text: "x", logId: "3", status: "ok" })).toBeNull();
    expect(parseTaskResult({ text: "x", logId: 1, status: 5 })).toBeNull();
  });
});
