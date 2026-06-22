# Narration dataset — sourcing & ethics guide (storytelling-style model)

Goal: 30–100 `(facts -> styled retelling)` pairs **per tradition**, balanced,
drawn from authentic, openly-licensed sources, with attribution recorded.

## The pipeline
1. **Gather public-domain texts** of a tradition:
   ```bash
   python fetch_texts.py gutenberg --query "West African folk tales" --out ./griot --max 5
   python fetch_texts.py gutenberg --query "Poetic Edda Norse" --out ./myth --max 5
   ```
2. **Hand-pick** short, representative passages (3–8 sentences) that truly show the
   tradition's cadence. Save each as its own `.txt` in a folder (e.g. `griot_excerpts/`).
3. **Build pairs** (auto with an LLM key, or manual):
   ```bash
   python make_pairs.py build --dir ./griot_excerpts --style griot \
       --style-label "Griot (West Africa)" --out ../narration_style_dataset.jsonl
   ```
   No key → it writes `pairs_to_fill.csv`; fill the `facts` column, then:
   `python make_pairs.py tojsonl --csv pairs_to_fill.csv --out ../narration_style_dataset.jsonl`

## Where to find each tradition (public domain)
| Tradition | Good search terms / sources |
|---|---|
| Oral / folk tale | Gutenberg: "folk tales", "fairy tales", Lang's Fairy Books |
| Griot / West African epic | Gutenberg/Archive: West African folklore; *Sundiata* (use PD translations only) |
| Epic ballad | Gutenberg: Child's "English and Scottish Popular Ballads"; Wikisource: Border ballads |
| Koan / parable | Gutenberg: "Zen", "101 Zen Stories", Aesop, Panchatantra (PD translations) |
| Mythic cycle | Gutenberg: Poetic/Prose Edda, Bulfinch's Mythology, Hellenic myth collections |
| Dastangoi / qissa | seek PD Urdu/Persian *dastan* translations; verify license per text |
| Kamishibai / Japanese tale | Gutenberg: Japanese fairy tales (Ozaki); note picture-theatre form |

Always check each text's license (Gutenberg = public domain; Wikisource varies).
`fetch_texts.py` records sources in `sources.json` — keep it.

## Ethics (this is the project, not a footnote)
- These traditions belong to **living communities**; a griot is a hereditary role,
  not a writing style. Source respectfully, attribute, and frame model output as an
  **interpretation in the style of**, never "authentic griot performance".
- Prefer translations/anthologies that are public domain AND credited. Avoid sacred
  or initiation material a community restricts.
- Where you can, read or cite contemporary practitioners and scholars — and say so
  in your README. Reviewers (and communities) notice this care.

## Balance & evaluation
- Keep counts even across traditions (imbalance makes the model collapse to one voice).
- Hold out ~10% as a test set.
- Add a **faithfulness check**: confirm the styled output introduces no fact absent
  from the input. That's your provenance ethic measured for *form* — a genuinely
  novel evaluation worth writing up.
