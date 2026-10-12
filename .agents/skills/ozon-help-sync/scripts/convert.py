# -*- coding: utf-8 -*-
"""
Ozon 帮助中心知识库转换器
将抓取的 contentJson(ProseMirror) 转换为 HTML 与 Markdown，并按文档树组织目录。

用法: python tools/convert.py
"""
import json
import os
import re
import html as html_mod
from pathlib import Path

RAW = Path(r"E:\code\zqr\ozon-helper\ozon-help-kb\raw\ozon_help_zh_raw.json")
OUT = Path(r"E:\code\zqr\ozon-helper\ozon-help-kb")
MD_DIR = OUT / "markdown"
HTML_DIR = OUT / "html"
ASSETS_DIR = HTML_DIR / "assets"
IMAGES_DIR = HTML_DIR / "images"

SITE_BASE = "https://global-help.ozon.com"
REGION = "CHN"


def esc(s):
    return html_mod.escape(s or "", quote=True)


def render_marks(text, marks):
    """按顺序包裹 bold / italic / link 标记。"""
    if not marks:
        return esc(text)
    node = esc(text)
    for m in marks:
        t = m.get("type")
        if t == "bold":
            node = f"<strong>{node}</strong>"
        elif t == "italic":
            node = f"<em>{node}</em>"
        elif t == "link":
            attrs = m.get("attrs", {})
            href = attrs.get("href", "")
            target = attrs.get("target", "_self")
            cls = attrs.get("class", "link")
            tgt = f' target="{esc(target)}"' if target and target != "_self" else ""
            node = f'<a class="{esc(cls)}" href="{esc(href)}"{tgt}>{node}</a>'
    return node


