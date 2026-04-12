#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


DEFAULT_CHUNK_CHARS = 5000
DEFAULT_MISTRAL_MD_NAME = "mistral.md"
DEFAULT_OCR_JSON_NAME = "ocr.json"


@dataclass
class Chunk:
    title: str
    body: str


def run_step(cmd: list[str]) -> None:
    print("running:", " ".join(cmd))
    subprocess.run(cmd, check=True)


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_markdown_sections(text: str) -> list[Chunk]:
    text = normalize_text(text)
    if not text:
        return []

    heading_re = re.compile(r"(?m)^(#{1,6})\s+(.+?)\s*$")
    matches = list(heading_re.finditer(text))
    if not matches:
        return [Chunk(title="全文初稿", body=text)]

    chunks: list[Chunk] = []
    preface = text[: matches[0].start()].strip()
    if preface:
        chunks.append(Chunk(title="前置内容", body=preface))

    for idx, match in enumerate(matches):
        title = match.group(2).strip()
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if body:
            chunks.append(Chunk(title=title, body=body))
    return chunks


def split_large_chunk(chunk: Chunk, max_chars: int) -> list[Chunk]:
    body = chunk.body.strip()
    if len(body) <= max_chars:
        return [chunk]

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    if not paragraphs:
        return [Chunk(title=chunk.title, body=body[:max_chars])]

    out: list[Chunk] = []
    part = 1
    current: list[str] = []
    current_len = 0

    for para in paragraphs:
        addition = len(para) + (2 if current else 0)
        if current and current_len + addition > max_chars:
            out.append(Chunk(title=f"{chunk.title}（第{part}段）", body="\n\n".join(current)))
            part += 1
            current = [para]
            current_len = len(para)
            continue
        current.append(para)
        current_len += addition

    if current:
        suffix = f"（第{part}段）" if part > 1 else ""
        out.append(Chunk(title=f"{chunk.title}{suffix}", body="\n\n".join(current)))

    return out


def chunk_source_text(text: str, max_chars: int) -> list[Chunk]:
    chunks: list[Chunk] = []
    for section in split_markdown_sections(text):
        chunks.extend(split_large_chunk(section, max_chars=max_chars))
    return chunks


def read_asset_index(asset_index: Path) -> str:
    if not asset_index.exists():
        return "- 未找到 `asset_index.md`，请直接参考原 PDF 页面。"

    lines = asset_index.read_text(encoding="utf-8").splitlines()
    bullet_lines = [ln for ln in lines if ln.startswith("- ")]
    if not bullet_lines:
        return f"- 资产索引存在，但没有可用条目：`{asset_index.name}`"

    preview = bullet_lines[:12]
    if len(bullet_lines) > 12:
        preview.append(f"- 其余条目请见 `{asset_index.name}`")
    return "\n".join(preview)


