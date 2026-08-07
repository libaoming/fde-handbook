#!/usr/bin/env python3
"""把 book/（v3 树）构建成多页 HTML 阅读站 → dist/site/

设计遵循 /teach 的方法：每节一个自含页面（短、可打印、Tufte 式排版）、
共享样式表组件（assets/style.css）、节编号自动互链（可查阅性）、
可选自测题（kit/quizzes/<节ID>.json → 页尾检索式 quiz，等长选项）。

用法：python3 kit/build-site.py        构建
      python3 kit/build-site.py --check 仅校验（figure 引用、页面数）
退出码：0=成功；1=任何 figure 引用断裂或 pandoc 失败。
输出判定标量：PAGES=<n> / FIGURES_INLINED=<n> / QUIZZES=<n> / VERDICT=SITE_BUILT
"""
import html
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BOOK = ROOT / "book"
OUT = ROOT / "dist" / "site"
QUIZ_DIR = ROOT / "kit" / "quizzes"

# (相对 book/ 的路径, 页面 ID, 部标签)
ORDER = [
    ("0-怎么用这本手册.md", "HOW", "第 0 部"),
    ("1-这份工作/ROL-01-角色定义.md", "ROL-01", "第 1 部 · 这份工作"),
    ("1-这份工作/ROL-02-相邻角色边界.md", "ROL-02", "第 1 部 · 这份工作"),
    ("1-这份工作/ROL-03-交付物清单.md", "ROL-03", "第 1 部 · 这份工作"),
    ("1-这份工作/ROL-04-全景图.md", "ROL-04", "第 1 部 · 这份工作"),
    ("2-交付生命周期/ENG-01-承接判定.md", "ENG-01", "第 2 部 · ENG 承接"),
    ("2-交付生命周期/ENG-02-成功标准.md", "ENG-02", "第 2 部 · ENG 承接"),
    ("2-交付生命周期/SUR-01-环境与语义勘察.md", "SUR-01", "第 2 部 · SUR 勘察"),
    ("2-交付生命周期/SUR-02-非工程域勘察.md", "SUR-02", "第 2 部 · SUR 勘察"),
    ("2-交付生命周期/BLD-03-链路迁移.md", "BLD-03", "第 2 部 · BLD 搭建"),
    ("2-交付生命周期/BLD-04-模型行为约束.md", "BLD-04", "第 2 部 · BLD 搭建"),
    ("2-交付生命周期/DEP-01-部署与切换.md", "DEP-01", "第 2 部 · DEP 上线"),
    ("2-交付生命周期/VER-01-验证前提.md", "VER-01", "第 2 部 · VER 签收"),
    ("2-交付生命周期/VER-02-切换验证.md", "VER-02", "第 2 部 · VER 签收"),
    ("2-交付生命周期/VER-03-可达性验证.md", "VER-03", "第 2 部 · VER 签收"),
    ("2-交付生命周期/VER-04-故障定位.md", "VER-04", "第 2 部 · VER 签收"),
    ("2-交付生命周期/VER-05-验收与签收.md", "VER-05", "第 2 部 · VER 签收"),
    ("2-交付生命周期/HND-01-移交.md", "HND-01", "第 2 部 · HND 移交"),
    ("3-验证纪律/DIS-01-证据分级.md", "DIS-01", "第 3 部 · 验证纪律"),
    ("3-验证纪律/DIS-02-三道焊缝.md", "DIS-02", "第 3 部 · 验证纪律"),
    ("3-验证纪律/DIS-03-助手产出验证.md", "DIS-03", "第 3 部 · 验证纪律"),
    ("3-验证纪律/DIS-04-事故台账.md", "DIS-04", "第 3 部 · 验证纪律"),
    ("附录/A-故障速查.md", "APPX-A", "附录"),
    ("附录/B-检查表汇编.md", "APPX-B", "附录"),
    ("附录/C-模板库.md", "APPX-C", "附录"),
]

