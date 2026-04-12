
# pdf-to-md-zh

`pdf-to-md-zh` is a Codex skill for turning a research PDF into a source Markdown package with Mistral OCR, then translating and correcting it into final Chinese Markdown.

[中文说明](README.zh-CN.md) | [Chinese Skill](SKILL.zh-CN.md)

## What it does

- Runs Mistral OCR first and saves a source package with `mistral.md`, `ocr.json`, `images/`, and `pages/`.
- Translates the source Markdown into `target.md`.
- Checks rendered PDF pages during translation so image placement, captions, and tables stay aligned with the paper.

## Files

- `SKILL.md`: main skill instructions.
- `scripts/`: OCR, extraction, and translation helpers.
- `agents/`: default agent prompts.
- `references/`: example configs for crop/table handling.

## Requirements

- Python 3
- `MISTRAL_API_KEY` for OCR
- `OPENAI_API_KEY` for scripted translation helpers that call the OpenAI Responses API

## Usage

```bash
python3 scripts/prepare_translation_inputs.py \
  --pdf <paper.pdf> \
  --outdir <output_dir> \
  --inline-images \
  --table-format markdown
```

The preferred final output is `target.md` in the same output directory.

## Notes

- The skill is designed for local use in Codex or Cloud Code.
- Generated outputs are not committed to the repository.