class PMRenderer:
    def __init__(self):
        self._heading_ids = {}

    def _unique_heading_id(self, raw_id):
        if not raw_id:
            return None
        base = raw_id.strip()
        if not base:
            return None
        if base in self._heading_ids:
            self._heading_ids[base] += 1
            return f"{base}-{self._heading_ids[base]}"
        self._heading_ids[base] = 0
        return base

    def render_children(self, nodes):
        out = []
        for n in nodes or []:
            out.append(self.render(n))
        return "\n".join(x for x in out if x)

    def render(self, n):
        if n is None:
            return ""
        t = n.get("type")
        if t == "text":
            return render_marks(n.get("text", ""), n.get("marks"))
        if t == "paragraph":
            return f"<p>{self.render_children(n.get('content'))}</p>"
        if t == "hardBreak":
            return "<br>"
        if t == "heading":
            level = int(n.get("attrs", {}).get("level", 2) or 2)
            level = max(2, min(level, 6))
            hid = self._unique_heading_id(n.get("attrs", {}).get("id", ""))
            anchor = f' id="{esc(hid)}"' if hid else ""
            return f"<h{level}{anchor}>{self.render_children(n.get('content'))}</h{level}>"
        if t == "unorderedList":
            return f"<ul>{self.render_children(n.get('content'))}</ul>"
        if t == "orderedList":
            attrs = n.get("attrs", {}) or {}
            start = attrs.get("start")
            s = f' start="{int(start)}"' if start else ""
            return f"<ol{s}>{self.render_children(n.get('content'))}</ol>"
        if t == "listItem":
            return f"<li>{self.render_children(n.get('content'))}</li>"
        if t == "table":
            return f'<div class="table-wrap"><table>{self.render_children(n.get("content"))}</table></div>'
        if t == "tableRow":
            return f"<tr>{self.render_children(n.get('content'))}</tr>"
        if t == "tableCell":
            attrs = n.get("attrs", {}) or {}
            tag = "th" if attrs.get("type") == "th" else "td"
            extra = ""
            if attrs.get("colspan", 1) != 1:
                extra += f' colspan="{int(attrs["colspan"])}"'
            if attrs.get("rowspan", 1) != 1:
                extra += f' rowspan="{int(attrs["rowspan"])}"'
            return f"<{tag}{extra}>{self.render_children(n.get('content'))}</{tag}>"
        if t == "note":
            attrs = n.get("attrs", {}) or {}
            variant = attrs.get("variant", "info") or "info"
            desc = attrs.get("description", "") or ""
            body = self.render_children(n.get("content"))
            desc_html = f'<div class="note-desc">{esc(desc)}</div>' if desc else ""
            return f'<div class="note note-{esc(variant)}">{desc_html}{body}</div>'
        if t == "spoilerWrapper":
            attrs = n.get("attrs", {}) or {}
            open_attr = " open" if attrs.get("isOpenByDefault") else ""
            return f'<details class="spoiler"{open_attr}>{self.render_children(n.get("content"))}</details>'
        if t == "spoilerTitle":
            return f"<summary>{self.render_children(n.get('content'))}</summary>"
        if t == "spoilerContent":
            return f"<div class=\"spoiler-content\">{self.render_children(n.get('content'))}</div>"
        if t == "tabs" or t == "tabsWrapper":
            return f'<div class="tabs">{self.render_children(n.get("content"))}</div>'
        if t == "tabsItem":
            attrs = n.get("attrs", {}) or {}
            label = esc(attrs.get("label", ""))
            return f'<div class="tabs-item" data-label="{label}">{self.render_children(n.get("content"))}</div>'
        if t == "tabItem":
            return f'<div class="tab-item">{self.render_children(n.get("content"))}</div>'
        if t == "tabItemTitle":
            return f'<h4 class="tab-item-title">{self.render_children(n.get("content"))}</h4>'
        if t == "tabItemContent":
            return f'<div class="tab-item-content">{self.render_children(n.get("content"))}</div>'
        if t == "pictureBlock":
            attrs = n.get("attrs", {}) or {}
            src = attrs.get("src", "")
            alt = attrs.get("alt", "") or ""
            width = attrs.get("width")
            height = attrs.get("height")
            desc = attrs.get("description", "") or ""
            loading = attrs.get("loading", "lazy") or "lazy"
            w = f' width="{esc(str(width))}"' if width and str(width) not in ("auto", "None") else ""
            h = f' height="{esc(str(height))}"' if height and str(height) not in ("auto", "None") else ""
            img = f'<img src="{esc(src)}" alt="{esc(alt)}"{w}{h} loading="{esc(loading)}">'
            cap = f'<figcaption>{esc(desc)}</figcaption>' if desc else ""
            fig = f'<figure class="picture">{img}{cap}</figure>'
            href = attrs.get("href") or ""
            if href:
                target = attrs.get("target", "_self") or "_self"
                tgt = f' target="{esc(target)}"' if target != "_self" else ""
                fig = f'<a href="{esc(href)}"{tgt}>{fig}</a>'
            return fig
        if t == "inlinePicture":
            attrs = n.get("attrs", {}) or {}
            src = attrs.get("src", "")
            alt = attrs.get("alt", "") or ""
            return f'<img class="inline-picture" src="{esc(src)}" alt="{esc(alt)}">'
        if t == "codeBlock":
            attrs = n.get("attrs", {}) or {}
            lang = attrs.get("language", "") or ""
            code = "".join((c.get("text") or "") for c in (n.get("content") or []))
            cls = f' class="language-{esc(lang)}"' if lang else ""
            return f"<pre><code{cls}>{esc(code)}</code></pre>"
        if t == "geo":
            attrs = n.get("attrs", {}) or {}
            regions = attrs.get("regions") or []
            label = f'<div class="geo-label">适用地区: {esc(", ".join(regions))}</div>' if regions else ""
            return f'<div class="geo">{label}{self.render_children(n.get("content"))}</div>'
        if t == "geoItem":
            attrs = n.get("attrs", {}) or {}
            region = esc(attrs.get("region", ""))
            return f'<div class="geo-item" data-region="{region}"><div class="geo-region">{region}</div>{self.render_children(n.get("content"))}</div>'
        if t == "file":
            attrs = n.get("attrs", {}) or {}
            name = attrs.get("name", "文件")
            src = attrs.get("src", "")
            size = attrs.get("size")
            size_txt = f" ({round(int(size) / 1024)} KB)" if size else ""
            return f'<a class="file" href="{esc(src)}" download>{esc(name)}{esc(size_txt)}</a>'
        if t == "gallery":
            attrs = n.get("attrs", {}) or {}
            imgs = attrs.get("images") or []
            inner = []
            for im in imgs:
                s = im.get("src", "")
                a = im.get("alt", "") or ""
                if s:
                    inner.append(f'<img src="{esc(s)}" alt="{esc(a)}" loading="lazy">')
            return f'<div class="gallery">{"".join(inner)}</div>'
        if t == "IframeBlock":
            attrs = n.get("attrs", {}) or {}
            src = attrs.get("src", "")
            width = attrs.get("width") or "100%"
            height = attrs.get("height") or "400"
            return f'<iframe class="iframe-block" src="{esc(src)}" width="{esc(str(width))}" height="{esc(str(height))}" loading="lazy"></iframe>'
        # 未知类型：渲染子节点
        return self.render_children(n.get("content"))


