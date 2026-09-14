#!/usr/bin/env python3
"""Render paper/wage_inflation.md to a bzhmacro house-style HTML page and a PDF.

    python scripts/build_paper.py                  # HTML + PDF
    python scripts/build_paper.py --html-only
    python scripts/build_paper.py --pdf-engine weasyprint

Two outputs, two jobs:

* **HTML** (`web/paper/wage_inflation.html`) lives inside the deployed site, so
  the paper ships with the model it describes and the Vercel build picks it up
  with no extra configuration. It uses the house document stylesheet
  (`bzh-doc.css`, light — screen is dark, paper is light) and renders maths with
  KaTeX from a CDN.

* **PDF** (`paper/wage_inflation.pdf`) goes through pandoc and xelatex rather
  than through the HTML. The house tooling normally prints from HTML with
  WeasyPrint, and that is right for a note; this is a paper with twelve numbered
  display equations, and no HTML-to-PDF engine available here typesets
  mathematics acceptably. The LaTeX template carries the house paper accents,
  the house type trio (vendored under `paper/assets/fonts/`) and the house
  closing furniture, so the identity survives the change of engine. Pass
  ``--pdf-engine weasyprint`` to print from the HTML instead and see the
  difference for yourself.

The fonts are vendored, not linked, so the PDF renders identically on a machine
with no Google Fonts access.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "paper" / "wage_inflation.md"
ASSETS = REPO / "paper" / "assets"
FONTS = ASSETS / "fonts"
HTML_OUT = REPO / "web" / "paper" / "wage_inflation.html"
PDF_OUT = REPO / "paper" / "wage_inflation.pdf"
TEX_OUT = REPO / "paper" / "wage_inflation.tex"

FOOTER = ("Derived from public sources — see method. Estimates, not official "
          "publications. Not investment advice. · bzhmacro.com")


def front_matter(text: str) -> tuple[dict, str]:
    """Split YAML front matter from the body. Uses PyYAML when present and a
    two-key fallback when not, so the script never fails on a missing dep."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end < 0:
        return {}, text
    raw, body = text[3:end], text[end + 4:]
    try:
        import yaml
        meta = yaml.safe_load(raw) or {}
    except Exception:  # noqa: BLE001
        meta = {}
        for line in raw.splitlines():
            m = re.match(r"^(\w+):\s*(.+)$", line)
            if m:
                meta[m.group(1)] = m.group(2).strip().strip('"')
    return meta, body.lstrip("\n")


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------
HTML_SHELL = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{title} — bzhmacro</title>
<meta name="description" content="{tagline}" />
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
<link rel="stylesheet"
      href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:ital,wght@0,400;0,600;0,700;1,400&family=IBM+Plex+Mono:wght@400;600&family=Source+Serif+4:ital,wght@0,400;0,600;0,700;1,400&display=swap" />
<link rel="stylesheet" href="https://www.bzhmacro.com/brand/bzh-doc.css"
      onerror="this.onerror=null;this.href='assets/bzh-doc.css';" />
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css" />
<style>
  /* Project layer only. No token is overridden here: the house rule is that a
     value that needs changing is changed in tokens.json so every site and
     document moves together. */
  .doc-head {{ border-bottom:2px solid var(--rule); padding-bottom:18px; margin-bottom:26px; }}
  .doc-head .kicker {{ font-family:var(--font-mono); font-size:9.5pt; letter-spacing:.12em;
                       text-transform:uppercase; color:var(--gold); }}
  .doc-head h1 {{ margin:.25em 0 .15em; }}
  .doc-head .meta {{ font-family:var(--font-mono); font-size:9pt; color:var(--muted); }}
  .abstract {{ background:var(--panel); border-left:3px solid var(--seal);
               padding:16px 20px; margin:22px 0 30px; }}
  .abstract-label {{ font-size:9.5pt; font-family:var(--font-mono); letter-spacing:.12em;
                     text-transform:uppercase; color:var(--muted); margin:0 0 8px !important; }}
  .abstract p {{ margin:0; }}
  .backlink {{ font-family:var(--font-mono); font-size:9pt; }}
  .site-footer {{ margin-top:46px; padding-top:14px; border-top:1px solid var(--line);
                  font-family:var(--font-mono); font-size:8.5pt; color:var(--muted); }}
  .katex-display {{ overflow-x:auto; overflow-y:hidden; padding:2px 0; }}
  table {{ font-variant-numeric: tabular-nums; }}
