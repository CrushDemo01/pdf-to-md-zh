#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

import build_translation_draft as draftlib


DEFAULT_MODEL = "gpt-5-mini"
DEFAULT_API_BASE = "https://api.openai.com/v1"
DEFAULT_MISTRAL_MD_NAME = "mistral.md"
DEFAULT_OCR_JSON_NAME = "ocr.json"
SYSTEM_PROMPT = (
    "You are translating an academic paper into Chinese markdown. "
    "Return only the translated markdown for the current chunk. "
    "Preserve markdown image syntax, equations, citations, and table "
    "structure. Keep model names, method names, and citation keys in "
    "their original form. Translate section headings to Chinese when "
    "appropriate. Do not add explanations, YAML, code fences around the "
    "whole answer, or placeholder text. If the input contains markers like "
    "[[[PDF2MD_IMAGE_1]]], keep every marker exactly unchanged unless the OCR "
    "placement is clearly wrong. You must check image placement against the "
    "rendered PDF pages and, when needed, move the image marker so the image "
    "appears near the paragraph that actually discusses it."
)
IMAGE_TOKEN_RE = r"\[\[\[PDF2MD_IMAGE_(\d+)\]\]\]"


def get_env_or_raise(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing environment variable: {name}")
    return value


def run_step(cmd: list[str]) -> None:
    print("running:", " ".join(cmd))
    subprocess.run(cmd, check=True)


def load_manifest(outdir: Path) -> dict:
    manifest_path = outdir / "translation_prep.json"
    if not manifest_path.exists():
        return {}
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def call_responses_api(
    *,
    api_key: str,
    model: str,
    api_base: str,
    prompt: str,
) -> str:
    url = f"{api_base.rstrip('/')}/responses"
    payload = {
        "model": model,
        "input": [
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": SYSTEM_PROMPT,
                    }
                ],
            },
            {
                "role": "user",
                "content": [{"type": "input_text", "text": prompt}],
            },
        ],
    }
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Responses API request failed: {exc.code} {detail}") from exc

    output_text = []
    for item in body.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "output_text":
                output_text.append(content.get("text", ""))

    text = "\n".join(part for part in output_text if part).strip()
    if not text:
        raise RuntimeError("Responses API returned no output_text content")
    return text


def build_chunk_prompt(
    *,
    title: str,
    chunk_title: str,
    chunk_body: str,
    asset_summary: str,
    pages_dir: str,
    ocr_json_path: str,
) -> str:
    return (
        f"Paper title: {title}\n\n"
        f"Current chunk title: {chunk_title}\n\n"
        f"Rendered PDF pages directory: {pages_dir}\n"
        f"OCR response JSON: {ocr_json_path}\n\n"
        "Asset index summary for reference:\n"
        f"{asset_summary}\n\n"
        "Translate the following chunk into polished Chinese markdown. Also correct "
        "obvious OCR mistakes in headings, captions, and table formatting when the "
        "OCR draft is clearly wrong. Preserve image links and markdown tables. "
        "You must verify image placement against the rendered PDF pages and keep each "
        "image near the paragraph or subsection that actually discusses it. If the OCR "
        "inserted an image in the wrong place, move that image line to a better location "
        "in the translated markdown. Placeholder markers such as [[[PDF2MD_IMAGE_1]]] "
        "represent image lines: do not delete, rename, or translate them, but you may "
        "move them when OCR placement is clearly incorrect. Use [待人工校对] only when "
        "truly unreadable.\n\n"
        "Chunk source markdown:\n"
        f"{chunk_body}"
    )


def protect_image_syntax(text: str) -> tuple[str, dict[str, str]]:
    image_map: dict[str, str] = {}
    counter = 0

    def repl(match) -> str:
        nonlocal counter
        counter += 1
        token = f"[[[PDF2MD_IMAGE_{counter}]]]"
        image_map[token] = match.group(0)
        return token

    patterns = [r"!\[[^\]]*\]\([^)]+\)", r'<img\b[^>]*?>']
    protected = text
    for pattern in patterns:
        protected = re.sub(pattern, repl, protected, flags=re.IGNORECASE)
    return protected, image_map