PAGE_IDS = {pid for _, pid, _ in ORDER}
SECTION_TOKEN = re.compile(r"\b((?:ROL|ENG|SUR|BLD|DEP|VER|HND|DIS)-\d{2})\b")
APPX_TOKEN = {"附录 A": "APPX-A.html", "附录 B": "APPX-B.html", "附录 C": "APPX-C.html"}

stats = {"figures": 0, "quizzes": 0}


def md_to_html(path: Path) -> str:
    r = subprocess.run(
        ["pandoc", "-f", "markdown+east_asian_line_breaks", "-t", "html5",
         "--no-highlight", "--wrap=none", str(path)],
        capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"PANDOC_FAIL {path}: {r.stderr[:200]}")
    return r.stdout


def inline_svgs(fragment: str, src_md: Path) -> str:
    def repl(m):
        rel = m.group(1)
        svg_path = (src_md.parent / rel).resolve()
        if not svg_path.exists():
            sys.exit(f"BROKEN_FIGURE_REF {src_md.name}: {rel}")
        stats["figures"] += 1
        svg = svg_path.read_text()
        alt = m.group(2) or ""
        cap = f'<figcaption>{alt}</figcaption>' if alt else ""
        return f'<figure class="fig">{svg}{cap}</figure>'
    # pandoc: <img src="../figures/x.svg" alt="..." /> （可能被 <figure> 包裹）
    frag = re.sub(r'<img src="((?:\.\./)?figures/[^"]+\.svg)" alt="([^"]*)"[^>]*/?>', repl, fragment)
    # 去掉 pandoc 自带的空 figcaption 双层包裹
    frag = re.sub(r'<figure>\s*(<figure class="fig">.*?</figure>)\s*(?:<figcaption[^>]*>.*?</figcaption>)?\s*</figure>',
                  r'\1', frag, flags=re.S)
    return frag


def style_checklists(fragment: str) -> str:
    """```checklist 围栏 → 勾选卡。pandoc 产出 <pre class="checklist"><code>…</code></pre>"""
    def repl(m):
        text = html.unescape(m.group(1))
        items = []
        for line in text.rstrip("\n").split("\n"):
            if line.strip().startswith("[ ]"):
                items.append(f'<li><span class="box">☐</span>{html.escape(line.strip()[3:].strip())}</li>')
            else:
                items.append(f'<li class="cont">{html.escape(line.strip())}</li>')
        return '<div class="checklist"><ul>' + "".join(items) + "</ul></div>"
    return re.sub(r'<pre class="checklist"><code>(.*?)</code></pre>', repl, fragment, flags=re.S)


def linkify_sections(fragment: str, self_id: str) -> str:
    """正文里的节编号 → 页面互链（自身页面不自链；已有链接内不再嵌套）。"""
    parts = re.split(r'(<a\b.*?</a>|<h1\b.*?</h1>)', fragment, flags=re.S)
    out = []
    for i, part in enumerate(parts):
        if i % 2 == 1:
            out.append(part)
            continue
        def repl(m):
            pid = m.group(1)
            if pid == self_id or pid not in PAGE_IDS:
                return pid
            return f'<a class="xref" href="{pid}.html">{pid}</a>'
        part = SECTION_TOKEN.sub(repl, part)
        for zh, href in APPX_TOKEN.items():
            if f"APPX-{href[5]}" != self_id:
                part = part.replace(zh, f'<a class="xref" href="{href}">{zh}</a>')
        out.append(part)
    return "".join(out)


def quiz_block(pid: str) -> str:
    qf = QUIZ_DIR / f"{pid}.json"
    if not qf.exists():
        return ""
    data = json.loads(qf.read_text())
    stats["quizzes"] += 1
    payload = html.escape(json.dumps(data, ensure_ascii=False), quote=True)
    return (f'<section class="quiz" data-quiz="{payload}">'
            f'<h2>自测：先作答，再回看正文</h2>'
            f'<p class="quiz-note">检索式练习——凭记忆答，答错的那条就是该重读的小节。</p>'
            f'<div class="quiz-body"></div></section>'
            f'<script src="assets/quiz.js"></script>')


