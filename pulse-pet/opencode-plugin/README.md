# PulsePet opencode 插件

监听 opencode 官方 hooks → 归一化 kind → POST `/state` 到 PulsePet 桌面 App，驱动宠物动画。

## 安装

```bash
# macOS / Linux
./install.sh

# Windows（PowerShell）
.\install.ps1
```

安装脚本会：

1. 拷贝 `pulse-pet-hook.js` 到 `~/.config/opencode/plugins/`（Windows：`%APPDATA%\opencode\plugins\`）；
2. 在 `opencode.json` / `opencode.jsonc` 的 `plugin` 数组合并 `"pulse-pet"` 一项（带
   `// --pulse-pet-managed` 标记），JSONC 感知——注释与尾逗号保留，用户原有 plugin 项不动；
3. 重复安装幂等（不会产生重复项）。

> 依赖 `node` 做 JSONC 感知的配置合并（仅安装期）；插件本体在 opencode 的 Bun 运行时运行。

## 卸载

```bash
./install.sh --uninstall     # macOS / Linux
.\install.ps1 -Uninstall     # Windows
```

只移除带 `--pulse-pet-managed` 标记的插件项 + 删除插件文件；用户原有 plugin 项保留。

## 行为

- **App 未启动 / 已退出时静默**：endpoint / token 文件缺失、连接拒绝、超时、401 一律静默
  跳过（不打日志、不报错给 opencode 终端），并以指数退避（首次立即重试，之后 1s→2s→5s→30s
  封顶）避免高频事件打爆日志；文件重新出现后下次事件即恢复立即投递。
- **killswitch**：`~/.pulsepet/runtime/hooks-disabled`（Windows `%LOCALAPPDATA%\pulsepet\runtime\`）
  存在时插件整体跳过，删除后立即恢复（无需重启 opencode）。
- **端口回退**：插件每次发请求前读最新 `endpoint` 文件，PulsePet 换端口后无需重装插件。

## 状态复位（TC-EV-05 实测结论）

基于 opencode 1.18.18 + `@opencode-ai/plugin` 1.17.13 实测：

- `tool.execute.after` 存在（`input: { tool, sessionID, callID, args }`）→ 主复位信号，
  把 `editing`/`testing` 拉回 `working`。
- `chat.message` 存在（`input: { sessionID, agent, model, messageID, variant }`）→ `thinking`；
  opencode 无独立的「chat.message 完成」事件。
- 兜底复位：`event` bus 的 `session.status`（`status.type ∈ {idle, busy, retry}`，非 idle →
  `working`）；专用 `session.idle` 事件 → `idle`。
- App 侧另有 30s 瞬态超时兜底（Rust `session_state`）。

## 隐私

事件仅经内存 HTTP 传递（`127.0.0.1` + token），插件**不明文落盘**；命令行内容仅用于归一化
分类，不发送给宠物；气泡文案只来自白名单语音池，不展示原始 prompt/输出/路径/URL/secret。
