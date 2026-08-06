# AGENTS.md

个人实验室：多个实验性 App / POC 的汇聚仓库（见 README.md）。

## 项目结构

- 每个实验 App 在仓库根目录下各占一个独立目录，彼此无依赖，各自是完整的单体项目（自带技术栈、依赖和配置）。
- 不同 App 的技术栈和业务可能完全不同：动手前先看该目录自身的配置文件，不要假设全仓有统一技术栈或框架。
- 每个 App 本质是一个 POC：效果验证通过后，可能拆出去单独建仓继续演进，所以目录应保持自包含、独立可运行。

## 工作约定

- 仓库没有统一的 build / test / lint / typecheck 工具链。执行任何命令前先检查对应目录内的配置文件，不要臆测。
- 代码是实验性的、可随时丢弃：无 CI、无发布、无稳定性保证。
- 默认开发分支是 `develop`（不是 `main`）。
- 除非用户明确要求，否则开发完成后不要提交到 GitHub（不要 commit / push）。
- **Git 推送必须用 SSH**：本机 keychain 无 GitHub HTTPS 凭据，HTTPS push 会报认证错误。remote 已配置为 `git@github.com:yq3/lab.git`，请勿改回 HTTPS。推送到 GitHub 前先确认 `ssh -T git@github.com` 可用（首次可能需 `ssh-add ~/.ssh/id_ed25519`）。
- 发布流程：push tag `todo-lite-v*`（如 `git tag todo-lite-v0.1.0 && git push origin todo-lite-v0.1.0`）触发 `.github/workflows/build.yml`，在 GitHub Actions 上构建 Windows / macOS 安装包并挂到 draft Release。

## GitHub CLI（gh）

- 已安装（v2.97.0，2026-07-31），但**不在默认 PATH 里**：二进制在 `$HOME/install/gh_2.97.0_macOS_arm64/bin/gh`，PATH 是通过 `~/.zshrc` 加的，非交互式 shell（如 opencode 的 bash 工具）不会加载 `.zshrc`。
  - 使用前先 `export PATH="$HOME/install/gh_2.97.0_macOS_arm64/bin:$PATH"`，或直接调用完整路径。
- 已登录 GitHub 账号 `yq3`（凭据存系统 keychain，git 操作用 SSH）。
- **网络环境**：`api.github.com` 通畅；`github.com` 网页和 `raw.githubusercontent.com` 经常超时（webfetch / curl 直连会卡）。因此：
  - 查 GitHub 仓库、README、文件树、文件内容优先用 `gh api`（如 `gh api repos/{owner}/{repo}/contents/{path}` 返回 base64 内容，`gh api repos/{owner}/{repo}/readme` 同理）。
  - 需要整仓细读时用 `git clone --depth 1 git@github.com:{owner}/{repo}`（SSH 已验证可用）到 `/var/folders/9k/4ts9r9n92737zx0fjkqtrnym0000gn/T/opencode/`（macOS 系统临时目录下 opencode 预创建的工作区，等价 `/tmp` 且对工具有访问权限；每次按 `仓库名-时间戳` 建子目录，用完即弃）再本地 grep。