def build_markdown(
    *,
    title: str,
    pdf_path: Path,
    source_md: Path,
    ocr_json: Path,
    asset_index: Path,
    pages_dir: Path,
    chunks: list[Chunk],
) -> str:
    lines: list[str] = [
        f"# {title}（中文分块草稿）",
        "",
        "> 本文件是基于富 OCR 原文包生成的翻译工作稿。",
        "> 请同时参考原文 Markdown、OCR JSON、Mistral 图片与 PDF 页面图进行翻译和校对。",
        "",
        "## 使用说明",
        "",
        "- 逐块处理，不要一次性全文翻译。",
        "- 先参考 `原文骨架`，再对照 PDF 页面图修正标题、公式、图注和表格。",
        "- 优先使用 `images/` 与 OCR 返回表格，不依赖启发式裁图。",
        "- 完成一块后立即将中文内容整理到正式译稿。",
        "",
        "## 输入来源",
        "",
        f"- PDF: `{pdf_path}`",
        f"- Source Markdown: `{source_md}`",
        f"- OCR JSON: `{ocr_json}`",
        f"- 资产索引: `{asset_index}`",
        f"- PDF 页面图: `{pages_dir}`",
        "",
        "## 资产索引摘要",
        "",
        read_asset_index(asset_index),
        "",
    ]

    for idx, chunk in enumerate(chunks, start=1):
        lines.extend(
            [
                f"## 第{idx}块：{chunk.title}",
                "",
                "> 校对要求：结合 PDF 页面图、OCR 图片与 OCR JSON，修正原文骨架中的明显 OCR 错误。",
                "",
                "### 中文译文",
                "",
                "[待翻译]",
                "",
                "### 原文骨架",
                "",
                "```text",
                chunk.body.strip(),
                "```",
                "",
            ]
        )

    return "\n".join(lines).rstrip() + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build a chunked Chinese translation working draft from a rich OCR "
            "source package. This helper creates a draft, not a fully translated final zh.md."
        )
    )
    parser.add_argument("--pdf", required=True, type=Path, help="Path to source PDF")
    parser.add_argument("--outdir", required=True, type=Path, help="Working output directory")
    parser.add_argument("--out-md", required=True, type=Path, help="Draft markdown output path")
    parser.add_argument("--title", help="Document title used in the generated draft")
    parser.add_argument(
        "--ocr-md",
        type=Path,
        help="Optional existing Mistral OCR markdown path; defaults to <outdir>/mistral.md",
    )
    parser.add_argument(
        "--ocr-json",
        type=Path,
        help="Optional OCR response JSON path; defaults to <outdir>/ocr.json",
    )
    parser.add_argument(
        "--chunk-chars",
        type=int,
        default=DEFAULT_CHUNK_CHARS,
        help="Approximate maximum characters per chunk",
    )
    parser.add_argument(
        "--skip-prepare",
        action="store_true",
        help="Do not run prepare_translation_inputs.py first",
    )
    parser.add_argument(
        "--skip-mistral",
        action="store_true",
        help="Pass through to prepare_translation_inputs.py",
    )
    parser.add_argument(
        "--skip-assets",
        action="store_true",
        help="Pass through to prepare_translation_inputs.py",
    )
    parser.add_argument("--model", default="mistral-ocr-latest", help="Mistral OCR model name")
    parser.add_argument(
        "--signed-url-expiry-minutes",
        type=int,
        default=10,
        help="Signed URL expiry passed to the Mistral files API",
    )
    parser.add_argument(
        "--inline-images",
        action="store_true",
        help=(
            "Request OCR image data from Mistral and let the OCR script save them "
            "as local files referenced from markdown"
        ),
    )
    parser.add_argument(
        "--keep-inline-images",
        action="store_true",
        help="Keep OCR image data inline in markdown instead of writing local image files",
    )
    parser.add_argument(
        "--table-format",
        choices=["markdown", "html", "none"],
        default="markdown",
        help="Request table extraction format from Mistral OCR during preparation",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    pdf_path = args.pdf.resolve()
    outdir = args.outdir.resolve()
    out_md = args.out_md.resolve()
    title = args.title or pdf_path.stem
    outdir.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)

    scripts_dir = Path(__file__).resolve().parent
    prepare_script = scripts_dir / "prepare_translation_inputs.py"

    if not args.skip_prepare:
        prepare_cmd = [
            sys.executable,
            str(prepare_script),
            "--pdf",
            str(pdf_path),
            "--outdir",
            str(outdir),
            "--model",
            args.model,
            "--signed-url-expiry-minutes",
            str(args.signed_url_expiry_minutes),
        ]
        if args.inline_images:
            prepare_cmd.append("--inline-images")
        if args.keep_inline_images:
            prepare_cmd.append("--keep-inline-images")
        prepare_cmd.extend(["--table-format", args.table_format])
        if args.skip_mistral:
            prepare_cmd.append("--skip-mistral")
        if args.skip_assets:
            prepare_cmd.append("--skip-assets")
        run_step(prepare_cmd)

    manifest_path = outdir / "translation_prep.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        manifest = {}

    source_md = (
        args.ocr_md.resolve()
        if args.ocr_md
        else Path(manifest.get("mistral_markdown") or (outdir / DEFAULT_MISTRAL_MD_NAME))
    )
    ocr_json = (
        args.ocr_json.resolve()
        if args.ocr_json
        else Path(manifest.get("mistral_response_json") or (outdir / DEFAULT_OCR_JSON_NAME))
    )
    asset_index = Path(manifest.get("asset_index") or (outdir / "asset_index.md"))
    pages_dir = Path(manifest.get("pages_dir") or (outdir / "pages"))

    if not source_md.exists():
        raise FileNotFoundError(
            f"OCR markdown not found: {source_md}. "
            "Run preparation first or provide --ocr-md."
        )

    source_text = source_md.read_text(encoding="utf-8")
    chunks = chunk_source_text(source_text, max_chars=args.chunk_chars)
    if not chunks:
        raise RuntimeError(f"No usable content found in {source_md}")

    draft = build_markdown(
        title=title,
        pdf_path=pdf_path,
        source_md=source_md,
        ocr_json=ocr_json,
        asset_index=asset_index,
        pages_dir=pages_dir,
        chunks=chunks,
    )
    out_md.write_text(draft, encoding="utf-8")
    print(out_md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
