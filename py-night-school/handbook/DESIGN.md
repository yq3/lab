---
name: Python 夜校 · 在线阅读站
description: 素纸双主题——一册素纸书，浅色素纸 / 深色夜色由读者自选
colors:
  # 浅色（素纸，default）
  light-bg: "#ffffff"
  light-bg-alt: "#f6f5f0"
  light-line: "#e4e2d8"
  light-ink: "#232936"
  light-ink-2: "#5a6072"
  light-ink-3: "#8a8e9a"
  light-numeral: "#dcd7c8"
  light-code-bg: "#f6f5ef"
  # 深色（夜，slate）
  dark-bg: "#0d1322"
  dark-bg-alt: "#131b2e"
  dark-line: "#232f4e"
  dark-ink: "#dde4f2"
  dark-ink-2: "#97a2ba"
  dark-ink-3: "#6f7b96"
  dark-numeral: "#2c3a5e"
  dark-code-bg: "#0e1524"
  dark-hover: "#1a2540"
  print-ink: "#000000"
  # 双语义与灯（浅色用深读版 / 深色用亮饰版）
  java: "#a63e0b"
  java-bright: "#e8935a"
  java-edge: "rgba(200, 100, 40, 0.55)"
  python: "#1f6fb2"
  python-deep: "#175a92"
  python-bright: "#8ec2f2"
  python-sky: "#b3d5f8"
  lamp-ink: "#9a6a10"
  lamp: "#f2c14e"
  seal: "#c14f3c"
  grow: "#3f7d4e"
  code-comment-dark: "#7d8aac"
typography:
  display:
    fontFamily: "Songti SC, STSong, Source Han Serif SC, Noto Serif CJK SC, SimSun, serif"
    fontSize: "1.9rem"
    fontWeight: 900
    lineHeight: 1.4
    letterSpacing: "0.015em"
  display-mobile:
    fontFamily: "{typography.display.fontFamily}"
    fontSize: "1.5rem"
    fontWeight: 900
  cover:
    fontFamily: "{typography.display.fontFamily}"
    fontSize: "clamp(2.5rem, 6vw, 3.6rem)"
    fontWeight: 900
  section:
    fontFamily: "{typography.display.fontFamily}"
    fontSize: "1.42rem"
    fontWeight: 900
  lamp-title:
    fontFamily: "{typography.display.fontFamily}"
    fontSize: "1.32rem"
    fontWeight: 900
  h3:
    fontFamily: "{typography.body.fontFamily}"
    fontSize: "1.08rem"
    fontWeight: 700
  body:
    fontFamily: "PingFang SC, Hiragino Sans GB, Source Han Sans SC, Noto Sans CJK SC, Microsoft YaHei, system-ui, sans-serif"
    fontSize: "0.8rem"
    fontWeight: 400
    lineHeight: 1.92
    letterSpacing: "0.012em"
  ui:
    fontFamily: "{typography.body.fontFamily}"
    fontSize: "0.95rem"
  ui-lg:
    fontFamily: "{typography.body.fontFamily}"
    fontSize: "0.88rem"
  note-title:
    fontFamily: "{typography.body.fontFamily}"
    fontSize: "0.86rem"
  ui-md:
    fontFamily: "{typography.body.fontFamily}"
    fontSize: "0.78rem"
  ui-sm:
    fontFamily: "{typography.body.fontFamily}"
    fontSize: "0.68rem"
  body-mobile:
    fontFamily: "{typography.body.fontFamily}"
    fontSize: "0.84rem"
  ui-xs:
    fontFamily: "{typography.mono.fontFamily}"
    fontSize: "0.62rem"
  note-label:
    fontFamily: "{typography.mono.fontFamily}"
    fontSize: "0.74rem"
  cover-sub:
    fontFamily: "{typography.body.fontFamily}"
    fontSize: "clamp(0.98rem, 1.4vw, 1.1rem)"
  micro:
    fontFamily: "{typography.mono.fontFamily}"
    fontSize: "0.62rem"
  mono:
    fontFamily: "ui-monospace, SF Mono, Cascadia Code, Menlo, Consolas, monospace"
    fontSize: "0.8rem"
rounded:
  hair: "2px"
  cell: "3px"
  sm: "5px"
  md: "6px"
  nav: "7px"
  lg: "8px"
spacing:
  content-max: "40rem"
  section-gap: "3.1rem"
