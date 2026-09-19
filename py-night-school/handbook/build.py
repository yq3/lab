#!/usr/bin/env python3
"""py-night-school 在线阅读站构建器。

units/ 下的课程 Markdown 是唯一事实源（check_lesson.py 仍以它为校验对象）；
本脚本把源文件「暂存 + 轻转换」到 .stage/docs/，再交给 mkdocs-material 渲染到 dist/。
不要手改 .stage/ 与 dist/——它们是产物；改源文件后重跑本脚本。

转换清单（只作用于围栏代码块之外）：
  1. 剥离首个 `# ` 一级标题 → 写入 frontmatter title（页面标题由主题渲染）；
  2. 六段式 `## N. 标题` → 数字章 + 标题（数字走 CSS content，TOC 文本不受污染）；
  3. 结尾段「离毕业又近的一块」→ 包进灯卡容器；
  4. 表头命中「你熟悉的 X 物 / 今天的 Y 物」定式（或 Java/Python 关键词）的表
     → 包进 jp-table 并标注列位（X 侧橙、Y 侧蓝，Unit 3+ 框架对照表同样适用）；
  5. 相对链接 `.../README.md` → 目录链接；指向仓外（../research 等）的链接解包为纯文字。

用法：
    uv sync                        # 首次
    uv run build.py                # 构建全部单元到 dist/
    uv run build.py unit0-toolchain  # 只构建指定单元（原型阶段）
    uv run build.py --serve        # 构建并本地预览 http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HANDBOOK = Path(__file__).resolve().parent
ROOT = HANDBOOK.parent
STAGE_DOCS = HANDBOOK / ".stage" / "docs"
DIST = HANDBOOK / "dist"
MKDOCS_YML = HANDBOOK / "mkdocs.yml"

FINAL_HEADING_RE = re.compile(r"^## 离毕业又近[了的]?一块[ \t]*$", re.M)
# 方向契约（impeccable：随构建产物留存，可审计——dist 任一页 grep「DESIGN CONTRACT」）
DESIGN_CONTRACT = """<!--
DESIGN CONTRACT 「素纸双主题」v4 · code-led（品牌锚不变：夜/灯/橙蓝语义/衬线标题）
THESIS: 在线讲义是一册素纸书——单一表面、零装饰零动效；深/浅双主题由读者自选；
拒绝封面夜空动效与深浅混搭（v3 已废）。
OWN-WORLD: 浅色 = 素纸（#ffffff × 墨 #232936），深色 = 夜（#0d1322 × 星墨 #dde4f2）；
细铅线分隔；Java 橙 / Python 蓝只承担信息（对照表列、代码语言顶边、链接）；
琥珀只给灯卡与读数；宋体标题、黑体正文、等宽代码；零图片零外链零动画。
STORY: 读者选一种眼睛舒服的模式，像读一本书一样顺序读完一讲。
FIRST VIEWPORT: 扉页式主页（衬线大题 + 副题 + 两枚安静按钮 + 目次表）；内页衬线标题起头，正文 ~840px。
FORM: 既定品牌内的素化重做（surface-scope，code-led），参考 ddia.vonng.com 的朴实书感（仅 UI 气质）。
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance.
-->
"""
# 行尾锚必须是 [ \t]*$ 而非 \s*$：\s 会吃掉块尾换行（split_fences 在围栏处切块，
# 标题块以「）\n\n」结尾时贪婪 \s*$ 吞掉全部换行，替换串无换行 → 标题与下一个
# 围栏 ``` 粘连成一行，围栏失效（CURRICULUM.md 曾因此 3 处模板内容泄漏进 TOC）。
SEG_RE = re.compile(r"^## (\d)\.[ \t]*(.+?)[ \t]*$", re.M)
H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.M)
MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

# 列语义识别：表头单元格命中哪一侧的关键词（小写子串匹配）。
# 「你熟悉的 X 物 / 今天的 Y 物」是全课表头定式——X 侧恒为旧世界（Java 及其生态），
# Y 侧恒为新世界（Python / 框架 / mini-agent），Unit 3+ 的框架课同样命中。
JAVA_WORDS = ("你熟悉的", "java", "jvm", "jdk", "jshell", "junit", "maven", "pom", "spring", "jar", "sdkman", "idea")
PY_WORDS = ("今天的", "python", "pyproject", "pytest", "pyright", "pydantic", "uv", "ruff", "pip", "venv", "jupyter", "mini-agent")


# ---------------------------------------------------------------- 源文件分块

def split_fences(text: str) -> list[tuple[bool, str]]:
    """按围栏代码块切分为 [(是否代码块, 文本块), ...]——一切转换只落在代码块外。"""
    parts: list[tuple[bool, str]] = []
    buf: list[str] = []
    code = False
    for line in text.splitlines(keepends=True):
        if not code and line.lstrip().startswith("```"):
            parts.append((False, "".join(buf)))
            buf = [line]
            code = True
        elif code and line.lstrip().startswith("```"):
            buf.append(line)
            parts.append((True, "".join(buf)))
            buf = []
            code = False
        else:
            buf.append(line)
    parts.append((code, "".join(buf)))
    return parts


def map_outside_fences(text: str, fn: str) -> str:
    """对非代码块内容应用字符串变换 fn（整段进出，保持块顺序拼回）。"""
    return "".join(chunk if is_code else fn(chunk) for is_code, chunk in split_fences(text))


# ---------------------------------------------------------------- 各项转换

def seg_chips(text: str) -> str:
    return SEG_RE.sub(
        r'## <span class="segno" data-n="\1" aria-hidden="true"></span>'
        r'<span class="segtitle">\2</span> {: .seg data-seg="\1"}',
        text,
    )


def wrap_final_note(text: str) -> str:
    # 逐块累计偏移，找到标题所在的绝对位置（只在非代码块里找）
    pos = -1
    offset = 0
    for is_code, chunk in split_fences(text):
        if not is_code:
            m = FINAL_HEADING_RE.search(chunk)
            if m:
                pos = offset + m.start()
                break
        offset += len(chunk)
    if pos == -1:
        return text
    head, tail = text[:pos], text[pos:]
    return f'{head}<div class="final-note" markdown>\n\n{tail}\n\n</div>\n'


def jp_columns(header_line: str) -> tuple[int, int] | None:
    cells = [c.strip().lower() for c in header_line.strip().strip("|").split("|")]

    def col_with(words: tuple[str, ...]) -> int | None:
        return next((k + 1 for k, c in enumerate(cells) if any(w in c for w in words)), None)

    jc, pc = col_with(JAVA_WORDS), col_with(PY_WORDS)
    if jc and pc and jc != pc:
        return jc, pc
    return None


def wrap_jp_tables(text: str) -> str:
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    i = 0
    while i < len(lines):
        if lines[i].lstrip().startswith("|"):
            j = i
            while j < len(lines) and lines[j].lstrip().startswith("|"):
                j += 1
            block = lines[i:j]
            cols = jp_columns(block[0])
            if cols:
                out.append(f'<div class="jp-table" data-java-col="{cols[0]}" data-python-col="{cols[1]}" markdown>\n')
                out.extend(block)
                out.append("</div>\n")
            else:
                out.extend(block)
            i = j
        else:
            out.append(lines[i])
            i += 1
    return "".join(out)


def rewrite_links(text: str) -> str:
    def repl(m: re.Match[str]) -> str:
        label, target = m.group(1), m.group(2)
        if target.startswith(("http://", "https://", "#", "mailto:")):
            return m.group(0)
        if target.startswith("../"):
            return label  # 仓外引用（research 等）不进站：解链接保文字
        fixed = re.sub(r"^(\./)?(.*?/)README\.md$", r"\2index.md", target)
        return f"[{label}]({fixed})"

    return MD_LINK_RE.sub(repl, text)


def transform(body: str) -> str:
    body = map_outside_fences(body, seg_chips)
    body = map_outside_fences(body, wrap_jp_tables)
    body = map_outside_fences(body, rewrite_links)
    body = wrap_final_note(body)
    return body


# ---------------------------------------------------------------- 暂存与导航

FM_RE = re.compile(r"\A---\n(.*?)\n---\n", re.S)


def stage_page(src: Path, dst: Path, title_override: str | None = None) -> str:
    """暂存一篇 MD（应用全部转换），返回页面标题。源文件若带 frontmatter，
    其 hide 列表会被合并进生成的 frontmatter（落地页的 hide: navigation/toc）。"""
    text = src.read_text(encoding="utf-8")
    hide: list[str] = []
    if m := FM_RE.match(text):
        for line in m.group(1).splitlines():
            if (item := line.strip().removeprefix("- ").strip()) and line.startswith((" ", "-")):
                hide.append(item)
        text = text[m.end():]
    m = H1_RE.search(text)
    title = title_override or (m.group(1) if m else src.parent.name)
    if m:
        text = text[: m.start()] + text[m.end():]  # 剥离一级标题，页面标题交给主题
    fm = f"title: {title}\n"
    if hide:
        fm += "hide:\n" + "".join(f"  - {h}\n" for h in hide)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(f"---\n{fm}---\n{DESIGN_CONTRACT}{transform(text)}", encoding="utf-8")
    return title


def short_label(title: str) -> str:
    """导航短标签：课时全标题截到冒号/括号前（侧栏与 tab 用；页面大标题不受影响）。"""
    return re.split(r"[：（(]", title, 1)[0].strip()


def build_nav(staged: dict[str, dict[str, str]]) -> str:
    lines = ["  - 首页: index.md", "  - 课表: curriculum.md"]
    for ukey in sorted(staged):
        unit = staged[ukey]
        tab, pages = unit["tab"], unit["pages"]
        lines.append(f"  - {json.dumps(tab, ensure_ascii=False)}:")
        for label, path in pages:
            lines.append(f"      - {json.dumps(short_label(label), ensure_ascii=False)}: {path}")
    return "\n".join(lines)


def write_mkdocs_yml(nav: str) -> None:
    MKDOCS_YML.write_text(
        f"""# 由 build.py 生成——不要手改；改源文件后重跑构建。
