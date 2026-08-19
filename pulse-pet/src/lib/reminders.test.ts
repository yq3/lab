import { describe, expect, it } from "vitest";
import {
  formatInterval,
  formatWindow,
  isCrossMidnight,
  kindLabel,
  parseReminderTrigger,
  ruleToForm,
  sanitizeReminderText,
  usesFireworks,
  validateReminderInput,
  type ReminderInput,
  type ReminderRule,
} from "./reminders";

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