def render_doc(content_json):
    try:
        cj = json.loads(content_json) if isinstance(content_json, str) else content_json
    except Exception:
        return "<p><em>（内容解析失败）</em></p>"
    if not isinstance(cj, dict):
        return "<p><em>（空内容）</em></p>"
    r = PMRenderer()
    body = r.render_children(cj.get("content"))
    return body or "<p><em>（空内容）</em></p>"


# ---------------- HTML 页面 ----------------

PAGE_TPL = """<!DOCTYPE html>
<html lang="zh-Hans">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} | Ozon 卖家知识库</title>
<link rel="stylesheet" href="{rel}assets/style.css">
</head>
<body>
<div class="layout">
<nav class="sidebar" id="sidebar">
<div class="sidebar-head"><a href="index.html">Ozon 卖家知识库</a></div>
<div class="sidebar-body" id="sidebar-body">{sidebar_tree}</div>
</nav>
<div class="main">
<button class="menu-toggle" id="menu-toggle" aria-label="菜单">☰</button>
<header class="doc-header">
<div class="breadcrumbs">{breadcrumbs}</div>
<h1>{title}</h1>
<div class="doc-meta">更新于 {updated} · 来源 <a href="{source}" target="_blank">global-help.ozon.com</a></div>
</header>
<article class="doc-body">
{body}
</article>
<footer class="doc-footer">由本地知识库工具生成 · {total} 篇文章</footer>
</div>
</div>
<script>window.__KB_ROOT = "{rel}";</script>
<script src="{rel}assets/search-index.js"></script>
<script src="{rel}assets/app.js"></script>
</body>
</html>
"""


def build_html_page(doc, tree_html, breadcrumb_html, total, source, rel):
    body = render_doc(doc.get("contentJson")) if doc.get("contentJson") else (
        "<p><em>（本文无正文内容，可能为占位文章。）</em></p>")
    title = esc(doc.get("title") or doc.get("path") or "")
    updated = esc(doc.get("updated") or "")
    return PAGE_TPL.format(
        title=title, body=body, breadcrumbs=breadcrumb_html, updated=updated,
        source=esc(source), total=total, rel=rel, sidebar_tree=tree_html,
    )


# ---------------- Markdown ----------------

def html_to_md(html_frag):
    """将上述渲染器产出的有限 HTML 片段转换为 Markdown（用于检索/RAG）。"""
    s = html_frag
    # 0) 先合并 li 内直接包裹的 p（<li><p>X</p></li> → <li>X</li>），避免列表项断裂
    prev = None
    while prev != s:
        prev = s
        s = re.sub(r"<li><p>(.*?)</p></li>", lambda m: "<li>" + m.group(1) + "</li>", s, flags=re.S)
    # 0.5) 先转图片与文件链接为 MD 语法（必须在 _inline_md 删除标签之前）
    s = re.sub(r'<img[^>]*src="([^"]+)"[^>]*alt="([^"]*)"[^>]*>', lambda m: f"![{m.group(2)}]({m.group(1)})", s)
    s = re.sub(r'<img[^>]*src="([^"]+)"[^>]*>', lambda m: f"![]({m.group(1)})", s)
    s = re.sub(r'<a class="file"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', lambda m: f"[{_inline_md(m.group(2))}]({m.group(1)})", s, flags=re.S)
    # 1) 处理表格为 MD 表格
    s = _tables_to_md(s)
    # 2) 标题
    for lv in (6, 5, 4, 3, 2):
        s = re.sub(rf"<h{lv}[^>]*>(.*?)</h{lv}>", lambda m: "\n\n" + "#" * lv + " " + _inline_md(m.group(1)) + "\n", s, flags=re.S)
    # 3) 段落 / 列表项 / 行
    s = re.sub(r"<p>(.*?)</p>", lambda m: "\n\n" + _inline_md(m.group(1)) + "\n", s, flags=re.S)
    s = re.sub(r"<li>(.*?)</li>", lambda m: "\n- " + _inline_md(m.group(1)).strip(), s, flags=re.S)
    s = re.sub(r"<br\s*/?>", "\n", s)
    # 4) 引用/说明块
    s = re.sub(r'<div class="note[^"]*">(.*?)</div>', lambda m: "\n> " + re.sub(r"\n\s*", "\n> ", _inline_md(m.group(1))).strip() + "\n", s, flags=re.S)
    # 5) 代码块
    s = re.sub(r'<pre><code[^>]*>(.*?)</code></pre>', lambda m: "\n```\n" + html_mod.unescape(m.group(1)) + "\n```\n", s, flags=re.S)
    # 6) details/summary
    s = re.sub(r"<details[^>]*>", "\n", s)
    s = re.sub(r"</details>", "\n", s)
    s = re.sub(r"<summary>(.*?)</summary>", lambda m: "\n**" + _inline_md(m.group(1)) + "**\n", s, flags=re.S)
    # 7) 折叠 tabs/geo 等容器标签
    s = re.sub(r"<div class=\"tabs[^\"]*\"[^>]*>", "\n", s)
    s = re.sub(r"<div class=\"tabs-item\"[^>]*>", "\n", s)
    s = re.sub(r"<div class=\"geo[^\"]*\"[^>]*>", "\n", s)
    s = re.sub(r"<div class=\"geo-item\"[^>]*>", "\n", s)
    s = re.sub(r"<div class=\"geo-region\">(.*?)</div>", lambda m: "\n**【" + _inline_md(m.group(1)) + "】**\n", s, flags=re.S)
    s = re.sub(r"</?(?:div|table|tbody|thead|tr|ul|ol|figure|figcaption|iframe|section)(?:\s[^>]*)?>", "\n", s)
    # 8) 图片 / 文件链接已在步骤 0.5 处理
    # 9) 内联
    s = _inline_md(s)
    # 清理
    s = re.sub(r"\n{3,}", "\n\n", s)
    s = re.sub(r"[ \t]+\n", "\n", s)
    return s.strip()


