# PulsePet Windows 开发环境搭建指南（新手向）

> 本文假设你几乎没配置过开发环境：所有命令都可以直接**复制、粘贴进 PowerShell、回车**执行。
>
> - 预计总耗时：1~2 小时（大部分时间在等下载和编译，挂机即可）
> - 磁盘预留：至少 20 GB
> - 遇到报错先别慌：翻到文末「常见问题排查（FAQ）」，大概率有现成解法
> - 本文写于 2026-08，文中版本号、界面文字以实际为准

---

## 0. 两个基本操作（先学会再往下走）

### 0.1 打开 PowerShell

本文所有命令都在 PowerShell 里运行：

1. 按键盘 `Win` 键（Ctrl 和 Alt 中间那个窗户图标）；
2. 直接输入 `powershell`；
3. 回车，打开一个蓝色或黑色窗口。

个别命令建议用**管理员身份**运行（本文会逐条标注），方法：按 `Win + X` → 选「终端(管理员)」或「Windows PowerShell(管理员)」→ 弹出确认框时点「是」。

粘贴：在 PowerShell 窗口里直接 `Ctrl+V`，或点鼠标右键即可粘贴。

### 0.2 「装完软件要重开窗口」——最重要的一条新手须知

每装完一个软件，它注册的环境变量只对**新开的**窗口生效。所以本文的节奏永远是：

**装完 → 关掉当前窗口 → 重新开一个 → 再验证**

如果装完立刻验证提示「无法识别」，99% 是没重开窗口。

---

## 1. 先检查：哪些已经装了

新开一个 PowerShell，逐条运行（每条一行，回车看结果）：

```powershell
node --version
npm --version
git --version
rustc --version
cargo --version
```

对照结果：

- 输出了版本号（如 `v22.x.x`）→ 已安装，跳过对应小节；
- 提示「无法将 "xxx" 项识别为 cmdlet、函数、脚本文件…」→ 没装，去第 2 章对应小节装。

---

## 2. 安装环境（5 个小节，按顺序来）

> 顺序很重要：**先装 2.2 的 Visual Studio 生成工具，再装 2.3 的 Rust**——Rust 安装器会自动检测前者。

### 2.1 Node.js（前端工具的运行时）

**为什么需要**：项目的依赖安装（npm）、开发服务器（Vite）、测试（vitest）都跑在 Node 上。

```powershell
winget install OpenJS.NodeJS.LTS
```

**验证**（重开窗口）：`node --version` 有版本号即可（v22 或更高都行）。

### 2.2 Visual Studio 2022 生成工具 + C++（最重的一步，约 7 GB，等 10~30 分钟）

**为什么需要**：Rust 编译出的程序要用微软的链接器（link.exe）；项目内嵌的 SQLite 数据库要用 C 编译器现场编译。

**方式 A（推荐：图形界面点选，直观不易错）**

1. 浏览器打开官方下载地址：https://aka.ms/vs/17/release/vs_BuildTools.exe （会直接下载一个安装器）；
2. 双击运行，弹出 UAC 确认框点「是」；
3. 等它出现一个蓝色的「Visual Studio Installer」窗口；
4. 在「工作负荷」选项卡勾选第一项 **「使用 C++ 的桌面开发」**（英文系统叫 Desktop development with C++）；
5. 点右下角「安装」，默认勾选项都不用改，等进度条走完。

**方式 B（备选：一条命令全自动，无需点选）**

```powershell
winget install --id Microsoft.VisualStudio.2022.BuildTools --override "--quiet --wait --norestart --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"
```

（普通窗口运行即可，弹 UAC 点「是」；之后就是安静等待。）

**验证**（两种方式通用，重开窗口）：

```powershell
Test-Path "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Tools\MSVC"
```

输出 `True` 即安装成功。

### 2.3 Rust（桌面壳的编译器）

