import { describe, expect, it } from "vitest";
import {
  celebrationText,
  composeDue,
  dueHasTime,
  formatDue,
  parseTodoCompleted,
  priorityLabel,
  splitDue,
  todoReminderText,
  validateTodoInput,
  type TodoInput,
} from "./todos";

function input(overrides: Partial<TodoInput> = {}): TodoInput {
  return {
    title: "交报告",
    notes: null,
    priority: 0,
    due_date: null,
    remind_before_minutes: 5,
    sort_order: 0,
    tags: [],
    ...overrides,
  };
}

describe("validateTodoInput：表单校验（与 Rust 同口径，TC-TD-02）", () => {
  it("合法输入通过（含两种 due 形态）", () => {
    expect(validateTodoInput(input())).toBeNull();
    expect(validateTodoInput(input({ due_date: "2026-08-18" }))).toBeNull();
    expect(validateTodoInput(input({ due_date: "2026-08-18T15:30" }))).toBeNull();
    expect(validateTodoInput(input({ remind_before_minutes: 0 }))).toBeNull();
  });

  it("标题空/超长拒绝", () => {
    expect(validateTodoInput(input({ title: "  " }))).toMatch(/标题/);
    expect(validateTodoInput(input({ title: "x".repeat(141) }))).toMatch(/标题/);
  });

  it("优先级/提前提醒越界拒绝", () => {
    expect(validateTodoInput(input({ priority: 4 }))).toMatch(/优先级/);
    expect(validateTodoInput(input({ priority: -1 }))).toMatch(/优先级/);
    expect(validateTodoInput(input({ remind_before_minutes: -1 }))).toMatch(/提前提醒/);
    expect(validateTodoInput(input({ remind_before_minutes: 10081 }))).toMatch(/提前提醒/);
  });

  it("due 格式非法拒绝（空格分隔/非零填充/越界）", () => {
    expect(validateTodoInput(input({ due_date: "2026-08-18 15:30" }))).toMatch(/截止/);
    expect(validateTodoInput(input({ due_date: "2026-8-18" }))).toMatch(/截止/);
    expect(validateTodoInput(input({ due_date: "2026-08-18T25:00" }))).toMatch(/截止/);
  });

  it("标签数量/长度限制", () => {
    expect(validateTodoInput(input({ tags: Array.from({ length: 21 }, (_, i) => `t${i}`) }))).toMatch(/标签/);
    expect(validateTodoInput(input({ tags: ["x".repeat(41)] }))).toMatch(/标签/);
  });
});

describe("due_date 形态互转（TC-TD-03/08 前提）", () => {
  it("dueHasTime", () => {
    expect(dueHasTime("2026-08-18T15:30")).toBe(true);
    expect(dueHasTime("2026-08-18")).toBe(false);
    expect(dueHasTime(null)).toBe(false);
  });

  it("composeDue / splitDue 互逆", () => {
    expect(composeDue("2026-08-18", "")).toBe("2026-08-18");
    expect(composeDue("2026-08-18", "15:30")).toBe("2026-08-18T15:30");
    expect(composeDue("", "15:30")).toBeNull();
    expect(splitDue("2026-08-18T15:30")).toEqual({ date: "2026-08-18", time: "15:30" });
    expect(splitDue("2026-08-18")).toEqual({ date: "2026-08-18", time: "" });
    expect(splitDue(null)).toEqual({ date: "", time: "" });
    // 往返
    const due = composeDue("2026-12-01", "09:05");
    expect(splitDue(due)).toEqual({ date: "2026-12-01", time: "09:05" });
  });
});

describe("todoReminderText：到点气泡文案（TC-TD-03）", () => {
  const now = 1_800_000_000_000;

  it("按触发时刻距 due 的剩余分钟数计算 X", () => {
    expect(todoReminderText("交报告", now + 5 * 60_000, now)).toBe("还有 5 分钟要完成「交报告」");
    expect(todoReminderText("交报告", now + 90 * 60_000, now)).toBe("还有 90 分钟要完成「交报告」");
  });

  it("四舍五入；已过期 → 0（不出现负数）", () => {
    expect(todoReminderText("交报告", now + 4 * 60_000 + 30_000, now)).toBe(
      "还有 5 分钟要完成「交报告」",
    );
    expect(todoReminderText("交报告", now - 60_000, now)).toBe("还有 0 分钟要完成「交报告」");
  });

  it("due 缺失/非法 → null（调用方回退纯 label）", () => {
    expect(todoReminderText("交报告", null, now)).toBeNull();
    expect(todoReminderText("交报告", Number.NaN, now)).toBeNull();
  });
});

describe("parseTodoCompleted / celebrationText（TC-TD-04/05）", () => {
  const valid = { title: "交报告", completed_today: 3, all_today_done: true };

  it("合法 payload 解析", () => {
    expect(parseTodoCompleted(valid)).toEqual(valid);
  });

  it("缺字段/类型不对 → null（静默忽略）", () => {
    expect(parseTodoCompleted(null)).toBeNull();
    expect(parseTodoCompleted("x")).toBeNull();
    expect(parseTodoCompleted({ ...valid, title: 5 })).toBeNull();
    expect(parseTodoCompleted({ ...valid, completed_today: "3" })).toBeNull();
    expect(parseTodoCompleted({ ...valid, all_today_done: 1 })).toBeNull();
  });

  it("全清 → 今日完成 N 项；普通完成 → 干得漂亮", () => {
    expect(celebrationText(valid)).toBe("今日完成 3 项");
    expect(
      celebrationText({ title: "交报告", completed_today: 1, all_today_done: false }),
    ).toBe("干得漂亮 🎉");
  });
});

describe("展示辅助", () => {
  it("priorityLabel / formatDue", () => {
    expect(priorityLabel(0)).toBe("无");
    expect(priorityLabel(3)).toBe("高");
    expect(priorityLabel(9)).toBe("9");
    expect(formatDue("2026-08-18T15:30")).toBe("2026-08-18 15:30");
    expect(formatDue("2026-08-18")).toBe("2026-08-18");
    expect(formatDue(null)).toBe("无");
  });
});
