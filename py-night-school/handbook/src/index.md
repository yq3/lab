---
title: Python 夜校
hide:
  - navigation
  - toc
---

<!-- 扉页：站内页面（不属于 units/ 课程源，不参与 check_lesson 校验）。文案取自仓库 README.md。 -->

<div class="ns-cover">
<h1 class="ns-title">Python Night School</h1>
<p class="ns-sub">Python 夜校——写给 Java 工程师的 Python Agent 开发晚课：以 agent 开发为场景学 Python，以 Java 心智模型为桥，一个学期从语言核心学到金融合规毕业设计。</p>
<p class="ns-meta">6 学段 · 30 讲 · 练习即测试 · 金融合规毕业设计</p>
<p class="ns-cta"><a class="ns-btn ns-btn--primary" href="unit0/">从 Unit 0 开始</a><a class="ns-btn" href="curriculum/">先看课表</a></p>
</div>

## 目次

| 学段 | 主题 | 讲次 |
|---|---|---|
| [Unit 0](unit0/) | 起步：环境与工具链 | L0.1 |
| [Unit 1](unit1/) | Python 语言核心 · Java 对照 | L1.1 – L1.9 + 里程碑 |
| [Unit 2](unit2/) | 无框架手写 mini-agent | L2.1 – L2.5 + 里程碑 |
| [Unit 3](unit3/) | 框架四重奏 | L3.1 – L3.8 + 里程碑 |
| [Unit 4](unit4/) | 开源产品实战 | L4.1 – L4.3 + 里程碑 |
| [Unit 5](unit5/) | 毕业设计 | L5.1 – L5.4 + 里程碑 |

## 这门课的六个不一样

<div class="ns-feats">
<div class="ns-feat">
<h4>Java 心智桥</h4>
<p>概念先给「Java 对应物 + 关键差异」对照表再动手；每个陷阱按「现象 / 最小复现 / Java 直觉为何失效 / 修复」四段命名化拆解。</p>
</div>
<div class="ns-feat">
<h4>练习即测试</h4>
<p>每课练习是带 TODO 的代码，<code>uv run pytest</code> 全绿即过关。八个头部教程解剖的结论：练习验收是全行业空白——这是我们的核心差异。</p>
</div>
<div class="ns-feat">
<h4>对照组教学</h4>
<p>Unit 2 先手写 ~300 行 mini-agent，之后每个框架课都回来对照「这层抽象替我付掉了什么」。</p>
</div>
<div class="ns-feat">
<h4>源码路标</h4>
<p>每课延伸给出 <code>仓库@commit#路径</code> 精确导读——学框架同时学读生产级 Python 源码。</p>
</div>
<div class="ns-feat">
<h4>双贯穿线</h4>
<p>明线「报销单审查」从第一课种下、四大框架同题重做；暗线财务 agent 毕业设计每课长一块。</p>
</div>
<div class="ns-feat">
<h4>夜校纪律</h4>
<p>中文原创、模型端点中立、每课独立 uv 项目锁定依赖、克隆即学——竞品的系统性短板在这里默认不发生。</p>
</div>
</div>

## 讲义在这里的读法

课程源文件是仓库里的 Markdown（单一事实源，机器校验的对象）；这个阅读站把它渲染成更适合晚上读的形态。下面三个组件对应教学机制的三个主张，讲义将逐课采用。

**对照即颜色**：Java 物与 Python 物在站内各有固定颜色（橙 / 蓝），对照表的列、代码块的语言顶边同套着色——

=== "Maven · pom.xml"

    ```xml
    <dependencies>
      <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <scope>test</scope>
      </dependency>
    </dependencies>
    ```

=== "uv · pyproject.toml"

    ```toml
    [dependency-groups]
    dev = ["pytest>=8", "ruff>=0.8", "pyright>=1.1"]
    ```

**渐进披露**：hints 三级提示在纸面上是平铺的（一眼扫到第 3 级就泄底），在站内逐级折叠——想 5 分钟再点开：

??? note "第 1 级 · 方向"

    Python 的「块」由什么界定？花括号吗？——想想缩进层级决定代码归属。

??? tip "第 2 级 · 形状"

    缩进层级 == 块归属。检查出错那行的缩进与谁对齐：`def` 体？`if` 分支？

??? success "第 3 级 · 做法（接近完整的参考）"

    统一 4 空格一层，`def` 体整体缩进；提交前 `uv run ruff format .` 一键归一——但格式化器永远不会改写字符串内容。

**每课一格灯**：每讲结尾的「离毕业又近的一块」渲染成灯卡，进度拼图逐课点亮（演示：完成 L0.1 后的第一格）——

<div class="final-note">
<p class="ns-cells-label">1 / 30 讲</p>
<div class="ns-cells">
<i class="on"></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i>
</div>
<h2>离毕业又近的一块</h2>
<p><code>preapprove()</code> 就是毕业设计「fail-closed 执行门」里<strong>限额检查</strong>的雏形（纯函数、整数分、可参数化测试）。到 Unit 5 你会把它升级成检查链——今晚你已经写下了最后一环的种子。</p>
</div>

## 练习在哪里

阅读站只负责「读」。练习在仓库里：每课目录是独立 uv 项目，`uv sync` 后 `uv run pytest` 全绿即毕业——三命令验收、hints 渐进、参考答案分离，这些机制都以文件形态躺在课时目录里，克隆即学。

> 全部 6 学段 44 页已上线；课程内容以仓库 `units/` 的 Markdown 为唯一事实源，改源文件后重跑构建即可。右上角的月亮 / 太阳可切换夜间 / 日间模式。
