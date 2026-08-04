import { useEffect, useMemo, useRef, useState } from "react";
import {
  DndContext,
  closestCenter,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  verticalListSortingStrategy,
  useSortable,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { listen } from "@tauri-apps/api/event";
import { useTaskStore } from "../store/useTaskStore";
import { useUIStore } from "../store/useUIStore";
import { useListsStore } from "../store/useListsStore";
import type { Section, SortMode, TaskWithTags } from "../types";
import { TaskItem } from "./TaskItem";
import { PlusIcon, SearchIcon, TrashIcon, RotateCcwIcon } from "./Icons";

const SMART_TITLES: Record<string, string> = {
  "my-day": "我的某天",
  important: "重要",
  planned: "计划",
  scheduled: "已安排",
  "no-date": "无日期",
  completed: "已完成",
  all: "全部任务",
};

function SortableTask({ task, selected, onSelect, onToggleComplete, onDelete }: {
  task: TaskWithTags;
  selected: boolean;
  onSelect: (id: number) => void;
  onToggleComplete: (task: TaskWithTags) => void;
  onDelete: (task: TaskWithTags) => void;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: task.id,
  });
  return (
    <div
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition, opacity: isDragging ? 0.5 : 1 }}
      {...attributes}
      {...listeners}
    >
      <TaskItem task={task} selected={selected} onSelect={onSelect} onToggleComplete={onToggleComplete} onDelete={onDelete} />
    </div>
  );
}