def _tables_to_md(s):
    def conv(m):
        rows = re.findall(r"<tr>(.*?)</tr>", m.group(0), flags=re.S)
        md_rows = []
        for i, r in enumerate(rows):
            cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", r, flags=re.S)
            cells = [_inline_md(c).strip().replace("|", "\\|") for c in cells]
            md_rows.append("| " + " | ".join(cells) + " |")
        if not md_rows:
            return ""
        sep = "| " + " | ".join(["---"] * (len(md_rows[0].split("|")) - 2)) + " |"
        md_rows.insert(1, sep)
        return "\n\n" + "\n".join(md_rows) + "\n"
    return re.sub(r"<table>.*?</table>", conv, s, flags=re.S)


def _inline_md(s):
    s = re.sub(r"<strong>(.*?)</strong>", lambda m: "**" + m.group(1) + "**", s, flags=re.S)
    s = re.sub(r"<em>(.*?)</em>", lambda m: "*" + m.group(1) + "*", s, flags=re.S)
    s = re.sub(r'<a class="[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', lambda m: f"[{m.group(2)}]({m.group(1)})", s, flags=re.S)
    s = re.sub(r"<[^>]+>", "", s)
    return html_mod.unescape(s)


# ---------------- 目录组织 ----------------

def collect_articles(tree, path_parts=()):
    """递归收集树中的文章，返回 (article, dir_parts) 列表；section 作为路径前缀。"""
    items = []
    for node in tree:
        name = _safe_name(node.get("title") or node.get("path") or "section")
        sub = path_parts + (name,)
        for a in node.get("articles", []):
            items.append((a, sub))
        items.extend(collect_articles(node.get("sections", []), sub))
    return items


def _safe_name(name):
    s = re.sub(r'[\\/:*?"<>|]', "-", name).strip()
    s = re.sub(r"\s+", " ", s)
    return s[:80] or "untitled"


def build_sidebar_html(tree, active_path, rel=""):
    """根据树生成侧边栏导航（嵌套 ul）。active_path 为当前文章 API path。rel 为相对知识库根的前缀。"""
    def node_li(n):
        # n: {'title','path','url','articles':[...],'sections':[...]}
        kids = []
        for a in n.get("articles", []):
            ap = a.get("url", "")
            target = rel + ("index.html" if not ap else _local_html_path(ap, rel=True))
            cls = ' class="active"' if ap == active_path else ""
            kids.append(f'<li><a href="{target}"{cls}>{esc(a.get("title") or ap)}</a></li>')
        for s in n.get("sections", []):
            kids.append(node_li(s))
        if not kids:
            return ""
        open_cls = ' class="open"' if active_path and (active_path.startswith(n.get("path", "")) or any(True for a in n.get("articles", []) if a.get("url") == active_path)) else ""
        slug = _section_slug(n)
        inner = "\n".join(kids)
        return (f'<li><details{open_cls}><summary><a class="sec-link" href="{rel}{esc(slug)}.html">'
                f'{esc(n.get("title") or "")}</a></summary><ul>{inner}</ul></details></li>')
    lis = "\n".join(node_li(t) for t in tree)
    return f"<ul class=\"tree\">{lis}</ul>"


