---
name: pdf-to-md-zh
description: Convert a research PDF into a rich source Markdown package with Mistral OCR first, then translate and correct it into Chinese Markdown by combining the source markdown with rendered PDF page images.
---

# PDF to Markdown (Chinese) Skill

## Core Principle

**Two-stage workflow: rich OCR first, agent translation second.**

This skill is no longer centered on heuristic figure crops. The preferred flow is:

1. Use **Mistral OCR** to generate a **complete source markdown package**
2. Use the **agent** to translate that markdown into Chinese
3. During translation, the agent must also **correct OCR errors** by checking the
   rendered PDF page images

The default final deliverable is `target.md`. The first-stage OCR output is a
source package, not the final translated result. The default workflow should
not create a separate translation draft file.

This skill expects `MISTRAL_API_KEY` to be present in the environment before
OCR starts. It does not prompt for the token interactively.

## Stage 1: Rich OCR Package

The OCR stage should preserve as much Mistral-returned structure as possible.
Prefer these outputs:

- `mistral.md`
- `ocr.json`
- `images/`
- `tables_md/` or `tables_html/`
- `asset_index.md`
- `source_package.md`
- `pages/page_XX.png`
- `translation_prep.json`
- `target.md`

At this stage, do **not** translate. The goal is to create the most complete
possible source markdown in the original language.

### OCR Rules

- Prefer **Mistral OCR returned images** as the image source.
- Prefer **Mistral OCR returned tables** as the table source.
- Do **not** treat heuristic figure crops as the primary path.
- Preserve OCR-returned placeholders by mapping them to local image/table files.
- Save the raw OCR response JSON so the agent can inspect missing details later.
- Render PDF pages to `pages/` so the agent can visually verify OCR output.

## Stage 2: Agent Translation And Correction

The second stage is not just “translate markdown”. The agent must:

- translate the source markdown into Chinese
- inspect rendered PDF page images when OCR structure is suspicious
- correct section boundaries, captions, table content, formula layout, and image placement when needed
- verify that each image is placed near the paragraph or subsection that actually discusses it
- move an image line when the OCR insertion point is clearly wrong
- keep model names, method names, and citations in original form
- preserve markdown structure and math formatting

The translation stage should use:

- source markdown from Mistral OCR
- rendered PDF page images in `pages/`
- OCR-returned images in `images/`
- OCR-returned tables in `tables_md/` or `tables_html/`
- OCR response metadata from `ocr.json` when needed

## Required Workflow

1. Confirm the PDF path and final markdown filename.
2. Run the OCR preparation step once.
3. Inspect the source markdown and OCR asset index.
   First read `source_package.md` if present.
4. Split `mistral.md` into manageable chunks in memory.
5. Translate a small chunk using:
   - source markdown
   - rendered PDF page images
   - OCR images/tables
6. Correct OCR mistakes while translating.
7. Verify image placement against the PDF pages and repair wrong insertion points.
8. Immediately write the translated chunk into `target.md`.
9. Continue chunk by chunk until the final Chinese markdown is complete.

Do **not** stop at a scaffold containing `[待翻译]`, and do **not** create an
extra `*_draft.md` file unless the user explicitly asks for one.

## Preferred Tools

1. Preparation tools
   - `prepare_translation_inputs.py`
   - `mistral_ocr_to_markdown.py`
   - `extract_pdf_assets.py`
2. Mechanical writer
   - `write_md_chunk.py`
3. Optional compatibility helpers
   - `translate_markdown_chunks.py`
   - `build_translation_draft.py` for debugging only

`translate_markdown_chunks.py` is still allowed as a scripted compatibility path,
but the preferred quality path is agent-led translation with page-image checking.

## Preferred Commands

Rich OCR preparation:

```bash
python3 skills/pdf-to-md-zh/scripts/prepare_translation_inputs.py \
  --pdf <paper.pdf> \
  --outdir <output_dir> \
  --inline-images \
  --table-format markdown
```

This should also produce `source_package.md`, which is the preferred brief entry
point for stage 2. The output directory should be normalized and stable:

- `mistral.md`
- `ocr.json`
- `images/`
- `pages/`
- `target.md`

Direct OCR only:

```bash
python3 skills/pdf-to-md-zh/scripts/mistral_ocr_to_markdown.py \
  <paper.pdf> \
  -o <output_dir>/mistral.md \
  --inline-images \
  --table-format markdown
```

Render pages and build index from OCR outputs:

```bash
python3 skills/pdf-to-md-zh/scripts/extract_pdf_assets.py \
  --pdf <paper.pdf> \
  --outdir <output_dir> \
  --ocr-md <output_dir>/mistral.md \
  --ocr-json <output_dir>/ocr.json
```

## Translation Rules

- Translate narrative text to Chinese.
- Keep model names, method names, equations, and citations in original form.
- Preserve markdown image syntax and local relative links such as `images/...`.
- Check every image against `pages/` and keep it near the paragraph or subsection that discusses it.
- If OCR inserted an image in the wrong place, move that image line in `target.md` instead of preserving the wrong location.
- Preserve or repair table structure using OCR-returned tables first.
- Use rendered PDF page images as the ground truth when OCR markdown is wrong.
- If OCR is clearly wrong, fix it in the translated output instead of copying the mistake forward.
- Use `[待人工校对]` only when content remains unreadable after checking page images.
- Do not leave `[待翻译]` in the final delivered `target.md`.
- Do not create an intermediate draft markdown file unless the user explicitly asks for one.

## Quality Checklist

- Does the OCR package contain source markdown, OCR JSON, OCR images, OCR tables, and rendered page images?
- Does the OCR package contain `source_package.md` so stage 2 has a stable starting point?
- Does the translated output correct obvious OCR mistakes instead of inheriting them blindly?
- Are images taken from `images/` rather than heuristic crops?
- Are images placed near the correct discussion instead of blindly following OCR insertion points?
- Are tables taken from OCR-returned table files where possible?
- Are figures and tables placed near the relevant discussion?
- Does the final `target.md` read like a publishable translated article?
