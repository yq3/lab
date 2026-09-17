# handbook —— 在线阅读站（原型）

`units/` 的课程 Markdown 是**唯一事实源**（`scripts/check_lesson.py` 与三态验证仍以它为对象）；
本目录是自包含的 uv 项目，负责「暂存 + 轻转换 → mkdocs-material 渲染」。这是 AGENTS.md §7
「远期才做：在线阅读站」的提前落地（原型阶段）。

> 时间线与踩坑实录见文末两节——**改本目录任何东西之前先读踩坑实录**，里面的坑全部真实踩过。

## 用法

```bash
cd py-night-school/handbook
uv sync                          # 首次；国内网络先 export UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple
uv run build.py unit0-toolchain  # 只构建 Unit 0
uv run build.py                  # 全部单元（6 学段 44 页）
uv run build.py --serve          # 构建并预览 http://127.0.0.1:8000（见踩坑 #8：不用 mkdocs serve）
```

产物在 `dist/`（gitignore）；`.stage/` 是暂存副本（gitignore）；`mkdocs.yml` 由
`build.py` 生成（gitignore）。**改课程内容永远改 `units/` 下的源文件**，然后重跑构建——
不要手改 `.stage/`、`dist/`、`mkdocs.yml`。

本地预览推荐静态服务（重建不会弄死服务）：

```bash
uv run build.py && python3 -m http.server 8347 -d dist
```

## 架构决策（变更前先读）

1. **MD 单一事实源，HTML 是构建产物**。不手写 HTML、不双份维护；`check_lesson.py`
   的六段式机器校验对象不变。链接分叉即维护崩盘，此为第一原则。
2. **构建期转换而非源文件改造**。课程 MD 保持「在编辑器/终端可读」（克隆即学不受影响），
   全部增强在 `.stage/` 副本上做，且**只作用于围栏代码块之外**：
   - 剥离 h1 → frontmatter title（页面标题交给主题）；
   - 六段式 `## N. 标题` → 琥珀数字章徽章 + 标题（`attr_list` 挂 class，TOC 文本不受污染）；
   - 结尾「离毕业又近的一块」→ 包进灯卡容器；
   - 表头命中「你熟悉的 X 物 / 今天的 Y 物」定式（或 Java/Python 关键词）的表 → 包进
     jp-table 并实测标注列位（X 侧橙、Y 侧蓝；Unit 3+ 的框架对照表同样命中）；
   - 相对链接 `.../README.md` → `.../index.md`（mkdocs 原生认识）；指向仓外（`../research`）
     的链接解包为纯文字（research 是创作输入不进站）。
3. **宪法对齐**：`font: false`——不加载 Google Fonts 等任何 CDN 字体，字体走系统栈；
   全站零图片（夜空/灯光/印章均为 CSS），讲义图片本地化纪律天然满足；站点只读不存数据。
4. **版本锚定**：mkdocs-material 9.x（MIT，9.7.5 起钉 `mkdocs<2`——MkDocs 2.0 是不兼容的
   预发布重写，material 9.7.2+ 会打迁移警告，构建脚本用 `NO_MKDOCS_2_WARNING=1` 静音）。
   pymdown-extensions 12.x 的 tabbed 配置键是 `alternate_style`（旧文档的 `alternate` 已删）。
5. **设计系统 v2**（经历一轮推倒重做，见过程志）：夜色深蓝底 = 品牌（夜校）；
   Java 物橙 / Python 物蓝是**双语义强调色**（对照表列、代码块语言顶边同套着色）；
   灯光琥珀只给「离毕业又近的一块」仪式段。落地页 front-matter `hide: [navigation, toc]`
   做成全幅封面（衬线大标题 + 红印章落款 + 桥形连线）；正文栏靠覆盖 `.md-main__inner`
   的 61rem 上限放开到 72rem（≈936px）。
6. **Material 集成陷阱备忘**（写 CSS 前先读，详见踩坑实录 #4–#7）：
   - 背景变量是 `--md-default-bg-color`（带 `-dark` 后缀的写法不存在，写错则主题灰底漏出）；
   - `rem` 基于 Material 的 20px 根字号——侧栏宽 11.4rem ≈ 228px，不是常规浏览器语义；
   - `.md-typeset a` 等元素选择器特异性压过单类名，自定组件要写成 `.md-typeset a.ns-btn` 形态；
   - `generator: false` 是 `theme:` 下的键，放顶层会报 Unrecognised configuration；
   - 中文 CJK 长句搜索召回弱（lunr 默认空白分词），留待换索引方案。

## 目录

```
handbook/
├── build.py                     # 构建器：staging 转换 + 生成 mkdocs.yml + 调 mkdocs
├── src/
│   ├── index.md                 # 落地页（站内页面，非课程源，不参与 check_lesson）
│   └── assets/stylesheets/night.css
├── .stage/                      # 暂存副本（生成物，gitignore）
├── dist/                        # 站点产物（生成物，gitignore）
└── mkdocs.yml                   # 由 build.py 生成（gitignore）
```

