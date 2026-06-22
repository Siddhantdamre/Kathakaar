# Image dataset — sourcing & curation guide (visual LoRA)

Goal: 20–60 **consistent, on-topic, openly-licensed** images per style/subject.
Quality beats quantity — 30 good images outperform 300 random ones.

## Run the gatherer
```bash
python fetch_images.py --subject "Konark Sun Temple" --out ./konark --per-source 20
python fetch_images.py --subject "Mughal architecture Agra" --out ./mughal --sources commons,met
```
Every file is logged in `manifest.csv` with source + creator + license + URL.
(Run where there's open internet — Colab, or your laptop.)

## Best open sources (all free; the script uses the first three)
| Source | License | Key needed? |
|---|---|---|
| Wikimedia Commons | CC / public domain (per file — check `manifest.csv`) | no |
| The Met Open Access | CC0 public domain | no |
| Art Institute of Chicago | public-domain subset | no |
| Smithsonian Open Access | CC0 | free key (api.si.edu) |
| Rijksmuseum | public domain | free key |
| NYPL / Library of Congress / Europeana / DPLA | mixed PD/CC | mostly no |

## Curate (the part that decides quality)
1. **Delete off-topic hits** — searches are noisy; keep only your subject.
2. **Stay consistent** — pick one visual register (e.g. the monument itself, or
   the carvings, not maps/diagrams/tourist selfies). Mixed registers blur the LoRA.
3. **20–40 is plenty** for a style LoRA. Add a few wide + a few detail shots.
4. **Resolution** ≥ 768px on the short side; drop tiny/blurry ones.
5. **Keep `manifest.csv`** — it's your attribution record and shows reviewers you
   sourced responsibly.

## Licensing & sensitivity (do not skip)
- Public-domain / CC0 is safest for training and redistribution. For CC BY / BY-SA,
  keep attribution (the manifest does this) and note share-alike obligations.
- Some heritage imagery depicts sacred or living-community contexts. Be respectful:
  avoid sacred objects a community asks not to be reproduced, and describe rather
  than caricature. This judgment is exactly the human value your project adds.

## Then
Point the LoRA notebook's `instance` folder at your curated set. One subject per
LoRA gives the cleanest style; train separate adapters per culture/era and load
the one that matches the user's selection.