def _local_html_path(api_path, rel=False):
    """API path(/commissions/ozon-fees/ogl-rates) → 本地 html 相对路径。"""
    parts = [p for p in api_path.split("/") if p]
    if not parts:
        return "index.html"
    p = "/".join(parts)
    if rel:
        return p + ".html"
    return str(HTML_DIR / f"{p}.html")


def breadcrumb_html(breadcrumbs, api_path, rel=""):
    if not breadcrumbs:
        return f'<a href="{rel}index.html">首頁</a>'
    out = [f'<a href="{rel}index.html">首頁</a>']
    for bc in breadcrumbs:
        if bc.get("id") == 0:
            continue
        url = bc.get("url", "")
        title = bc.get("title", "")
        if url and url != "/":
            href = rel + (_local_html_path(url, rel=True) if url.startswith("/") and url != "/" else url)
            out.append(f'<a href="{esc(href)}">{esc(title)}</a>')
        else:
            out.append(f"<span>{esc(title)}</span>")
    return " / ".join(out)


def main():
    with open(RAW, encoding="utf-8") as f:
        data = json.load(f)
    tree = data["tree"]
    docs = data["docs"]
    doc_by_path = {d["path"]: d for d in docs}
    global total_articles
    total_articles = len(docs)
    total = total_articles

    MD_DIR.mkdir(parents=True, exist_ok=True)
    HTML_DIR.mkdir(parents=True, exist_ok=True)
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    # 侧边栏（活动文章为 None 的通用版本）
    sidebar = build_sidebar_html(tree, active_path="")

    written = []
    missing = []
    for d in docs:
        api_path = d["path"]
        parts = [p for p in api_path.split("/") if p]
        if not parts:
            continue
        rel_path = "/".join(parts)
        out_html = HTML_DIR / f"{rel_path}.html"
        out_md = MD_DIR / f"{rel_path}.md"
        out_html.parent.mkdir(parents=True, exist_ok=True)
        out_md.parent.mkdir(parents=True, exist_ok=True)

        rel_to_root = "../" * (len(parts) - 1)
        source = f"{SITE_BASE}/zh{api_path}?region={REGION}"

        body_html = render_doc(d.get("contentJson")) if d.get("contentJson") else (
            "<p><em>（本文无正文内容，可能为占位文章。）</em></p>")
        title = d.get("title") or api_path
        updated = d.get("updated") or ""
        breadcrumbs = breadcrumb_html(d.get("breadcrumbs") or [], api_path, rel=rel_to_root)
        sidebar_active = build_sidebar_html(tree, active_path=api_path, rel=rel_to_root)

        page = PAGE_TPL.format(
            title=esc(title), body=body_html, breadcrumbs=breadcrumbs, updated=esc(updated),
            source=esc(source), total=total, rel=rel_to_root, sidebar_tree=sidebar_active,
        )
        out_html.write_text(page, encoding="utf-8")

        md_body = html_to_md(body_html)
        front = (
            "---\n"
            f"title: \"{title}\"\n"
            f"path: {api_path}\n"
            f"id: {d.get('id') or ''}\n"
            f"updated: {updated}\n"
            f"source: {source}\n"
            "---\n\n"
        )
        out_md.write_text(front + md_body + "\n", encoding="utf-8")
        written.append(rel_path)

    # 首页
    home_sidebar = build_sidebar_html(tree, active_path="")
    home_body = _build_home_body(tree)
    home = PAGE_TPL.format(
        title="Ozon 卖家知识库", body=home_body, breadcrumbs="<span>首頁</span>",
        updated="", source=SITE_BASE, total=total, rel="", sidebar_tree=home_sidebar,
    )
    (HTML_DIR / "index.html").write_text(home, encoding="utf-8")

    # 分类落地页（含文章/子分类链接，供首页卡片与侧边栏导航使用）
    n_sections = build_section_pages(tree)
    print(f"分类落地页: {n_sections}")

    # 索引 JSON
    index = {
        "name": "Ozon Global 卖家知识库 (中文)",
        "region": REGION,
        "fetched_at": data.get("fetchedAt"),
        "total_articles": total,
        "tree": tree,
        "articles": [
            {
                "path": d["path"],
                "title": d.get("title"),
                "id": d.get("id"),
                "updated": d.get("updated"),
                "url": f"{SITE_BASE}/zh{d['path']}?region={REGION}",
            }
            for d in docs
        ],
    }
    (OUT / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")

    # 内联搜索索引（script 标签加载，避免 file:// 下 fetch 被 CORS 限制）
    search_items = [{"t": d.get("title") or d["path"], "p": d["path"]} for d in docs]
    js = "window.__SEARCH_INDEX = " + json.dumps(search_items, ensure_ascii=False) + ";\n"
    (ASSETS_DIR / "search-index.js").write_text(js, encoding="utf-8")

    print(f"OK: {len(written)} html + {len(written)} md + index.json + index.html")
    print("MISSING DOCS:", missing if missing else "none")


def _build_home_body(tree):
    """首页正文：顶级分类卡片。"""
    cards = []
    for t in tree:
        title = t.get("title") or ""
        articles = t.get("articles") or []
        sections = t.get("sections") or []
        n_articles = len(articles)
        n_sections = len(sections)
        href = _local_html_path(t.get("url") or t.get("path") or "/", rel=True)
        if href == "index.html":
            href = _safe_name(title) + ".html"
        cards.append(
            f'<div class="home-card"><h3><a href="{esc(href)}">{esc(title)}</a></h3>'
            f'<div class="home-card-meta">{n_sections} 个分类 · {n_articles} 篇文章</div></div>'
        )
    return (
        "<h2>Ozon Global 卖家知识库 · 中文离线版</h2>"
        "<p>共收录 18 个顶级分类下的全部文章。左侧为完整目录树，支持站内搜索（Ctrl+K）。</p>"
        '<div class="home-cards">' + "\n".join(cards) + "</div>"
    )


def _section_slug(node):
    url = node.get("url") or node.get("path") or ""
    parts = [p for p in url.split("/") if p]
    if not parts:
        return "home"
    return "/".join(parts)


def build_section_pages(tree):
    """为每个分类（section）生成落地页，列出其子分类与文章。返回生成数量。"""
    count = 0

    def collect_descendant_articles(node):
        arts = list(node.get("articles", []))
        for s in node.get("sections", []):
            arts.extend(collect_descendant_articles(s))
        return arts

    def render_section_page(node, breadcrumb_chain):
        nonlocal count
        title = node.get("title") or _section_slug(node)
        parts = [p for p in _section_slug(node).split("/") if p]
        out_path = HTML_DIR / f"{'/'.join(parts)}.html"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        rel = "../" * (len(parts) - 1)

        crumb = [f'<a href="{rel}index.html">首頁</a>']
        for bc in breadcrumb_chain:
            crumb.append(f'<span>{esc(bc)}</span>')
        crumb.append(f"<span>{esc(title)}</span>")

        body_parts = [f"<h2>{esc(title)}</h2>"]
        desc = node.get("description")
        if desc:
            body_parts.append(f"<p>{esc(desc)}</p>")
        if node.get("sections"):
            body_parts.append("<h3>子分类</h3><ul>")
            for s in node["sections"]:
                slug = _section_slug(s)
                body_parts.append(f'<li><a href="{rel}{esc(slug)}.html">{esc(s.get("title") or slug)}</a></li>')
            body_parts.append("</ul>")
        if node.get("articles"):
            body_parts.append("<h3>文章</h3><ul>")
            for a in node["articles"]:
                ap = a.get("url", "")
                body_parts.append(
                    f'<li><a href="{rel}{esc(ap.strip("/"))}.html">{esc(a.get("title") or ap)}</a></li>')
            body_parts.append("</ul>")

        sidebar = build_sidebar_html(tree, active_path="", rel=rel)
        page = PAGE_TPL.format(
            title=esc(title),
            body="\n".join(body_parts),
            breadcrumbs=" / ".join(crumb),
            updated="",
            source=SITE_BASE,
            total=total_articles,
            rel=rel,
            sidebar_tree=sidebar,
        )
        out_path.write_text(page, encoding="utf-8")
        count += 1

        for s in node.get("sections", []):
            render_section_page(s, breadcrumb_chain + [title])

    for t in tree:
        render_section_page(t, [])
    return count


if __name__ == "__main__":
    main()
