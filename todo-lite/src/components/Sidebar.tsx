import { useState } from "react";
import { useListsStore } from "../store/useListsStore";
import { useUIStore } from "../store/useUIStore";
import type { SmartListId } from "../types";
import {
  CalendarIcon,
  CheckIcon,
  ClockIcon,
  FlagIcon,
  InboxIcon,
  MonitorIcon,
  MoonIcon,
  PlusIcon,
  StarIcon,
  SunIcon,
  TrashIcon,
} from "./Icons";

const SMART_LISTS: { id: SmartListId; name: string; icon: React.ReactNode }[] = [
  { id: "my-day", name: "我的某天", icon: <SunIcon /> },
  { id: "important", name: "重要", icon: <StarIcon /> },
  { id: "planned", name: "计划", icon: <CalendarIcon /> },
  { id: "scheduled", name: "已安排", icon: <ClockIcon /> },
  { id: "no-date", name: "无日期", icon: <InboxIcon /> },
  { id: "completed", name: "已完成", icon: <CheckIcon /> },
];

const LIST_COLORS = [
  "#2563eb",
  "#7c3aed",
  "#db2777",
  "#ea580c",
  "#ca8a04",
  "#16a34a",
  "#0d9488",
  "#64748b",
];

export function Sidebar() {
  const { groups, lists, addList, deleteList, addGroup, deleteGroup } = useListsStore();
  const { nav, setNav, theme, cycleTheme } = useUIStore();
  const [showNewList, setShowNewList] = useState(false);
  const [showNewGroup, setShowNewGroup] = useState(false);
  const [name, setName] = useState("");
  const [color, setColor] = useState(LIST_COLORS[0]);
  const [groupId, setGroupId] = useState<number | null>(null);
  const [groupName, setGroupName] = useState("");

  const ungrouped = lists.filter((l) => l.group_id === null);
  const groupedLists = groups.map((g) => ({
    group: g,
    lists: lists.filter((l) => l.group_id === g.id),
  }));

  const submitNewList = async () => {
    if (!name.trim()) return;
    await addList(name.trim(), color, groupId);
    setName("");
    setColor(LIST_COLORS[0]);
    setGroupId(null);
    setShowNewList(false);
  };

  const submitNewGroup = async () => {
    if (!groupName.trim()) return;
    await addGroup(groupName.trim());
    setGroupName("");
    setShowNewGroup(false);
  };

  return (
    <aside className="sidebar">
      <div className="sidebar-scroll">
        <div className="sidebar-title">
          todo-lite
          <button
            className="icon-btn"
            style={{ marginLeft: "auto", opacity: 1 }}
            onClick={() => setShowNewList(true)}
            title="新建列表"
          >
            <PlusIcon />
          </button>
        </div>

        <div className="nav-section-label">智能列表</div>
        {SMART_LISTS.map((s) => (
          <button
            key={s.id}
            className={`nav-item ${nav.kind === "smart" && nav.id === s.id ? "active" : ""}`}
            onClick={() => setNav({ kind: "smart", id: s.id })}
          >
            <span className="nav-icon">{s.icon}</span>
            {s.name}
          </button>
        ))}

        <div className="nav-section-label">
          <span>我的列表</span>
          <button className="icon-btn" onClick={() => setShowNewGroup(true)} title="新建分组">
            <PlusIcon width={14} height={14} />
          </button>
        </div>

        {ungrouped.map((l) => (
          <button
            key={l.id}
            className={`nav-item ${nav.kind === "list" && nav.listId === l.id ? "active" : ""}`}
            onClick={() => setNav({ kind: "list", listId: l.id })}
          >
            <span className="nav-dot" style={{ background: l.color }} />
            <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {l.name}
            </span>
            <span
              className="icon-btn"
              role="button"
              title="删除列表"
              onClick={(e) => {
                e.stopPropagation();
                deleteList(l.id);
              }}
            >
              <TrashIcon width={13} height={13} />
            </span>
          </button>
        ))}

        {groupedLists.map(({ group, lists: gl }) => (
          <div key={group.id}>
            <div className="nav-section-label">
              <span>{group.name}</span>
              <button
                className="icon-btn"
                onClick={() => deleteGroup(group.id)}
                title="删除分组"
              >
                <TrashIcon width={13} height={13} />
              </button>
            </div>
            {gl.map((l) => (
              <button
                key={l.id}
                className={`nav-item ${nav.kind === "list" && nav.listId === l.id ? "active" : ""}`}
                onClick={() => setNav({ kind: "list", listId: l.id })}
              >
                <span className="nav-dot" style={{ background: l.color }} />
                <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {l.name}
                </span>
                <span
                  className="icon-btn"
                  role="button"
                  title="删除列表"
                  onClick={(e) => {
                    e.stopPropagation();
                    deleteList(l.id);
                  }}
                >
                  <TrashIcon width={13} height={13} />
                </span>
              </button>
            ))}
          </div>
        ))}

        {lists.length === 0 && groups.length === 0 && (
          <div style={{ padding: "4px 12px", fontSize: 12, color: "var(--text-disabled)" }}>
            还没有列表，点右上角 + 新建
          </div>
        )}

        <div className="nav-section-label">其他</div>
        <button
          className={`nav-item ${nav.kind === "deleted" ? "active" : ""}`}
          onClick={() => setNav({ kind: "deleted" })}
        >
          <span className="nav-icon">
            <FlagIcon />
          </span>
          最近删除
        </button>
        <div className="sidebar-footer">
          <button
            className="nav-item"
            onClick={cycleTheme}
            title={`主题：${theme === "system" ? "跟随系统" : theme === "light" ? "浅色" : "深色"}（点击切换）`}
          >
            <span className="nav-icon">
              {theme === "system" ? <MonitorIcon /> : theme === "light" ? <SunIcon /> : <MoonIcon />}
            </span>
            {theme === "system" ? "跟随系统" : theme === "light" ? "浅色模式" : "深色模式"}
          </button>
        </div>
      </div>

      {showNewList && (
        <div className="modal-backdrop" onClick={() => setShowNewList(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>新建列表</h3>
            <input
              type="text"
              placeholder="列表名称"
              value={name}
              autoFocus
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && submitNewList()}
            />
            <div className="color-picker">
              {LIST_COLORS.map((c) => (
                <button
                  key={c}
                  className={`color-swatch ${color === c ? "selected" : ""}`}
                  style={{ background: c }}
                  onClick={() => setColor(c)}
                />
              ))}
            </div>
            <div style={{ marginTop: 12 }}>
              <select
                value={groupId ?? ""}
                onChange={(e) => setGroupId(e.target.value ? Number(e.target.value) : null)}
                style={{ width: "100%", padding: "7px 10px", borderRadius: 8, border: "1px solid var(--border)", background: "var(--bg-input)" }}
              >
                <option value="">无分组</option>
                {groups.map((g) => (
                  <option key={g.id} value={g.id}>
                    {g.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="modal-actions">
              <button className="btn" onClick={() => setShowNewList(false)}>
                取消
              </button>
              <button className="btn btn-primary" onClick={submitNewList}>
                创建
              </button>
            </div>
          </div>
        </div>
      )}

      {showNewGroup && (
        <div className="modal-backdrop" onClick={() => setShowNewGroup(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>新建分组</h3>
            <input
              type="text"
              placeholder="分组名称"
              value={groupName}
              autoFocus
              onChange={(e) => setGroupName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && submitNewGroup()}
            />
            <div className="modal-actions">
              <button className="btn" onClick={() => setShowNewGroup(false)}>
                取消
              </button>
              <button className="btn btn-primary" onClick={submitNewGroup}>
                创建
              </button>
            </div>
          </div>
        </div>
      )}
    </aside>
  );
}
