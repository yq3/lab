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

## PlantUML 渲染（流程图）

仓库内文档（如 `.opencode/README.md`）用 ```puml 代码块嵌图。已验证可用的本地渲染流程（2026-08-12）：

- **下载 jar**（本机有 java，无需 brew/graphviz；api.github.com 下载 29MB 会超时，用阿里云 maven 镜像）：
  ```bash
  curl -sL -o plantuml.jar https://maven.aliyun.com/repository/central/net/sourceforge/plantuml/plantuml/1.2026.6/plantuml-1.2026.6.jar
  ```
- **语法验证**（改完 puml 必跑，exit 0 = 通过）：
  ```bash
  java -jar plantuml.jar -checkonly file.puml
  ```
- **渲染 SVG**（输出文件名取自 `@startuml <name>`，不是输入文件名）：
  ```bash
  java -jar plantuml.jar -tsvg -o out/ file.puml   # 产物在 out/<@startuml名>.svg
  ```

踩坑记录（都实测过）：

- **在线渲染服务不可用**：`plantuml.com` 匿名请求被拒（连官方示例 URL 都返回 400）；`kroki.io` 的 plantuml 后端同样返回错误页。别用在线服务验证语法。
- **在线错误页是 HTTP 200**：plantuml.com 语法错误返回 200 + 错误文案图片（"The plugin you are using seems to generated a bad URL"），只判断 200 会误判成功。同理，服务器要求的编码是自定义 base64 表（`0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_`），标准 base64 会解出乱码。
- **活动图（activity 简单语法）不支持 `note bottom`**：会报 `syntax error? (assumed diagram type: activity)`（VS Code 插件旧 jar 同样报错）；note 位置受限，用 `:文本;` 活动节点或图下文字替代。
- **SVG 里中文以 HTML 实体存储**（如 `&#21542;` = 否，`&#65292;` = 全角逗号），验证渲染内容时用 grep 实体而非中文字面。
- VS Code 预览 puml 需装插件 `jebbs.plantuml`（本地 java 渲染）；插件内置 jar 较旧，用标准语法（while/if/break）最稳。