def restore_image_syntax(text: str, image_map: dict[str, str]) -> str:
    restored = text
    for token, original in image_map.items():
        restored = restored.replace(token, original)
        restored = restored.replace(f"`{token}`", original)
        restored = restored.replace(f"` {token} `", original)

    token_line_re = re.compile(rf"`?\s*{IMAGE_TOKEN_RE}\s*`?")

    def repl(match) -> str:
        token = f"[[[PDF2MD_IMAGE_{match.group(1)}]]]"
        return image_map.get(token, match.group(0))

    return token_line_re.sub(repl, restored)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Translate OCR markdown chunk by chunk into a final Chinese zh.md "
            "using the OpenAI Responses API."
        )
    )
    parser.add_argument("--pdf", required=True, type=Path, help="Path to source PDF")
    parser.add_argument("--outdir", required=True, type=Path, help="Working output directory")
    parser.add_argument(
        "--out-md",
        required=True,
        type=Path,
        help="Final translated markdown output path, typically <outdir>/target.md",
    )
    parser.add_argument("--title", help="Document title used in the output file")
    parser.add_argument("--ocr-md", type=Path, help="Optional existing OCR markdown path")
    parser.add_argument("--ocr-json", type=Path, help="Optional OCR response JSON path")
    parser.add_argument(
        "--chunk-chars",
        type=int,
        default=draftlib.DEFAULT_CHUNK_CHARS,
        help="Approximate maximum characters per chunk",
    )
    parser.add_argument(
        "--start-chunk",
        type=int,
        default=1,
        help="1-based chunk index to start translation from",
    )
    parser.add_argument(
        "--end-chunk",
        type=int,
        help="1-based chunk index to stop translation at",
    )
    parser.add_argument(
        "--skip-prepare",
        action="store_true",
        help="Do not run prepare_translation_inputs.py first",
    )
    parser.add_argument(
        "--inline-images",
        action="store_true",
        help="Request OCR image data and save them as local files referenced from markdown",
    )
    parser.add_argument(
        "--keep-inline-images",
        action="store_true",
        help="Keep OCR image data inline in markdown instead of writing local image files",
    )
    parser.add_argument("--skip-mistral", action="store_true", help="Pass through to preparation step")
    parser.add_argument("--skip-assets", action="store_true", help="Pass through to preparation step")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Responses API model name")
    parser.add_argument(
        "--api-base",
        default=DEFAULT_API_BASE,
        help="Responses API base URL, default https://api.openai.com/v1",
    )
    parser.add_argument(
        "--ocr-model",
        default="mistral-ocr-latest",
        help="Mistral OCR model passed to prepare_translation_inputs.py",
    )
    parser.add_argument(
        "--signed-url-expiry-minutes",
        type=int,
        default=10,
        help="Signed URL expiry passed to the Mistral files API",
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
    write_script = scripts_dir / "write_md_chunk.py"

    if not args.skip_prepare:
        prepare_cmd = [
            sys.executable,
            str(prepare_script),
            "--pdf",
            str(pdf_path),
            "--outdir",
            str(outdir),
            "--model",
            args.ocr_model,
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

    manifest = load_manifest(outdir)
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
            f"OCR markdown not found: {source_md}. Run preparation first or provide --ocr-md."
        )

    source_text = source_md.read_text(encoding="utf-8")
    chunks = draftlib.chunk_source_text(source_text, max_chars=args.chunk_chars)
    if not chunks:
        raise RuntimeError(f"No usable content found in {source_md}")

    start_idx = max(1, args.start_chunk)
    end_idx = min(len(chunks), args.end_chunk or len(chunks))
    if start_idx > end_idx:
        raise RuntimeError("Invalid chunk range: start-chunk is greater than end-chunk")

    api_key = get_env_or_raise("OPENAI_API_KEY")
    asset_summary = draftlib.read_asset_index(asset_index)

    if start_idx == 1 and out_md.exists():
        out_md.unlink()

    for idx in range(start_idx, end_idx + 1):
        chunk = chunks[idx - 1]
        protected_body, image_map = protect_image_syntax(chunk.body)
        prompt = build_chunk_prompt(
            title=title,
            chunk_title=chunk.title,
            chunk_body=protected_body,
            asset_summary=asset_summary,
            pages_dir=str(pages_dir),
            ocr_json_path=str(ocr_json),
        )
        translated = call_responses_api(
            api_key=api_key,
            model=args.model,
            api_base=args.api_base,
            prompt=prompt,
        )
        translated = restore_image_syntax(translated, image_map)

        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as tmp:
            tmp.write(translated.strip() + "\n")
            tmp_path = Path(tmp.name)

        try:
            write_cmd = [
                sys.executable,
                str(write_script),
                "--out-md",
                str(out_md),
                "--body-file",
                str(tmp_path),
                "--title",
                title,
            ]
            if idx > 1 or start_idx > 1:
                write_cmd.append("--append")
            run_step(write_cmd)
        finally:
            tmp_path.unlink(missing_ok=True)

    print(out_md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