</style>
</head>
<body>
<main class="wrap doc">
  <header class="doc-head">
    <div class="kicker">bzhmacro · research</div>
    <h1>{title}</h1>
    <p class="lede">{tagline}</p>
    <p class="meta">{author} · {date}{status}</p>
    <p class="backlink"><a href="../index.html#wage">← the interactive model</a></p>
  </header>
  {abstract}
  {body}
  <footer class="site-footer">{footer}</footer>
</main>
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"></script>
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/contrib/auto-render.min.js"
        onload="renderMathInElement(document.body, {{delimiters:[
          {{left:'$$',right:'$$',display:true}},
          {{left:'$',right:'$',display:false}},
          {{left:'\\\\[',right:'\\\\]',display:true}},
          {{left:'\\\\(',right:'\\\\)',display:false}}], throwOnError:false}});"></script>
</body>
</html>
"""


def build_html(meta: dict, body_md: str) -> Path:
    import markdown

    # `md_in_html` lets the callout blocks survive; `attr_list` and `tables` are
    # what the house markdown conventions rely on.
    html = markdown.markdown(
        body_md,
        extensions=["extra", "tables", "attr_list", "footnotes", "md_in_html",
                    "sane_lists", "toc"],
        output_format="html5",
    )
    # GitHub-style alert blocks -> house callouts.
    html = re.sub(r"<blockquote>\s*<p>\[!NOTE\]\s*", '<div class="callout info"><p>', html)
    html = re.sub(r"<blockquote>\s*<p>\[!WARNING\]\s*", '<div class="callout warn"><p>', html)
    html = re.sub(r"<blockquote>\s*<p>\[!IMPORTANT\]\s*", '<div class="callout"><p>', html)
    html = html.replace("</blockquote>", "</div>") if "callout" in html else html

    # The house markdown convention: the document's own `#` heading and the
    # paragraph after it are furniture, not body. The heading duplicates the
    # title already in the banner, and the paragraph is the serif lede. Pull
    # both out rather than printing the title twice.
    lede = meta.get("tagline", meta.get("subtitle", ""))
    m = re.match(r"\s*<h1[^>]*>.*?</h1>\s*(?:<p>(.*?)</p>)?", html, flags=re.S)
    if m:
        if m.group(1):
            lede = m.group(1).strip()
        html = html[m.end():]

    abstract = ""
    if meta.get("abstract"):
        # A <p> and not an <h2>: bzh-doc.css numbers h2 with a CSS counter, and
        # an abstract is not section 01.
        abstract = (f'<section class="abstract">'
                    f'<p class="abstract-label">Abstract</p>'
                    f'<p>{str(meta["abstract"]).strip()}</p></section>')
    status = f" · {meta['status']}" if meta.get("status") else ""

    HTML_OUT.parent.mkdir(parents=True, exist_ok=True)
    HTML_OUT.write_text(HTML_SHELL.format(
        title=meta.get("title", "Untitled"),
        tagline=lede,
        author=meta.get("author", "bzhmacro"),
        date=meta.get("date", ""),
        status=status, abstract=abstract, body=html, footer=FOOTER,
    ), encoding="utf-8")

    # The page links the hosted stylesheet with a vendored fallback, so the
    # fallback has to be next to it in the deployed tree.
    (HTML_OUT.parent / "assets").mkdir(exist_ok=True)
    shutil.copy(ASSETS / "bzh-doc.css", HTML_OUT.parent / "assets" / "bzh-doc.css")
    return HTML_OUT


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------
TEX_PREAMBLE = r"""
\usepackage{fontspec}
\usepackage{unicode-math}
\usepackage[a4paper,margin=28mm,bottom=30mm]{geometry}
\usepackage{xcolor}
\usepackage{booktabs}
\usepackage{longtable}
\usepackage{array}
\usepackage{titlesec}
\usepackage{fancyhdr}
\usepackage{microtype}

%% House paper accents (bzh-doc.css token block, print variant).
\definecolor{seal}{HTML}{C75130}
\definecolor{gold}{HTML}{956D27}
\definecolor{teal}{HTML}{218174}
\definecolor{ink}{HTML}{191D26}
\definecolor{dim}{HTML}{4E5464}
\definecolor{rule}{HTML}{C4BAA4}

%% House type trio, vendored so the PDF is reproducible offline.
\setmainfont{SourceSerif4}[
  Path=FONTDIR/, Extension=.ttf,
  UprightFont=*-400, ItalicFont=*-400i, BoldFont=*-700, BoldItalicFont=*-600i]