export function TaskList() {
  const { tasks, load, addTask, toggleComplete, reorder, restoreTask, purgeTask, deleteTask, error } = useTaskStore();
  const {
    nav,
    showCompleted,
    sortMode,
    setSortMode,
    toggleShowCompleted,
    selectedTaskId,
    selectTask,
    search,
    setSearch,
    closeSearch,
    searchFocus,
    searchOpen,
    quickAddFocus,
  } = useUIStore();
  const { lists, sectionsByList, reloadSections } = useListsStore();
  const [newTitle, setNewTitle] = useState("");
  const searchRef = useRef<HTMLInputElement>(null);
  const quickAddRef = useRef<HTMLInputElement>(null);
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 4 } }));

  const list = nav.kind === "list" ? lists.find((l) => l.id === nav.listId) : null;
  const title = search
    ? "搜索"
    : nav.kind === "list"
      ? list?.name ?? ""
      : nav.kind === "deleted"
        ? "最近删除"
        : SMART_TITLES[nav.id] ?? "";

  useEffect(() => {
    load({ nav, showCompleted, sortMode, search: search || undefined });
  }, [nav, showCompleted, sortMode, search, load]);

  useEffect(() => {
    if (nav.kind === "list") reloadSections(nav.listId);
  }, [nav, reloadSections]);

  useEffect(() => {
    if (searchFocus > 0) searchRef.current?.focus();
  }, [searchFocus]);

  useEffect(() => {
    if (quickAddFocus > 0) quickAddRef.current?.focus();
  }, [quickAddFocus]);

  useEffect(() => {
    let unlisten: (() => void) | null = null;
    listen("todo://quick-add", () => {
      useUIStore.getState().focusQuickAdd();
    }).then((fn) => {
      unlisten = fn;
    });
    return () => {
      unlisten?.();
    };
  }, []);

  const sections: Section[] = nav.kind === "list" ? (sectionsByList[nav.listId] ?? []) : [];

  const grouped = useMemo(() => {
    if (nav.kind !== "list" || sections.length === 0 || search) return null;
    const map = new Map<number | null, TaskWithTags[]>();
    for (const s of sections) map.set(s.id, []);
    map.set(null, []);
    for (const t of tasks) {
      const key = t.section_id ?? null;
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(t);
    }
    return Array.from(map.entries()).filter(([, ts]) => ts.length > 0);
  }, [tasks, sections, nav, search]);

  const quickAdd = async () => {
    const t = newTitle.trim();
    if (!t) return;
    await addTask({ listId: nav.kind === "list" ? nav.listId : null, title: t, myDay: nav.kind === "smart" && nav.id === "my-day" });
    setNewTitle("");
  };

  const onKeyDown = (e: KeyboardEvent) => {
    const ui = useUIStore.getState();
    const taskStore = useTaskStore.getState();
    if (e.key === "Escape") {
      if (ui.searchOpen) ui.closeSearch();
      else ui.toggleDetail(false);
      return;
    }
    const tag = (e.target as HTMLElement).tagName;
    const isTyping = tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
    if (isTyping || !taskStore.tasks.length) return;
    const idx = taskStore.tasks.findIndex((t) => t.id === ui.selectedTaskId);
    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        ui.selectTask(taskStore.tasks[Math.min(idx + 1, taskStore.tasks.length - 1)].id);
        break;
      case "ArrowUp":
        e.preventDefault();
        ui.selectTask(taskStore.tasks[Math.max(idx - 1, 0)].id);
        break;
      case "Enter":
        e.preventDefault();
        const cur = taskStore.tasks.find((t) => t.id === ui.selectedTaskId);
        if (cur) ui.selectTask(cur.id);
        break;
      case " ":
        e.preventDefault();
        const spaceCur = taskStore.tasks.find((t) => t.id === ui.selectedTaskId);
        if (spaceCur) taskStore.toggleComplete(spaceCur);
        break;
      case "t":
      case "T":
        if (e.metaKey || e.ctrlKey) {
          e.preventDefault();
          quickAddRef.current?.focus();
        }
        break;
      case "f":
      case "F":
        if (e.metaKey || e.ctrlKey) {
          e.preventDefault();
          useUIStore.getState().focusSearch();
        }
        break;
    }
  };

  useEffect(() => {
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const onDragEnd = (e: DragEndEvent) => {
    const { active, over } = e;
    if (!over || active.id === over.id || sortMode !== "manual" || search) return;
    const activeTask = tasks.find((t) => t.id === active.id);
    const overTask = tasks.find((t) => t.id === over.id);
    if (!activeTask || !overTask) return;

    if (grouped) {
      if (activeTask.section_id !== overTask.section_id) return;
      const sectionTasks = tasks.filter((t) => t.section_id === activeTask.section_id);
      const oldIndex = sectionTasks.findIndex((t) => t.id === active.id);
      const newIndex = sectionTasks.findIndex((t) => t.id === over.id);
      const next = [...sectionTasks];
      const [moved] = next.splice(oldIndex, 1);
      next.splice(newIndex, 0, moved);
      const orderedBySection = [
        ...sections.map((s) => next.filter((t) => t.section_id === s.id)),
        next.filter((t) => t.section_id === null),
      ].flat();
      reorder(orderedBySection.map((t) => t.id));
      return;
    }

    const oldIndex = tasks.findIndex((t) => t.id === active.id);
    const newIndex = tasks.findIndex((t) => t.id === over.id);
    const next = [...tasks];
    const [moved] = next.splice(oldIndex, 1);
    next.splice(newIndex, 0, moved);
    reorder(next.map((t) => t.id));
  };

  const renderTasks = (items: TaskWithTags[]) =>
    sortMode === "manual" && nav.kind !== "deleted" && !search ? (
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
        <SortableContext items={items.map((t) => t.id)} strategy={verticalListSortingStrategy}>
          {items.map((t) => (
            <SortableTask
              key={t.id}
              task={t}
              selected={selectedTaskId === t.id}
              onSelect={(id) => selectTask(id)}
              onToggleComplete={toggleComplete}
              onDelete={(t) => deleteTask(t.id)}
            />
          ))}
        </SortableContext>
      </DndContext>
    ) : (
      items.map((t) => (
        <div key={t.id} className="task-item-wrap">
          <TaskItem
            task={t}
            selected={selectedTaskId === t.id}
            onSelect={(id) => selectTask(id)}
            onToggleComplete={toggleComplete}
            onDelete={nav.kind === "deleted" ? undefined : (t) => deleteTask(t.id)}
          />
          {nav.kind === "deleted" && (
            <div className="task-item-actions">
              <button
                className="header-btn"
                onClick={() => restoreTask(t.id)}
                title="恢复任务"
              >
                <RotateCcwIcon width={13} height={13} />
                恢复
              </button>
              <button
                className="header-btn danger"
                onClick={() => purgeTask(t.id)}
                title="永久删除"
              >
                <TrashIcon width={13} height={13} />
              </button>
            </div>
          )}
        </div>
      ))
    );

  const onPaneClick = (e: React.MouseEvent) => {
    const el = e.target as HTMLElement;
    if (el.closest(".task-item") || el.closest("input, textarea, select, button")) return;
    useUIStore.getState().toggleDetail(false);
  };

  return (
    <section className="task-pane">
      <header className="task-header">
        <h2>{title}</h2>
        <div className="task-meta">
          <span className="count">{tasks.length} 项</span>
          <div className="header-actions">
            {(searchOpen || search) && (
              <div className="search-box">
                <SearchIcon width={13} height={13} />
                <input
                  ref={searchRef}
                  placeholder="搜索任务…"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Escape") {
                      e.stopPropagation();
                      closeSearch();
                    }
                  }}
                />
                <button className="search-clear" onClick={closeSearch}>
                  ✕
                </button>
              </div>
            )}
            {!searchOpen && (
              <button className="header-btn" onClick={() => useUIStore.getState().focusSearch()} title="搜索 (⌘F)">
                <SearchIcon width={13} height={13} />
              </button>
            )}
            {nav.kind === "deleted" && (
              <button className="header-btn" onClick={() => useTaskStore.getState().purgeAllDeleted()}>
                清空
              </button>
            )}
            {nav.kind !== "deleted" && (
              <>
                <select
                  className="header-btn"
                  value={sortMode}
                  onChange={(e) => setSortMode(e.target.value as SortMode)}
                  title="排序方式"
                >
                  <option value="manual">手动排序</option>
                  <option value="priority">按重要性</option>
                  <option value="due">按截止日期</option>
                  <option value="created">按创建时间</option>
                  <option value="alpha">按字母顺序</option>
                </select>
                <button
                  className={`header-btn ${showCompleted ? "active" : ""}`}
                  onClick={toggleShowCompleted}
                >
                  已完成
                </button>
              </>
            )}
          </div>
        </div>
      </header>

      <div className="task-scroll" onClick={onPaneClick}>
        {nav.kind !== "deleted" && !search && (
          <div className="quick-add">
            <PlusIcon width={15} height={15} style={{ color: "var(--text-disabled)" }} />
            <input
              ref={quickAddRef}
              placeholder={`添加任务到"${title}"`}
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && quickAdd()}
            />
          </div>
        )}

        {tasks.length === 0 ? (
          <div className="empty-state">
            <div className="emoji">{search ? "🔍" : nav.kind === "deleted" ? "🗑️" : "🎉"}</div>
            <p>
              {error
                ? `加载失败: ${error}`
                : search
                  ? `没有匹配"${search}"的任务`
                  : nav.kind === "deleted"
                    ? "没有已删除的任务"
                    : "这里很清静，添加一个任务开始吧"}
            </p>
            {!search && nav.kind !== "deleted" && (
              <button className="btn btn-primary empty-cta" onClick={() => quickAddRef.current?.focus()}>
                添加任务
              </button>
            )}
          </div>
        ) : grouped ? (
          grouped.map(([sectionId, items]) => {
            const section = sections.find((s) => s.id === sectionId);
            return (
              <div key={sectionId ?? "unsectioned"}>
                <div className="section-header">
                  {section?.name ?? "任务"}
                  <span className="count">{items.length}</span>
                </div>
                {renderTasks(items)}
              </div>
            );
          })
        ) : (
          renderTasks(tasks)
        )}
      </div>
    </section>
  );
}
