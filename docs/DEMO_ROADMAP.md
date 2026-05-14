# Demo Upgrade Roadmap

Goal: make Kathakaar feel like a usable cultural AI product, not just a notebook/prototype.

## Current State

- GitHub Pages surface is live.
- README explains the agentic storytelling pipeline.
- Notebook and Python files show the implementation path.

## Highest-Impact Improvements

| Priority | Upgrade | Recruiter value |
| --- | --- | --- |
| P0 | Add a Gradio or Hugging Face Spaces demo with text-based place input. | Lets reviewers try the product immediately. |
| P0 | Add 3 curated sample locations with generated stories. | Gives predictable demo outputs even if APIs are unavailable. |
| P1 | Show source snippets/citations beside generated narratives. | Makes the RAG/grounding claim credible. |
| P1 | Add a sample voice/narration output. | Makes the project distinctive and memorable. |
| P2 | Add a short GIF of the map/story flow. | Improves README scan value. |

## Suggested Demo Shape

- Gradio UI with fields: place, language/tone, output length.
- Output cards: summary, grounded facts, generated story, image/source links, optional voice sample.
- Safe fallback mode using checked-in examples if live search/LLM calls fail.

## Definition Of Done

- Reviewer can open one link, enter a place, and receive a story-style output.
- Demo includes at least three stable examples.
- README includes screenshots and a short explanation of grounding vs generation.