## 制作过程志（2026-09-17，一个下午 + 一轮推倒重做）

### 第 0 步：定位讨论

起因是课程全部是 MD，人类阅读不友好。讨论确立第一原则：**HTML 是构建产物不是第二份内容**——
`check_lesson.py` 直接解析 README.md（六段式、bash 块 `&&`、commit 锚点），MD 降级为
「底稿」等于让质量流水线失去校验对象。HTML 的真实增益点也据此选定：hints 三级渐进披露
（MD 平铺会泄底）、Java↔Python 对照表排版、坑位四段式、暗线进度可视化。

### 第 1 步：设计方案

以 frontend-design 纪律先定 token 再动手：

- **色板**：夜色深蓝底 `#0a0f1b` × 双语义强调色——Java 物橙 `#e8935a`、Python 物蓝
  `#5ca8e5`，灯光琥珀 `#f2c14e` 只给仪式段，印章红 `#c14f3c` 只给落款。
  让「Java↔Python 桥」从教学主张变成视觉系统本身。
- **签名元素**：「离毕业又近的一块」灯照卡片 + 顶栏 active 标签的橙→蓝渐变桥形下划线。
- **字体**：全系统栈（宪法禁 CDN）；标题用宋体系衬线展示体，正文黑体系。
- **零图片**：夜空、灯光、星点全 CSS。

### 第 2 步：v1 实现（骨架 + 首轮自查）

- `build.py`：fence 感知的暂存转换器（一切正则替换只落在代码块外，CURRICULUM 的课时
  模板代码块不受影响）+ 生成 mkdocs.yml + 调 mkdocs。
- `night.css` v1 + 落地页（hero 卡片 + 三组件演示）+ Unit 0 构建。
- 自查（playwright-cli 截图 + 视觉严评）修掉：tabbed 扩展键名、TOC 混入卡片 h4
  （`toc_depth: 3`）、README.md 链接改写方式、课表页长标题。
- **中途一个重要调查**：构建时蹦出红色警告说 mkdocs-material「Currently unlicensed /
  Closed contribution model」——读官方博客弄清：那是 **MkDocs 核心 2.0 预发布**的罪状，
  material 9.7.x 仍 MIT 且已自动钉 `mkdocs<2`，虚惊一场，但要静音警告防止每次吓人。

### 第 3 步：用户差评 → 全页严评诊断

用户反馈「丑陋」。把落地页与课程页**整页长截图**下来做逐条严评，诊断收敛为三条：

1. **比例失衡**：正文栏 ~700px 两侧死空间、页面标题无分量、正文 12.6px 偏小；
2. **真 bug**：`--md-default-bg-color--dark` 是杜撰的变量名（正确为
   `--md-default-bg-color`），页面背景一直是主题默认灰黑而非设计的深海军蓝——「脏色」元凶；
3. **组件裸**：卡片纯色块、表格像默认 HTML、侧栏选中态几乎不可见。

### 第 4 步：v2 重做（设计系统推倒重来）

- 全局：字号 0.86rem（≈17px）/ 行距 2.0；氛围背景三层 fixed 渐变（星幕蓝顶 + 城市余光）；
  正文栏 936px（覆盖 `.md-main__inner` 61rem 上限 + 侧栏收窄）。
- 落地页：front-matter `hide: [navigation, toc]` 全幅封面化；衬线大标题（clamp 至 5.2rem）
  + 红印章「夜校」落款；桥形装饰改为「Java —●— Python」连线中点悬灯珠；六卡片固定 3×2；
  hero 底部地平线光带。
- 课程页：h1 衬线展示体；六段章加底部分隔线；侧栏选中态蓝底胶囊；TOC 左边线 + 当前项
  渐变指示条 + Step 子级缩进拉开；表格圆角容器 + 表头底色 + 行悬停；代码块加内边距、
  pygments 注释色提亮；Tab/折叠/灯卡全部加质感。
- 特异性修复：Material 的 `.md-typeset a` 压过单类名——自定按钮全部改写为
  `.md-typeset a.ns-btn` 形态（主按钮文字被染成链接色的 bug 即由此来）。
- 印章迭代：竖排（writing-mode）小尺寸溢出不可靠 → 改横排内容自适应。
- 检测补全：发现 Unit 3+ 表头是「你熟悉的 Java 物 / 今天的 openai-agents 物」变体，
  词表补「你熟悉的 / 今天的」定式后全站 34 张对照表全部命中着色。

### 第 5 步：验证

- 视觉：playwright-cli 截图（1440×900 首屏 / 长视口整页 / 390×844 移动端）× 视觉严评
  三轮全过；关键状态用 DOM 查证（侧栏 active、TOC scroll-spy、布局宽度实测 936px），
  不轻信截图目测。
- 管线：全量构建 44 页通过；jp-table 检出逐单元核对（unit1:14 / unit2:4 / unit3:8 /
  unit4:4 / unit5:4）；课程源文件零改动（git status 核验）。

