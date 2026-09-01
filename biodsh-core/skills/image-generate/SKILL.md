---
name: image-generate
description: Generate scientific illustrations (graphical abstracts, mechanism schematics, cover art, poster art) from a text prompt through the image provider configured in the BioDSH app. Not for data plots.
---

# AI scientific illustration (text-to-image)

Use this skill when the user wants a **picture that is drawn, not computed**: a graphical abstract, a mechanism or pathway schematic, a cell/tissue cartoon, journal cover art, a poster hero image, a conceptual figure for a talk.

Do **not** use it for data plots (UMAP, volcano, heatmap, bar/box plots, survival curves). Those must come from the data through matplotlib/seaborn/scanpy so that every point is real. An image model cannot plot data; it only paints something that looks like a plot.

## Provider configuration

The provider is configured by the user in the BioDSH app under **更多 → 图像生成** (base URL, API key, model). The app passes it to this script as environment variables `BIODSH_IMAGE_BASE_URL`, `BIODSH_IMAGE_API_KEY`, `BIODSH_IMAGE_MODEL`. Any OpenAI-compatible Images API works (OpenAI `gpt-image-1`, 智谱 CogView `cogview-4-250304`, SiliconFlow `Kwai-Kolors/Kolors`, 通义万相 `wan2.2-t2i-flash`, ...).

If the script prints `{"error": "...not configured..."}`, tell the user to fill in 更多 → 图像生成 in the app. Never guess a base URL or key and never ask the user to paste a key into the chat.

## Command

```bash
python "<skill dir>/generate.py" --prompt "..." --out generated_images
```

Options: `--name NAME` (file stem, default: slug of the prompt + timestamp), `--size 1024x1024` (normalized per provider, e.g. 智谱 accepts 1024x1024, 768x1344, 864x1152, 1344x768, 1152x864, 1440x720, 720x1440), `--n 1` (number of variants), `--style scientific|flat|photo|none` (default `scientific`, prepends a style template to your prompt), `--negative "..."` (things to avoid), `--reference path.png` (OpenAI-style providers only; others return an error).

Output: `generated_images/<name>-1.png` (one file per variant) plus `generation.json` (prompt, final prompt, model, provider hostname, size, files, elapsed seconds). The script prints the same JSON to stdout. On failure it prints `{"error": ...}` and exits 1; report the error text to the user as-is (HTTP status and body excerpt are included) and do not retry in a loop.

## Writing a good prompt for a scientific figure

State, in one or two sentences each:

- **Subject** — the biological entities and the relationship between them: "a T cell contacting a tumor cell through PD-1/PD-L1, with a blocking antibody in between".
- **Style** — the `--style scientific` template already asks for a clean vector-like illustration on a white background with flat colors; add only the deviations ("isometric", "watercolor", "dark background for a slide").
- **Layout** — left-to-right flow, number of panels, where the arrows go, what is enlarged in an inset.
- **What to avoid** — put it in `--negative`: "text, letters, watermark, photorealistic gore, extra limbs, cluttered background". Ask for **no text** whenever possible: models misspell gene names; add labels afterwards in PowerPoint/Illustrator.

Keep prompts concrete and short (under ~80 words). Generate 2–3 variants (`--n 2`) when the user is exploring, one when they know what they want. Iterate on wording rather than re-running the same prompt.

## After generation

- Report the absolute path of every PNG to the user and show the image if the interface supports it.
- Remind the user to check the image for factual errors: image models invent labels, ligand/receptor pairs, organelle shapes and arrow directions. A generated schematic is a draft to be corrected, not a source of truth, and should be labelled as AI-generated in a manuscript where the journal requires it.
- Record the prompt in the report (it is in `generation.json`) so the figure can be regenerated.

## Examples

```bash
# graphical abstract, two variants to choose from
python "<skill dir>/generate.py" --prompt "left: a tumor with infiltrating T cells; right: the same tumor after anti-PD-1 therapy with more T cells and shrinking tumor; arrow between them" --n 2 --out generated_images

# wide poster banner, 智谱 CogView accepts 1440x720
python "<skill dir>/generate.py" --prompt "cross-section of a lymph node with B-cell follicles and T-cell zones" --size 1440x720 --negative "text, letters" --out generated_images

# photo-like cover art
python "<skill dir>/generate.py" --prompt "close-up of a single neuron with glowing synapses on a dark background" --style photo --name cover --out generated_images
```

## Chinese prompt tips

Most image models follow English prompts more reliably than Chinese ones (CogView and 万相 handle Chinese well; OpenAI and Kolors prefer English). When the user writes the request in Chinese, translate the subject/style/layout into a precise English prompt internally before calling the script, but keep all your replies, file descriptions and the summary in Chinese. Do not translate gene, protein or drug names — keep the standard symbols (PD-1, TP53, KRAS G12C). If the user wants Chinese characters inside the image, warn that most models render CJK text poorly and suggest adding the text afterwards.
