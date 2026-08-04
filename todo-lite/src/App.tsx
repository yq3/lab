import { useEffect } from "react";
import { Sidebar } from "./components/Sidebar";
import { TaskList } from "./components/TaskList";
import { DetailPanel } from "./components/DetailPanel";
import { useListsStore } from "./store/useListsStore";
import { useUIStore } from "./store/useUIStore";
import { initDb } from "./lib/db";
import { startReminderLoop } from "./lib/reminders";
import "./styles/global.css";

function App() {
  const loadAll = useListsStore((s) => s.loadAll);
  const theme = useUIStore((s) => s.theme);

  useEffect(() => {
    (async () => {
      try {
        await initDb();
        await loadAll();
        startReminderLoop();
      } catch (e) {
        console.error("init failed", e);
      }
    })();
  }, [loadAll]);

  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () => {
      const dark = theme === "dark" || (theme === "system" && mq.matches);
      document.documentElement.dataset.theme = dark ? "dark" : "light";
    };
    apply();
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, [theme]);

  return (
    <div className="app">
      <Sidebar />
      <TaskList />
      <DetailPanel />
    </div>
  );
}

export default App;
