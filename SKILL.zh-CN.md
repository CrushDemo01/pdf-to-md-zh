---
name: pdf-to-md-zh
description: 先用 Mistral OCR 将研究论文 PDF 转成完整的源 Markdown 包，再结合 PDF 页面图把它翻译并校对成最终中文 Markdown。
---

# PDF 转 Markdown（中文）Skill

## 核心原则

**两阶段流程：先做富 OCR，再做人工/agent 翻译。**

这个 skill 不再依赖启发式裁图。推荐流程是：

1. 使用 **Mistral OCR** 生成完整的源 Markdown 包
2. 由 **agent** 将该 Markdown 翻译为中文
3. 翻译时必须结合 PDF 页面图，校正 OCR 错误

最终交付物默认是 `target.md`。第一阶段产物是源包，不是最终译文。默认流程不应额外生成单独的翻译草稿文件。

## 第一阶段：富 OCR 源包

OCR 阶段应尽可能保留 Mistral 返回的结构。推荐输出包括：

- `mistral.md`
- `ocr.json`
- `images/`
- `tables_md/` 或 `tables_html/`
- `asset_index.md`
- `source_package.md`
- `pages/page_XX.png`
- `translation_prep.json`
- `target.md`

此阶段不要翻译。目标是生成尽可能完整的原文 Markdown。

### OCR 规则

- 优先使用 **Mistral OCR 返回的图片**。
- 优先使用 **Mistral OCR 返回的表格**。
- 不要把启发式裁图当作主路径。
- 保留 OCR 占位符，并映射到本地图片/表格文件。
- 保存原始 OCR JSON，方便后续检查缺失内容。
- 将 PDF 页面渲染到 `pages/`，便于校对 OCR 输出。

## 第二阶段：agent 翻译与校对

第二阶段不只是“翻译 Markdown”。agent 还必须：

- 将源 Markdown 翻译成中文
- 在 OCR 结构可疑时检查 PDF 页面图
- 纠正章节边界、图注、表格内容、公式布局和图片位置
- 确认每张图都靠近真正讨论它的段落或小节
- 在 OCR 插入点明显错误时移动图片行
- 保留模型名、方法名和引用格式
- 保留 Markdown 结构和数学格式

翻译阶段应结合：

- Mistral OCR 源 Markdown
- `pages/` 中的 PDF 页面图
- `images/` 中的 OCR 返回图
- `tables_md/` 或 `tables_html/` 中的 OCR 表格
- `ocr.json` 中的元数据

## 必要流程

1. 确认 PDF 路径和最终 Markdown 文件名。
2. 先运行 OCR 准备步骤。
3. 检查源 Markdown 和资产索引，优先阅读 `source_package.md`。
4. 在内存中把 `mistral.md` 切成可处理的分块。
5. 翻译每个分块时同时参考：
   - 源 Markdown
   - PDF 页面图
   - OCR 图片/表格
6. 翻译时修正 OCR 错误。
7. 对照 PDF 页面图检查图片位置并修复插入点。
8. 立即把译文写入 `target.md`。
9. 分块继续，直到完成最终中文 Markdown。

不要停留在含有 `[待翻译]` 的草稿，也不要创建额外的 `*_draft.md` 文件，除非用户明确要求。

## 推荐工具

1. 准备工具
   - `prepare_translation_inputs.py`
   - `mistral_ocr_to_markdown.py`
   - `extract_pdf_assets.py`
2. 写入工具
   - `write_md_chunk.py`
3. 可选兼容工具
   - `translate_markdown_chunks.py`
   - `build_translation_draft.py`（仅调试）

`translate_markdown_chunks.py` 仍可作为脚本化兼容路径，但推荐的高质量路径是由 agent 结合页面图进行翻译。

## 推荐命令

富 OCR 准备：

```bash
python3 skills/pdf-to-md-zh/scripts/prepare_translation_inputs.py \
  --pdf <paper.pdf> \
  --outdir <output_dir> \
  --inline-images \
  --table-format markdown
```

这一步还会产出 `source_package.md`，它是第二阶段的推荐入口。输出目录应保持稳定：

- `mistral.md`
- `ocr.json`
- `images/`
- `pages/`
- `target.md`

直接 OCR：

```bash
python3 skills/pdf-to-md-zh/scripts/mistral_ocr_to_markdown.py \
  <paper.pdf> \
  -o <output_dir>/mistral.md \
  --inline-images \
  --table-format markdown
```

根据 OCR 输出渲染页面并构建索引：

```bash
python3 skills/pdf-to-md-zh/scripts/extract_pdf_assets.py \
  --pdf <paper.pdf> \
  --outdir <output_dir> \
  --ocr-md <output_dir>/mistral.md \
  --ocr-json <output_dir>/ocr.json
```

## 翻译规则

- 将正文翻译为中文。
- 保留模型名、方法名、公式和引用格式。
- 保留 Markdown 图片语法和 `images/...` 这样的相对路径。
- 检查每张图是否贴近 `pages/` 中对应的讨论位置。
- 如果 OCR 把图插错了，在 `target.md` 中移动图片行，而不是照搬错误位置。
- 优先使用 OCR 返回表格修复或保留表格结构。
- 当 OCR Markdown 有错时，以 PDF 页面图为准。
- 只有在确实无法辨认时才使用 `[待人工校对]`。
- 最终交付的 `target.md` 中不要保留 `[待翻译]`。
- 除非用户明确要求，否则不要创建中间草稿文件。

## 质量检查

- OCR 包是否包含源 Markdown、OCR JSON、OCR 图片、OCR 表格和 PDF 页面图？
- 是否包含 `source_package.md`，以便第二阶段有稳定起点？
- 译文是否修正了明显的 OCR 错误，而不是直接继承？
- 图片是否来自 `images/`，而不是启发式裁图？
- 图片是否放在真正讨论它的地方，而不是机械跟随 OCR 插入点？
- 表格是否优先使用 OCR 返回表格文件？
- 生成的 `target.md` 是否像一篇可发布的中文论文译稿？