def page(pid, part, title, body, prev_link, next_link) -> str:
    nav_prev = f'<a href="{prev_link[0]}">← {prev_link[1]}</a>' if prev_link else "<span></span>"
    nav_next = f'<a href="{next_link[0]}">{next_link[1]} →</a>' if next_link else "<span></span>"
    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)} · FDE 手册</title>
<link rel="stylesheet" href="assets/style.css"></head>
<body><header class="top">
<a class="home" href="index.html">《FDE 手册》</a><span class="crumb">{html.escape(part)}</span>
</header>
<main>{body}</main>
<nav class="pager">{nav_prev}{nav_next}</nav>
<footer>案例三档强制标注 · 引文写作当轮核实 · <a href="https://github.com/libaoming/fde-handbook">GitHub 源仓库</a>（发现分档冒充或引文失实，请提 issue——那是本手册的红线）</footer>
</body></html>"""


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "assets").mkdir(exist_ok=True)
    for asset in (ROOT / "kit" / "site-assets").glob("*"):
        (OUT / "assets" / asset.name).write_text(asset.read_text())

    entries = []
    for rel, pid, part in ORDER:
        src = BOOK / rel
        if not src.exists():
            sys.exit(f"MISSING_SOURCE {rel}")
        frag = md_to_html(src)
        frag = inline_svgs(frag, src)
        frag = style_checklists(frag)
        frag = linkify_sections(frag, pid)
        m = re.search(r"<h1[^>]*>(.*?)</h1>", frag, flags=re.S)
        title = re.sub(r"<[^>]+>", "", m.group(1)) if m else pid
        entries.append((pid, part, title, frag))

    for i, (pid, part, title, frag) in enumerate(entries):
        prev_l = (f"{entries[i-1][0]}.html", entries[i-1][0]) if i > 0 else None
        next_l = (f"{entries[i+1][0]}.html", entries[i+1][0]) if i < len(entries) - 1 else None
        body = frag + quiz_block(pid)
        (OUT / f"{pid}.html").write_text(page(pid, part, title, body, prev_l, next_l))

    # index：旗帜句 + 双入口 + 全目录
    lifecycle_svg = (BOOK / "figures" / "rol04-lifecycle.svg").read_text()
    toc_parts, cur = [], None
    for pid, part, title, _ in entries:
        if part != cur:
            if cur is not None:
                toc_parts.append("</ul>")
            toc_parts.append(f"<h3>{html.escape(part)}</h3><ul>")
            cur = part
        toc_parts.append(f'<li><a href="{pid}.html">{html.escape(title)}</a></li>')
    toc_parts.append("</ul>")
    index = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FDE 手册 · AI 交付的现场手册</title>
<link rel="stylesheet" href="assets/style.css"></head>
<body><main class="index">
<h1>FDE 手册</h1>
<p class="tagline">市面上讲 FDE 的内容，大多在回答「这个岗位是什么、怎么入行」。<br>
这本手册回答的是下一个问题：<strong>上了客户现场之后，照着什么干活。</strong></p>
<p class="stance">立场一句话：<strong>AI 说做完了不算做完，判定标量说了才算。</strong></p>
<div class="entries">
<a class="entry" href="ROL-04.html"><h2>我在交付的哪一步？</h2><p>主线入口：六阶段与关口 →</p></a>
<a class="entry" href="APPX-A.html"><h2>我遇到了这个症状</h2><p>速查入口：按症状索引，直达处置 →</p></a>
</div>
<figure class="fig">{lifecycle_svg}</figure>
<div class="install"><p>给你的 coding agent 装上切换验真（fail-closed）：</p>
<pre>npx skills add libaoming/fde-handbook</pre></div>
<nav class="toc">{"".join(toc_parts)}</nav>
</main>
<footer>案例三档强制标注 · 引文写作当轮核实 · <a href="https://github.com/libaoming/fde-handbook">GitHub 源仓库</a></footer>
</body></html>"""
    (OUT / "index.html").write_text(index)

    print(f"PAGES={len(entries) + 1}")
    print(f"FIGURES_INLINED={stats['figures']}")
    print(f"QUIZZES={stats['quizzes']}")
    print("VERDICT=SITE_BUILT")


if __name__ == "__main__":
    build()