**为什么需要**：PulsePet 是 Tauri 应用，桌面部分用 Rust 写、Rust 编译。

```powershell
winget install Rustlang.Rustup
```

- 过程中若出现 `Proceed with standard installation? ...` 之类的选择提示，直接回车（选默认的标准安装）；
- 若提示缺少 Visual C++ 相关组件，说明 2.2 没装好，回去重做。

**验证**（重开窗口）：

```powershell
rustc --version
cargo --version
rustup show
```

三条都有输出，且 `rustup show` 里能看到 `stable-x86_64-pc-windows-msvc` 字样即可。

### 2.4 Git + GitHub SSH 密钥（下载代码 / 以后推送代码）

**安装 Git**：

```powershell
winget install Git.Git
```

一路默认；装完重开窗口，`git --version` 有输出即可。

顺手做两个全局配置（防止 Windows 换行符和长路径的坑）：

```powershell
git config --global core.autocrlf true
git config --global core.longpaths true
```

**生成 SSH 密钥并登记到 GitHub**（本仓库规定用 SSH 方式下载和推送）：

第 1 步，看是否已有密钥：

```powershell
Test-Path "$env:USERPROFILE\.ssh\id_ed25519.pub"
```

输出 `True` → 直接跳到第 2 步；输出 `False` → 先生成一个（三个提问都不用输入，一路回车）：

```powershell
ssh-keygen -t ed25519 -C "windows-dev"
```

第 2 步，复制公钥到剪贴板：

```powershell
Get-Content "$env:USERPROFILE\.ssh\id_ed25519.pub" | Set-Clipboard
```

第 3 步，浏览器打开 https://github.com/settings/ssh/new ：

- Title 随便填（比如 `windows-dev`）；
- Key 的大框里 `Ctrl+V` 粘贴；
- 点绿色按钮「Add SSH key」（可能要求输一次 GitHub 密码或验证码）。

第 4 步，验证连通（重开窗口）：

```powershell
ssh -T git@github.com
```

第一次会问 `Are you sure you want to continue connecting (yes/no)?` → 输 `yes` 回车。看到 `Hi xxx! You've successfully authenticated...` 就成功了。

（卡住或超时 → FAQ 第 3 条。）

### 2.5 WebView2 运行时（一般系统自带，检查一下即可）

**为什么需要**：Tauri 应用（含开发模式）用系统 WebView2 显示界面。Win10 / Win11 基本都预装了。

```powershell
Test-Path "${env:ProgramFiles(x86)}\Microsoft\EdgeWebView\Application"
```

输出 `True` → 不用管，环境到此配齐；输出 `False` 再执行：

```powershell
winget install Microsoft.WebView2Runtime
```

---

## 3. 下载代码

新开一个 PowerShell：

```powershell
mkdir C:\dev -Force          # 想放别处就换路径，后同
cd C:\dev
git clone git@github.com:yq3/lab.git
cd lab
git checkout develop         # 重要！见下方说明
cd pulse-pet
```

**关于 `git checkout develop`**：GitHub 上这个仓库默认展示的分支是 `main`，但日常开发都在 `develop` 分支。克隆下来默认是 `main`，必须执行这条切到 `develop`（如果提示 `already on 'develop'` 也正常）。

`lab` 是一个多项目仓库，我们只在其中的 `pulse-pet` 目录里工作。

---

## 4. 安装项目依赖

确认当前在 `C:\dev\lab\pulse-pet`，运行：

```powershell
npm ci
```

