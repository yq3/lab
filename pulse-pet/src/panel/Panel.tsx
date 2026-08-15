export default function Panel() {
  return (
    <div className="panel">
      <h1>PulsePet 控制面板</h1>
      <p>
        M1 骨架占位页。后续里程碑将在此挂载：Token 统计（M3）、提醒配置（M4）、
        设置（宠物选择 / 穿透 / 烟花，M5/M6）、Todo 插件（M7）。
      </p>
      <ul>
        <li>Token 统计 — M3</li>
        <li>提醒配置 — M4</li>
        <li>设置（宠物选择 / 穿透 / 烟花全局开关）— M5/M6</li>
        <li>Todo 插件 — M7</li>
      </ul>
    </div>
  );
}
