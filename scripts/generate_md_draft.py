#!/usr/bin/env python3
"""
LEGACY HELPER — NOT THE PREFERRED WORKFLOW.

This script can generate draft markdown from extracted PDF assets, but it still
contains heuristic structure/placement behavior. Prefer the LLM-first workflow:

1. read a small chunk directly with the model
2. decide the chunk structure with the model
3. write the already-decided chunk using write_md_chunk.py

Use this file only as a temporary helper, not as the source of truth for paper
structure.
"""

import argparse
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple


@dataclass
class Asset:
    kind: str  # figure/table/extended_data_figure/...
    num: str
    page: int
    label: str = ""
    rel_path: str = ""
    md_text: str = ""


def normalize_math_markers(text: str) -> str:
    text = text.replace("\\[", "$$").replace("\\]", "$$")
    text = text.replace("\\(", "$").replace("\\)", "$")
    text = re.sub(r"\\tag\{(\d+)\}", r"\\qquad (\1)", text)
    return text


def clean_extracted_text(text: str) -> str:
    # Remove common CVPR/ICCV style page headers and line-number artifacts
    text = re.sub(r"(?m)^===== PAGE \d+ =====\n?", "", text)
    text = re.sub(r"CVPR\n#\d+CVPR\n#\d+\nCVPR .*?DO NOT DISTRIBUTE\.\n", "", text)
    text = re.sub(r"\b\d{3}\n", "\n", text)
    text = re.sub(r"-\n", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return normalize_math_markers(text)


def split_text_by_pages(raw_text: str) -> List[Tuple[int, str]]:
    parts = re.split(r"(?m)^===== PAGE (\d+) =====\n?", raw_text)
    pages: List[Tuple[int, str]] = []
    if len(parts) <= 1:
        txt = raw_text.strip()
        if txt:
            pages.append((1, txt))
        return pages

    for i in range(1, len(parts), 2):
        pno = int(parts[i])
        body = parts[i + 1].strip()
        pages.append((pno, body))
    return pages


def filter_pages(raw_text: str, start_page: Optional[int], end_page: Optional[int]) -> str:
    pages = split_text_by_pages(raw_text)
    kept = []
    for pno, body in pages:
        if start_page is not None and pno < start_page:
            continue
        if end_page is not None and pno > end_page:
            continue
        kept.append(f"===== PAGE {pno} =====\n{body}")
    return "\n\n".join(kept).strip()


def parse_sections(text: str) -> List[Tuple[str, str]]:
    # Preserve abstract + numbered headings
    m_abs = re.search(r"\bAbstract\b", text)
    start = m_abs.start() if m_abs else 0
    text = text[start:]

    # Match headings like 1. Introduction / 3.1 Foo
    pattern = re.compile(r"(?m)^((?:\d+\.)+(?:\d+)?\s+[^\n]+|\d+\.\s+[^\n]+)$")
    matches = list(pattern.finditer(text))

    sections: List[Tuple[str, str]] = []
    if not matches:
        sections.append(("全文", text.strip()))
        return sections

    # Abstract block
    pre = text[: matches[0].start()].strip()
    if pre:
        sections.append(("Abstract", pre))

    for i, m in enumerate(matches):
        title = m.group(1).strip()
        s = m.end()
        e = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[s:e].strip()
        sections.append((title, body))

    return sections


def build_page_sections(raw_text: str) -> List[Tuple[str, str]]:
    sections: List[Tuple[str, str]] = []
    for pno, body in split_text_by_pages(raw_text):
        cleaned = clean_extracted_text(body).strip()
        if cleaned:
            sections.append((f"第 {pno} 页", cleaned))
    return sections


def collect_assets(figtab_dir: Path, tables_md_dir: Path, out_md: Path) -> List[Asset]:
    assets: List[Asset] = []

    def label_to_kind_num(label: str) -> Tuple[str, str]:
        low = label.lower()
        m = re.search(r"(\d+[A-Za-z]?)", label)
        num = m.group(1) if m else "?"
        if low.startswith("extended_data_figure_"):
            return "extended_data_figure", num
        if low.startswith("supplementary_figure_"):
            return "supplementary_figure", num
        if low.startswith("figure_"):
            return "figure", num
        if low.startswith("extended_data_table_"):
            return "extended_data_table", num
        if low.startswith("supplementary_table_"):
            return "supplementary_table", num
        if low.startswith("table_"):
            return "table", num
        return "asset", num

    figure_best = {}
    if figtab_dir.exists():
        for p in sorted(figtab_dir.glob("*.png")):
            m = re.match(r"(.+)_p(\d+)\.png", p.name)
            if not m:
                continue
            stem, page = m.group(1), int(m.group(2))
            kind, num = label_to_kind_num(stem)
            rel = os.path.relpath(p, out_md.parent)
            label = " ".join(part.capitalize() for part in kind.split("_")) + f" {num}"
            key = (kind, num)
            cand = (p.stat().st_size, Asset(kind=kind, num=num, page=page, label=label, rel_path=rel))
            if key not in figure_best or cand[0] > figure_best[key][0]:
                figure_best[key] = cand
        assets.extend(v[1] for v in figure_best.values())

    if tables_md_dir.exists():
        for p in sorted(tables_md_dir.glob("*_p*.md")):
            m = re.match(r"(.+)_p(\d+)\.md", p.name)
            if not m:
                continue
            stem, page = m.group(1), int(m.group(2))
            kind, num = label_to_kind_num(stem)
            md_text = p.read_text(encoding="utf-8", errors="ignore").strip()
            label = " ".join(part.capitalize() for part in kind.split("_")) + f" {num}"
            assets.append(Asset(kind=kind, num=num, page=page, label=label, md_text=md_text))

    assets.sort(key=lambda a: (a.kind, a.num, a.page))
    return assets


def section_key(title: str) -> str:
    t = title.lower()
    if "introduction" in t or t.startswith("1."):
        return "intro"
    if "method" in t or t.startswith("3."):
        return "method"
    if "experiment" in t or t.startswith("4."):
        return "exp"
    if "related" in t or t.startswith("2."):
        return "related"
    if "conclusion" in t or t.startswith("5."):
        return "conclusion"
    return "other"


def assign_assets(sections: List[Tuple[str, str]], assets: List[Asset]) -> Dict[int, List[Asset]]:
    assigned: Dict[int, List[Asset]] = {i: [] for i in range(len(sections))}
    used = set()

    # pass1: by explicit mention "Figure N" / "Table N"
    for i, (_, body) in enumerate(sections):
        for a in assets:
            if (a.kind, a.num, a.page) in used:
                continue
            kind_pat = a.kind.replace("_", r"[_\s]*")
            pat = rf"\b{kind_pat}\s*{re.escape(str(a.num))}\b"
            if re.search(pat, body, flags=re.IGNORECASE):
                assigned[i].append(a)
                used.add((a.kind, a.num, a.page))

    # pass2: heuristic fallback
    key_to_idx = {section_key(t): i for i, (t, _) in enumerate(sections)}
    for a in assets:
        k = (a.kind, a.num, a.page)
        if k in used:
            continue
        num_int = int(a.num) if str(a.num).isdigit() else 999
        if a.kind.endswith("table"):
            idx = key_to_idx.get("exp", len(sections) - 1)
        else:
            if num_int <= 2:
                idx = key_to_idx.get("intro", 0)
            elif num_int <= 5:
                idx = key_to_idx.get("method", min(1, len(sections) - 1))
            else:
                idx = key_to_idx.get("exp", len(sections) - 1)
        assigned[idx].append(a)
        used.add(k)

    for v in assigned.values():
        v.sort(key=lambda a: (a.kind, a.num, a.page))
    return assigned


def to_cn_heading(title: str) -> str:
    mapping = {
        "abstract": "摘要（Abstract）",
        "introduction": "引言（Introduction）",
        "related work": "相关工作（Related Work）",
        "method": "方法（Method）",
        "experiments": "实验（Experiments）",
        "conclusion": "结论（Conclusion）",
        "references": "参考文献（References）",
    }
    low = title.lower()
    for k, v in mapping.items():
        if k in low:
            return re.sub(r"\d+(?:\.\d+)*\.?\s*", "", title).strip() and v or v
    return title


def build_markdown_body(sections: List[Tuple[str, str]], sec_assets: Dict[int, List[Asset]]) -> str:
    lines: List[str] = []

    for i, (sec_title, body) in enumerate(sections):
        h = to_cn_heading(sec_title)
        lines.append(f"## {h}")
        lines.append("")
        lines.append("[待翻译：请将下方英文内容翻译为中文，保留术语与引用编号一致。]")
        lines.append("")
        lines.append("```text")
        lines.append(body.strip())
        lines.append("```")
        lines.append("")

        if sec_assets.get(i):
            for a in sec_assets[i]:
                label = a.label or f"{a.kind.capitalize()} {a.num}"
                if "figure" in a.kind:
                    lines.append(f"![{label}]({a.rel_path})")
                    lines.append("")
                    lines.append(f"**{label}（待补中文图注）**")
                    lines.append("")
                else:
                    lines.append(f"### {label}")
                    lines.append("")
                    lines.append(a.md_text or "[待人工校对] 自动表格提取失败，请参考原 PDF。")
                    lines.append("")
                    lines.append(f"**{label}（待补中文表注）**")
                    lines.append("")

    return "\n".join(lines).strip()


def build_markdown(title: str, sections: List[Tuple[str, str]], sec_assets: Dict[int, List[Asset]], *, include_header: bool = True, include_footer: bool = True) -> str:
    lines: List[str] = []
    if include_header:
        lines.append(f"# {title}（中文翻译稿）")
        lines.append("")
        lines.append("> 自动草稿：已插入 Figure 图像和 Table markdown，公式标记已转为 markdown 兼容格式（$$ / $）。")
        lines.append("> 提示：请在此基础上做术语统一与人工校对。")
        lines.append("")

    body = build_markdown_body(sections, sec_assets)
    if body:
        lines.append(body)

    if include_footer:
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("## 术语对照（可选）")
        lines.append("")
        lines.append("- [待补充]")
        lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(
        description="LEGACY helper: generate a draft markdown chunk from extracted assets. "
        "Not recommended as the main workflow; prefer LLM judgement + write_md_chunk.py."
    )
    ap.add_argument("--assets-dir", required=True, help="Directory generated by extract_pdf_assets.py")
    ap.add_argument("--out-md", required=True, help="Output markdown path")
    ap.add_argument("--title", default="论文", help="Markdown title")
    ap.add_argument("--start-page", type=int, help="Only process pages from this page number")
    ap.add_argument("--end-page", type=int, help="Only process pages up to this page number")
    ap.add_argument("--mode", choices=["section", "pages"], default="section", help="Split output by sections or by pages")
    ap.add_argument("--append", action="store_true", help="Append chunk content to an existing markdown file instead of overwriting")
    ap.add_argument("--chunk-label", help="Optional heading inserted before this chunk, e.g. '第1部分（P1-P2）'")
    args = ap.parse_args()

    assets_dir = Path(args.assets_dir)
    out_md = Path(args.out_md)
    out_md.parent.mkdir(parents=True, exist_ok=True)

    extracted = assets_dir / "extracted_text.txt"
    if not extracted.exists():
        raise FileNotFoundError(f"missing: {extracted}")

    raw_text = extracted.read_text(encoding="utf-8", errors="ignore")
    if args.start_page is not None or args.end_page is not None:
        raw_text = filter_pages(raw_text, args.start_page, args.end_page)

    text = clean_extracted_text(raw_text)
    if args.mode == "pages":
        sections = build_page_sections(raw_text)
    else:
        sections = parse_sections(text)
    assets = collect_assets(assets_dir / "figures_tables", assets_dir / "tables_md", out_md)
    if args.start_page is not None or args.end_page is not None:
        assets = [
            a for a in assets
            if (args.start_page is None or a.page >= args.start_page)
            and (args.end_page is None or a.page <= args.end_page)
        ]
    sec_assets = assign_assets(sections, assets)

    md = build_markdown(args.title, sections, sec_assets, include_header=not args.append or not out_md.exists(), include_footer=not args.append)
    if args.append and out_md.exists():
        pieces = []
        if args.chunk_label:
            pieces.append(f"\n\n---\n\n## {args.chunk_label}\n")
        pieces.append(md.lstrip())
        with out_md.open("a", encoding="utf-8") as f:
            f.write("".join(pieces))
    else:
        if args.chunk_label:
            md += f"\n\n> 当前块：{args.chunk_label}\n"
        out_md.write_text(md, encoding="utf-8")

    print(f"draft markdown written: {out_md}")
    print(f"sections={len(sections)}, assets={len(assets)}")


if __name__ == "__main__":
    main()
