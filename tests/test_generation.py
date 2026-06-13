from __future__ import annotations

from kathakaar.generation import GroundedStoryGenerator
from kathakaar.schemas import RetrievalHit, SourceDocument


def test_generator_links_each_claim_to_a_source():
    source = SourceDocument(
        source_id="archive",
        title="Archive",
        place="Example",
        url="https://example",
        text="The archive preserves a long tradition. Community members maintain it.",
    )

    story = GroundedStoryGenerator().generate(
        place="Example",
        theme="memory",
        hits=[RetrievalHit(source, 0.8)],
    )

    assert story.claims
    assert all(claim.source_ids == ("archive",) for claim in story.claims)
    assert "[archive]" in story.narrative