site_name: Python Night School
site_description: 写给 Java 工程师的 Python Agent 开发晚课
copyright: Python Night School · Python 夜校 · 以 Java 心智模型为桥
docs_dir: .stage/docs
site_dir: dist

theme:
  generator: false               # 页脚不显示主题署名
  name: material
  custom_dir: .stage/overrides   # 覆盖 header.html：去 logo、站名可点击回首页
  language: zh
  font: false                    # 宪法：不外链 CDN，字体走系统栈（night.css 定义）
  palette:
    - media: "(prefers-color-scheme: light)"
      scheme: default
      primary: custom
      accent: custom
      toggle:
        icon: material/weather-night
        name: 切换到夜间模式
    - media: "(prefers-color-scheme: dark)"
      scheme: slate
      primary: custom
      accent: custom
      toggle:
        icon: material/weather-sunny
        name: 切换到日间模式
  features:
    # 不用 navigation.sections：单元走 Material 原生可折叠嵌套导航
    # （桌面 = chevron 折叠开关，默认只展开所在单元；抽屉 = 层级钻取）。
    # 单元开合跨页记忆 + 首帧前恢复见 overrides/partials/nav.html 的内联脚本
    - navigation.top
    - navigation.tracking
    - toc.follow
    - content.code.copy
    - search.highlight
    - search.suggest