## 踩坑实录（现象 → 根因 → 修法）

1. **非交互 shell 里 `uv` 不存在**：本机 uv 装在 `~/.local/bin`，靠 `.zshrc` 加 PATH，
   工具的非交互 bash 不加载。→ 命令前 `export PATH="$HOME/.local/bin:$PATH"`。
2. **uv sync 卡死**：非交互 shell 同样没有 `UV_DEFAULT_INDEX` 镜像变量，直连 PyPI 超慢。
   → 显式 `export UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple`（宪法 Step 2
   本来就写了，别忘系统变量不会自动继承）。
3. **`KeyError: 'alternate'`**：mkdocs.yml 里按旧文档写了 `pymdownx.tabbed: {alternate:
   true}`。pymdown-extensions 12.x 已删该键（alternate 是默认行为），现名
   `alternate_style`。且键名写错时 tabbed 组件不渲染 → 前端 JS 报
   `Missing element: expected ".tabbed-labels"`——**配置错误的症状出现在浏览器 console
   而不是构建期**，别被带偏去查前端。
4. **页面背景发灰**：`--md-default-bg-color--dark` 不存在（Material 变量没有这个后缀
   形态），写错 = 静默失效，slate 主题的灰黑底漏出来和设计的海军蓝叠加成脏色。
   → 用 `--md-default-bg-color`。教训：**覆盖主题变量前先在浏览器里验证变量名真实存在**。
5. **rem 不是我以为的 rem**：Material 把 html 根字号设为 20px（宽屏 12.5px→20px 阶梯），
   CSS 里 `13.4rem` 的侧栏实际是 268px，比默认还宽，正文反而变窄。→ 侧栏 11.4rem ≈ 228px。
6. **正文栏死活只有 ~700px**：不是侧栏的锅——`.md-main__inner` 被 Material 钉死
   `max-width: 61rem`。→ 覆盖为 72rem（`.md-header__inner`/`.md-tabs__inner` 同步，
   否则顶栏与内容错位）。
7. **自定组件被主题样式污染**：`.ns-btn--primary { color: … }`（特异性 0-1-0）压不过
   `.md-typeset a`（0-1-1），主按钮文字被主题链接色覆盖。→ 自定组件挂到内容上下文下写：
   `.md-typeset a.ns-btn--primary`。
8. **`mkdocs serve` 在本管线里没法用**：build.py 每次构建 `rmtree(.stage/)`，
   serve 的 watcher 失去监听目录直接崩。→ 预览改静态服务产物：`python3 -m http.server
   8347 -d dist`（重建不影响服务）。
9. **`generator: false` 报 Unrecognised configuration**：它是 `theme:` 的子键，放顶层
   无效。→ 挪进 `theme:` 块（页脚不再显示主题署名）。
10. **印章竖排溢出**：`writing-mode: vertical-rl` + 固定方形盒在小尺寸下字符计算超框，
    渲染成溢出的糊字。→ 放弃竖排，横排内容自适应盒 + padding，旋转 5° 保留印章感。
11. **L3.1 对照表没被着色**：表头是「你熟悉的 Java 物 / 今天的 openai-agents 物」，
    第二列不含任何 Python 关键词。→ 词表补「你熟悉的 / 今天的」全课表头定式
    （X 侧恒旧世界、Y 侧恒新世界），Unit 3+ 框架对照表全部命中。
12. **TOC 混入卡片小标题**：落地页六卡片的 h4 进了右侧目录且「01Java」无空格。
    → 全局 `toc_depth: 3` 卡掉 h4/h5；卡片标题补空格（顺带治了目录文本）。
13. **红色「unlicensed」警告虚惊**：material 9.7.2+ 每次构建打印 MkDocs 2.0 迁移警告。
    读官方博客确认被指控的是 MkDocs 2.0 预发布（不兼容重写），material 9.x 仍 MIT 且已
    钉 `mkdocs<2`。→ `NO_MKDOCS_2_WARNING=1` 静音，版本决策记录在架构决策 #4。
14. **链接改写首轮方式不对**：把 `x/README.md` 改写成 `x/` 导致 mkdocs 报 unrecognized
    relative link。→ 改写成 `x/index.md`（mkdocs 原生认识，目录 URL 由它规范化）。

## 已知限制（原型阶段）

- 中文搜索分词弱（lunr 默认按空白切分，CJK 长句召回差）——待引入 CJK tokenizer 或换索引方案。
- 单暗色主题（品牌即夜色）；亮色切换待做。
- 讲义内的 Tab / 折叠渐进披露组件目前只在落地页演示；课程 MD 逐课采用需要先在
  宪法 §3/§4 补约定（对照块语法、坑位折叠语法），避免各课各写一套。
- `uv.lock` 暂列 gitignore：这是构建工具链锁文件，是否随仓提交待拆仓时与课程
  纪律（课时项目 uv.lock 必须提交）统一口径后决定。
- `:has()` 选择器（落地页全幅布局）在旧浏览器降级为普通窄栏布局，可接受。