components:
  table-jp-java-col:
    backgroundColor: "var(--ns-java-wash)"
    textColor: "{colors.java}"
  table-jp-python-col:
    backgroundColor: "var(--ns-python-wash)"
    textColor: "{colors.python}"
  lamp-card:
    backgroundColor: "var(--ns-lamp-wash)"
    textColor: "{colors.lamp-ink}"
    rounded: "{rounded.lg}"
  quiet-button:
    backgroundColor: "transparent"
    textColor: "{light-ink}"
    rounded: "{rounded.lg}"
---

# DESIGN.md — 「素纸双主题」设计系统 v4

## Overview

在线讲义是一册素纸书：单一表面、零装饰、零动画。浅色（素纸，默认跟随系统）与
深色（夜色）由读者在顶栏自选，localStorage 记忆。参考 ddia.vonng.com 的朴实书感。
引擎 mkdocs-material 9.x；全部主题色彩由 `src/assets/stylesheets/night.css` 的
语义令牌（`--ns-*`）按 scheme 映射接管。零图片零外链（宪法）。

## Colors

- 两套同构令牌：浅 `light-*` / 深 `dark-*`（bg / bg-alt 洗底 / line 铅线 / ink 三级字 /
  numeral 幽灵数字 / code-bg）。组件样式只引用 `--ns-*` 语义名，不写主题字面量。
- **双语义色只承担信息**：Java 橙（对照表列、java/xml 代码顶边）、Python 蓝（链接、
  对照表列、python 代码顶边、当前项标记）；hover 用 deep/sky 变体。
- **琥珀只给灯**：灯卡标题与顶边、进度拼图点亮格、focus ring；不进正文强调。
- seal 只给 warning/danger；grow 只给 success。

## Typography

宋体系衬线（900）承担 h1/封面/章节/灯卡标题；黑体正文 0.855rem/1.92；等宽只用于
代码、读数与计量。正文栏 max 40rem（800px，16px 字号约 50 字/行，居中于等宽双栏之间）。UI 微字号（导航
0.62–0.78rem）用于侧栏/目录/tab 等骨架文字，不用于正文。

## Layout

内页三栏：左栏课程目录（单元 = 可折叠分组，所在单元常开，其余单元开合跨页记忆）+ 正文（42rem 居中）+ 右栏本页目录
（单行省略，当前项蓝色短标）。全局无顶栏 tab。扉页（落地页）hide 侧栏目录，
居中封面块 + 目次表 + 凡例。

## Elevation & Depth

无阴影系统（除代码块在深色下 1px 描边）。层次由铅线、洗底色与语义色承担。
全站零动画（呼吸灯已于 v4 移除）；reduced-motion 天然满足。

## Shapes

半径小而统一：2/5/7/8px。无玻璃拟态、无外发光；灯卡顶边 2px 琥珀线是唯一的
装饰性线条。

## Components

- **对照表（jp-table）**：构建脚本按表头实测标注列位；语义列 wash 底 + 顶边 2px 语义色。
- **灯卡（final-note）**：`--ns-lamp-wash` 底 + 琥珀 2px 顶边 + 衬线琥珀标题 + 进度拼图。
- **折叠/提示**：bg-alt 底 + 铅线；语义色只给图标与标题（note→python、tip→lamp、
  success→grow、warning/danger→seal）；Material per-type 标题底色需 scheme 前缀压制。
- **安静按钮**：铅线描边（hover 蓝描边）；主按钮 = 墨底反白，无光无影。
- **浏览器表面**：选区琥珀 wash、focus 琥珀、细滚动条。

## Do's and Don'ts

- **Do**：新组件只引用 `--ns-*` 语义令牌，两种 scheme 自动成立；先问「这是信息还是
  装饰」——装饰即删。
- **Do**：顶栏无 logo（站名文字即回首页链接，header.html override）；覆盖 Material 变量前在浏览器验证（已知陷阱：`--md-default-bg-color` 无
  `-dark` 后缀；`.md-typeset table:not([class])` 同形压制；`.md-typeset` 与
  `.md-content__inner` 同元素，`:has(...) .md-typeset X` 永不命中；pymdownx 类型类是
  `note/tip/success`；侧栏邻接边距规则带 `[dir=ltr]` 前缀（0-5-1），需同形后发压制才能居中正文）。
- **Don't**：不加眉题/kicker、不加动效、不加阴影辉光、不用无序列语义的编号装饰；
  课程 MD 永不改版式（一切呈现增强在构建期转换与 CSS）。
