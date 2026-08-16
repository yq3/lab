import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { initHttpBridge } from "./lib/http-bridge";
import { initReminderBridge } from "./lib/reminder-bridge";
import "./styles/global.css";

// M2：启动时接入 Rust 事件链路（监听 pulsepet://state → petStore）。
void initHttpBridge();
// M4：提醒事件链路（监听 reminder://trigger → 气泡 / 烟花；仅 pet 路由生效）。
void initReminderBridge();

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