\setsansfont{IBMPlexSans}[
  Path=FONTDIR/, Extension=.ttf,
  UprightFont=*-400, ItalicFont=*-400i, BoldFont=*-600, BoldItalicFont=*-600i]
\setmonofont{IBMPlexMono}[
  Path=FONTDIR/, Extension=.ttf, Scale=0.88,
  UprightFont=*-400, ItalicFont=*-400i, BoldFont=*-600]
\setmathfont{Latin Modern Math}

\color{ink}
\titleformat{\section}{\sffamily\bfseries\large\color{ink}}{\thesection}{0.7em}{}
\titleformat{\subsection}{\sffamily\bfseries\normalsize\color{dim}}{\thesubsection}{0.6em}{}
\renewcommand{\arraystretch}{1.15}
\setlength{\tabcolsep}{5pt}

\pagestyle{fancy}
\fancyhf{}
\renewcommand{\headrulewidth}{0pt}
\renewcommand{\footrulewidth}{0.4pt}
\renewcommand{\footrule}{\color{rule}\hrule width\headwidth height\footrulewidth}
\fancyfoot[L]{\sffamily\scriptsize\color{dim}bzhmacro.com}
\fancyfoot[R]{\sffamily\scriptsize\color{dim}\thepage}
\fancyfoot[C]{\sffamily\scriptsize\color{dim}Estimates, not official publications. Not investment advice.}

\usepackage[colorlinks=true,linkcolor=teal,urlcolor=teal,citecolor=teal]{hyperref}
"""


def build_pdf(engine: str = "xelatex") -> Path | None:
    if shutil.which("pandoc") is None:
        print("pandoc not found; skipping the PDF", file=sys.stderr)
        return None

    if engine == "weasyprint":
        try:
            from weasyprint import HTML
        except ImportError:
            print("weasyprint not installed; skipping the PDF", file=sys.stderr)
            return None
        HTML(filename=str(HTML_OUT)).write_pdf(str(PDF_OUT))
        return PDF_OUT

    preamble = TEX_PREAMBLE.replace("FONTDIR", str(FONTS))
    header = REPO / "paper" / ".header.tex"
    header.write_text(preamble, encoding="utf-8")
    cmd = [
        "pandoc", str(SRC), "-o", str(PDF_OUT),
        "--pdf-engine", "xelatex",
        "--include-in-header", str(header),
        "--standalone",
        "--variable", "documentclass=article",
        "--variable", "fontsize=10pt",
        "--variable", "linestretch=1.15",
        "--variable", "colorlinks=true",
        "--from", "markdown+yaml_metadata_block+tex_math_dollars+pipe_tables+footnotes",
    ]
    # pandoc's default LaTeX template loads lmodern unconditionally, and this
    # TeX Live installation does not ship it. Rather than patch the template or
    # stub the package out, the real lmodern.sty is vendored under
    # paper/texmf/ and put on TEXINPUTS. It is overridden by the \setmainfont
    # in the header, so it changes nothing about the output -- it just has to
    # exist.
    import os
    env = dict(os.environ)
    texmf = REPO / "paper" / "texmf" / "tex" / "latex" / "local"
    env["TEXINPUTS"] = f"{texmf}:{env.get('TEXINPUTS', '')}"
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=900, env=env)
    header.unlink(missing_ok=True)
    if res.returncode != 0:
        print(res.stderr[-3000:], file=sys.stderr)
        return None
    # Keep the LaTeX source too: the brief asked for something that could be
    # turned into a PDF, and a .tex the author can edit is part of that.
    subprocess.run(cmd[:2] + ["-o", str(TEX_OUT)] + cmd[4:], capture_output=True,
                   text=True, timeout=600, env=env)
    return PDF_OUT


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--html-only", action="store_true")
    ap.add_argument("--pdf-engine", default="xelatex",
                    choices=["xelatex", "weasyprint"])
    args = ap.parse_args()

    if not SRC.exists():
        print(f"{SRC} not found", file=sys.stderr)
        return 1
    meta, body = front_matter(SRC.read_text(encoding="utf-8"))
    html = build_html(meta, body)
    print(f"wrote {html} ({html.stat().st_size / 1024:.0f} KB)")
    if args.html_only:
        return 0
    pdf = build_pdf(args.pdf_engine)
    if pdf and pdf.exists():
        print(f"wrote {pdf} ({pdf.stat().st_size / 1024:.0f} KB)")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
