# Training — Cultural Heritage Style LoRA

`kathakaar_lora_sdxl.ipynb` — fine-tune Stable Diffusion XL with LoRA on a small
heritage image set, on a **free** Colab/Kaggle T4 GPU. This is the first, achievable
step toward Kathakaar generating its own visuals.

## How to run
1. Open the notebook in **Google Colab** (or Kaggle).
2. Runtime → Change runtime type → **T4 GPU**.
3. Run the cells top to bottom. Edit `SUBJECT` (cell 3) to your heritage subject,
   and put 20–40 curated images in `/content/instance`.
4. After training, cell 5 generates a place/era/theme image with your style.

## Honest scope
- Trains an **image** style model (not video). Image→video is the next notebook.
- Output quality is driven by the **images you curate** — keep them on-topic and
  well-licensed (Wikimedia Commons public-domain/CC). Be respectful of sacred or
  sensitive heritage; that curation is the culturally-appropriate core of the work.
- Expect a few hours total, including dataset curation. This is a learning project,
  not a one-click result — and that's exactly why it's worth putting on a resume.

## What it earns you
> Fine-tuned SDXL with LoRA on a curated cultural-heritage dataset; built a
> place/era/theme-conditioned generation pipeline for an image-to-video cinematic.

---

## Narration-style training (text)

`kathakaar_narration_lora.ipynb` — QLoRA fine-tune of a small open LLM (Qwen2.5-3B)
so it retells grounded facts in different **storytelling traditions** (oral, griot,
ballad, koan, mythic…). Free T4. Seed data: `narration_style_dataset.jsonl`
(`{style, style_label, facts, narration}` per line).

### The work is the data, and the ethics
- The 10 seed pairs are a format demo. Grow each tradition to 30–100 authentic,
  openly-licensed pairs for real quality.
- These traditions belong to living communities — source respectfully, attribute,
  and frame outputs as interpretations *in the style of*. That care is the project.

### Plug-in
Serve the trained adapter and call it from `studio/app/cinematic.py` to produce each
scene's narration from the grounded `caption` + chosen tradition — keeping the refusal
gate and citations. Gate behind `NARRATION_MODEL_URL`, with the current templates as
the free fallback. This adds a measurable **faithfulness** check (no new facts) — a
strong thing to publish.

## Image → Video (the final piece)

`kathakaar_img2vid.ipynb` — takes your trained SDXL LoRA + a story manifest and
produces a real MP4 cinematic.

**What it does, end-to-end:**
1. Loads your `pytorch_lora_weights.safetensors`
2. Generates one cinematic image per scene (SDXL + LoRA, 1024×576, your heritage style)
3. Animates each image into a short video clip (Stable Video Diffusion img2vid-xt-1-1)
4. Adds spoken narration (gTTS free, or swap in ElevenLabs premium)
5. Stitches all scenes with captions into one MP4 (moviepy + ffmpeg)

**Runtime:** ~10–15 min for a 4-scene story on a free Kaggle T4.

**To use:** Upload your LoRA weights to Kaggle as a dataset, paste your story scenes
from the Kathakaar `/api/cinematic` response, and run top to bottom. The resulting MP4
connects directly to `/api/render` — upload it to Cloudflare R2 or Google Drive and
return the public URL as `video_url`.

## Suggested order
1. `kathakaar_narration_lora.ipynb` — text styling (closest to your core, cheapest to run).
2. `kathakaar_lora_sdxl.ipynb` — visual style (you've already done this — great start).
3. `kathakaar_img2vid.ipynb` — animate your LoRA stills into a real MP4 cinematic.