约 1~3 分钟。它按 `package-lock.json` 精确安装所有前端依赖到 `node_modules\`（这个目录不进版本库，每台新机器都要装一次）。

（下载很慢或报网络错误 → FAQ 第 4 条：换国内 npm 镜像。）

---

## 5. 自检：跑一次测试

```powershell
npm test
```

看到 vitest 输出 `Test Files xx passed (xx)` 即通过——前端环境 OK。

（可选）Rust 侧也有单元测试：

```powershell
cd src-tauri
cargo test
cd ..
```

第一次会下载并编译几百个依赖包，耗时 5~20 分钟属正常现象，之后会快很多。

---

## 6. 日常开发：把 App 跑起来

```powershell
npm run tauri dev
```

- 第一次要编译整个 Rust 工程（5~20 分钟，控制台滚动大量信息是正常的）；
- 成功后：宠物窗口弹出 + 系统托盘出现小猫图标（Win11 若托盘没看到，点任务栏右下角的 `^` 展开隐藏图标）；
- 弹出防火墙提示时点「允许」（App 会在本机 127.0.0.1 起一个事件接收端口）；
- 窗口保持运行别关：改前端代码即时生效；改 Rust 代码会自动重编译并重启 App；
- 结束开发：在 PowerShell 里按 `Ctrl + C`。

常用热键：面板 `Ctrl+Shift+P`、点击穿透 `Ctrl+Shift+Alt+P`。

**（可选）接入 agent 状态**——想让宠物随 opencode / Claude Code 的工作状态切换动画，装一次事件插件即可：

```powershell
cd C:\dev\lab\pulse-pet\opencode-plugin
powershell -ExecutionPolicy Bypass -File .\install.ps1
cd ..
```

装完**重启 opencode** 生效；Claude Code 的接入不用命令行，在 App 里操作：设置 → 接入管理 → 一键安装。

---

## 7. 打一个 Windows 安装包

```powershell
npm run tauri build
```

首次约 10~40 分钟。成功后产物在（版本号目录名以实际为准）：

| 文件 | 说明 |
|---|---|
| `src-tauri\target\release\bundle\nsis\PulsePet_0.2.4_x64-setup.exe` | 安装包（分发用这个） |
| `src-tauri\target\release\bundle\msi\PulsePet_0.2.4_x64_en-US.msi` | MSI 格式安装包 |

- 双击 `setup.exe` 安装；若弹出 SmartScreen 蓝色提示「已保护你的电脑」→ 点「更多信息」→「仍要运行」（安装包没有付费代码签名，属正常现象）；
- 每次重新 build 都会覆盖旧产物，不会越积越多（同一个 target 目录）。

---

## 8. 常见问题排查（FAQ）

按报错关键词对号入座：

**1. 刚装完软件，验证时还是提示「无法识别」**
→ 关掉窗口重开（原因见 0.2）。还不行就是安装失败了，重跑对应安装命令。

**2. 提示 `winget` 无法识别**
→ 系统太老。打开 Microsoft Store（开始菜单搜「Store」）→ 搜「应用安装程序」→ 更新；或浏览器打开 https://aka.ms/getwinget 下载安装。

**3. `ssh -T git@github.com` 卡住不动 / `git clone` 超时**
→ 网络到 GitHub 的 SSH（22 端口）不通，改走 443 端口。运行：

```powershell
notepad "$env:USERPROFILE\.ssh\config"
```

（提示新建文件就点「是」）粘贴以下 4 行并保存，然后重试：

```
Host github.com
  HostName ssh.github.com
  Port 443
  User git
```

**4. `npm` 下载慢 / 网络错误**
→ 换国内镜像源后重新 `npm ci`（想换回官方：`npm config delete registry`）：

```powershell
npm config set registry https://registry.npmmirror.com
```

**5. cargo 下载极慢 / 报 `transfer too slow` / 长时间停在同一行**
→ 先试禁用 HTTP/2：在**同一个**窗口依次执行（设置只对当前窗口有效，设完就在这个窗口里跑构建命令）：

```powershell
$env:CARGO_HTTP_MULTIPLEXING = "false"
$env:CARGO_HTTP2 = "false"
```

仍慢就换国内镜像。运行 `notepad "$env:USERPROFILE\.cargo\config.toml"`（提示新建文件点「是」），写入以下内容保存：

```toml
[source.crates-io]
replace-with = "rsproxy-sparse"