markdown_extensions:
  - attr_list
  - md_in_html
  - admonition
  - pymdownx.details
  - pymdownx.superfences
  - pymdownx.highlight:
      anchor_linenums: true
  - pymdownx.inlinehilite
  - pymdownx.tabbed:
      alternate_style: true
  - toc:
      permalink: true
      toc_depth: 3

extra:
  generator: false                # material 9.7 页脚「Made with」检查的是 extra.generator

extra_css:
  - assets/stylesheets/night.css

nav:
{nav}
""",
        encoding="utf-8",
    )


# ---------------------------------------------------------------- 主流程

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("units", nargs="*", help="只构建这些单元目录名（如 unit0-toolchain）；缺省 = 全部")
    ap.add_argument("--serve", action="store_true", help="构建后启动本地预览（Ctrl-C 退出）")
    args = ap.parse_args()

    unit_dirs = sorted((ROOT / "units").glob("unit*-*"))
    if args.units:
        wanted = set(args.units)
        unit_dirs = [u for u in unit_dirs if u.name in wanted]
        missing = wanted - {u.name for u in unit_dirs}
        if missing:
            print(f"未找到单元目录：{', '.join(sorted(missing))}", file=sys.stderr)
            return 2

    # 干净重建暂存区
    if STAGE_DOCS.exists():
        shutil.rmtree(STAGE_DOCS)
    STAGE_DOCS.mkdir(parents=True)
    shutil.copytree(HANDBOOK / "src" / "assets", STAGE_DOCS / "assets")
    shutil.copytree(HANDBOOK / "src" / "overrides", HANDBOOK / ".stage" / "overrides",
                    dirs_exist_ok=True)

    # 落地页 + 课表（落地页也走 stage_page：带方向契约注释；无 h1/六段/表格，转换全部空转）
    stage_page(HANDBOOK / "src" / "index.md", STAGE_DOCS / "index.md", title_override="Python 夜校")
    stage_page(ROOT / "CURRICULUM.md", STAGE_DOCS / "curriculum.md", title_override="课表 · 30 讲")

    staged: dict[str, dict] = {}
    for unit_dir in unit_dirs:
        ukey = unit_dir.name.split("-", 1)[0]  # unit0-toolchain -> unit0
        unit_title = stage_page(unit_dir / "README.md", STAGE_DOCS / ukey / "index.md")
        short = re.sub(r"^Unit \d+\s*", "", unit_title).split("：")[0]
        num = unit_dir.name.split("-", 1)[0].removeprefix("unit")
        tab = f"Unit {num} · {short}"
        pages: list[tuple[str, str]] = [("单元导读", f"{ukey}/index.md")]
        for lesson in sorted(p for p in unit_dir.iterdir() if p.is_dir() and p.name.startswith("L")):
            title = stage_page(lesson / "README.md", STAGE_DOCS / ukey / lesson.name / "index.md")
            pages.append((title, f"{ukey}/{lesson.name}/index.md"))
        milestone = unit_dir / "milestone"
        if milestone.is_dir():
            title = stage_page(milestone / "README.md", STAGE_DOCS / ukey / "milestone" / "index.md")
            pages.append((f"里程碑 · {short}", f"{ukey}/milestone/index.md"))
        staged[ukey] = {"tab": tab, "pages": pages}

    write_mkdocs_yml(build_nav(staged))

    mkdocs = shutil.which("mkdocs") or str(HANDBOOK / ".venv" / "bin" / "mkdocs")
    # material 9.7.2+ 会打印 MkDocs 2.0（预发布、不兼容）迁移警告；我们钉在 1.x，静音之
    env = {**os.environ, "NO_MKDOCS_2_WARNING": "1"}
    cmd = [mkdocs, "build", "-f", str(MKDOCS_YML), "--clean"]
    print(f"$ {' '.join(cmd)}")
    if subprocess.run(cmd, cwd=HANDBOOK, env=env).returncode != 0:
        return 1
    n_pages = len(list(DIST.rglob("*.html")))
    print(f"OK：{n_pages} 个页面 → {DIST}/")
    if args.serve:
        cmd = [mkdocs, "serve", "-f", str(MKDOCS_YML)]
        print(f"$ {' '.join(cmd)}  （改动 units/ 后需重跑 build.py 刷新暂存区）")
        return subprocess.run(cmd, cwd=HANDBOOK, env=env).returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
