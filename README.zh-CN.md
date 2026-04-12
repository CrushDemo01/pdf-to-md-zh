# pdf-to-md-zh

`pdf-to-md-zh` 是一个 Codex skill，用于把研究论文 PDF 先转成 Mistral OCR 源 Markdown 包，再翻译并校对为最终中文 Markdown。

## 功能

- 先运行 Mistral OCR，生成 `mistral.md`、`ocr.json`、`images/`、`pages/` 等源文件。
- 将源 Markdown 翻译为 `target.md`。
- 翻译时结合 PDF 页面图校对图片位置、图注和表格，尽量保持与原论文一致。

## 文件结构

- `SKILL.md`：英文版主 skill 说明。
- `SKILL.zh-CN.md`：中文版本 skill 说明。
- `scripts/`：OCR、抽取和翻译脚本。
- `agents/`：默认 agent 提示词。
- `references/`：裁图和表格处理的示例配置。

## 依赖

- Python 3
- `MISTRAL_API_KEY`：用于 OCR
- `OPENAI_API_KEY`：用于脚本化翻译辅助流程

## 使用

```bash
python3 scripts/prepare_translation_inputs.py \
  --pdf <paper.pdf> \
  --outdir <output_dir> \
  --inline-images \
  --table-format markdown
```

最终推荐输出是同一目录下的 `target.md`。

## 说明

- 这个 skill 适合在 Codex 或 Cloud Code 的本地工作流中使用。
- 生成物默认不提交到仓库。