[source.rsproxy-sparse]
registry = "sparse+https://rsproxy.cn/index/"
```

**6. Rust 报 `linker 'link.exe' not found` 或 `MSVC ... required`**
→ 2.2 的 C++ 工作负载没装上。开始菜单搜「Visual Studio Installer」打开 → 找到「Visual Studio 2022 生成工具」点「修改」→ 勾选「使用 C++ 的桌面开发」→ 安装。

**7. cargo 报 nasm / 汇编相关错误**（概率很低）
→ 装 NASM 并手动加 PATH：

```powershell
winget install nasm.nasm
```

然后：按 `Win` 键搜「编辑系统环境变量」→ 点「环境变量」→ 在**上下两个列表**里都找 `Path` → 选中点「编辑」→「新建」→ 填 `C:\Program Files\NASM` → 一路「确定」。重开窗口后 `nasm -v` 验证。

**8. Vite 报 1430 端口被占用**
→ 找到占用者并结束它（第一条命令输出最后一列是进程号，替换 `<进程号>`）：

```powershell
netstat -ano | findstr :1430
taskkill /PID <进程号> /F
```

**9. App 运行异常，想看日志**
→ 日志文件位置：`%LOCALAPPDATA%\pulsepet\pulsepet.log`。打开资源管理器，把这段路径原样粘到地址栏回车即可跳到所在文件夹。

**10. 杀毒软件 / Windows Defender 删文件、报毒、编译莫名失败**
→ 把代码目录加入排除项：打开「Windows 安全中心」→ 病毒和威胁防护 → 管理设置 → 排除项 → 添加文件夹 → 选 `C:\dev\lab`。

**11. 编译报「路径 / 文件名过长」**
→ 确认 2.4 的 `git config --global core.longpaths true` 执行过；仍报错就用**管理员** PowerShell 运行下面这条并重启电脑（全局允许长路径）：

```powershell
reg add "HKLM\SYSTEM\CurrentControlSet\Control\FileSystem" /v LongPathsEnabled /t REG_DWORD /d 1 /f
```

---

## 9. 附录

### 9.1 高频命令速查（都在 `C:\dev\lab\pulse-pet` 目录下运行）

| 想做什么 | 命令 |
|---|---|
| 拉取最新代码 | `git pull` |
| 开发运行 App | `npm run tauri dev` |
| 前端测试 | `npm test` |
| Rust 测试 | `cd src-tauri; cargo test; cd ..` |
| 打安装包 | `npm run tauri build` |
| 依赖坏了重装 | 删除 `node_modules` 文件夹后再 `npm ci` |

### 9.2 文件位置速查（Windows）

| 内容 | 位置 |
|---|---|
| 项目代码 | `C:\dev\lab\pulse-pet` |
| 主数据库 | `%APPDATA%\com.pulsepet.app\pulsepet.db` |
| 运行日志 | `%LOCALAPPDATA%\pulsepet\pulsepet.log` |
| 事件接收 token | `%LOCALAPPDATA%\pulsepet\runtime\` |
| opencode 插件 | `%APPDATA%\opencode\plugins\pulse-pet-hook.js` |
| Claude Code hook 脚本 | `%LOCALAPPDATA%\pulsepet\hooks\` |
| 构建产物 | `src-tauri\target\release\bundle\` |

> `%APPDATA%`、`%LOCALAPPDATA%` 这类路径：直接粘到资源管理器地址栏回车即可跳转。

### 9.3 全局热键（Windows 版）

| 热键 | 作用 |
|---|---|
| `Ctrl+Shift+P` | 显示 / 隐藏控制面板 |
| `Ctrl+Shift+Alt+P` | 开 / 关点击穿透 |
| `Ctrl+Shift+Alt+F` | 调试烟花（仅开发构建有效） |
