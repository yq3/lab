import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { initHttpBridge } from "./lib/http-bridge";
import { initReminderBridge } from "./lib/reminder-bridge";
import { initAtlasBridge } from "./lib/atlas-bridge";
import { initInteractionBridge } from "./lib/interaction";
import { initSizeBridge } from "./lib/size-bridge";
import { initTodoBridge } from "./lib/todo-bridge";
import { initToolBubbleBridge } from "./lib/tool-bubble-bridge";
import { initI18n } from "./lib/i18n";
import "./styles/tokens.css"; // v2 M2 设计系统 token 层（先于组件层）
import "./styles/global.css";

// M8：i18n 初始化（读持久化语言 → 无则跟随系统；订阅 ui://language 三窗口同步）。
void initI18n();
// M2：启动时接入 Rust 事件链路（监听 pulsepet://state → petStore）。
void initHttpBridge();
// M4：提醒事件链路（监听 reminder://trigger → 气泡 / 烟花；仅 pet 路由生效）。
void initReminderBridge();
// M5：atlas 链路（pet 路由拉 atlas_meta/pixels → petStore；监听 atlas://changed 热替换）。
void initAtlasBridge();
// M6：交互模式链路（查询穿透状态 + 监听 pulsepet://pass-through → petStore；
// pet 的拖拽/右键守卫与 panel 设置页开关都依赖该状态位）。
void initInteractionBridge();
// §十一（V2-OPEN-ITEMS）：宠物大小档位链路（查询 pet.size + 监听 pet://size
// → petStore；pet 的 canvas/CSS 尺寸与 panel 设置页分段控件都依赖该状态位）。
void initSizeBridge();
// M7：todo 完成联动（监听 todo://completed → waving + 气泡；仅 pet 路由生效）。
void initTodoBridge();
// v2 M3：工具级气泡链路（pet：get 初始化开关 store + 监听 pulsepet://tool-bubble
// 透传与 pulsepet://tool-broadcast 开关广播；非 Tauri 环境直接返回）。
void initToolBubbleBridge();

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
