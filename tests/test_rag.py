from __future__ import annotations

from kathakaar.multimodal import HashingMultimodalEncoder, MultimodalRetriever
from kathakaar.rag import GuardedMultimodalRAG, StructuredGenAIStoryGenerator
from kathakaar.schemas import MediaAsset, SourceDocument


class FakeBackend:
    name = "fake"

    def __init__(self, response: str) -> None:
        self.response = response

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        return self.response


def _retriever() -> MultimodalRetriever:
    document = SourceDocument(
        "hampi",
        "Vittala Temple",
        "Hampi",
        "https://example.test/hampi",
        "The ceremonial architecture includes a stone chariot.",
        media_assets=(
            MediaAsset(
                "hampi-image",
                "image",
                "https://example.test/hampi.jpg",
                caption="Stone chariot at the Vittala temple",
            ),
        ),
    )
    return MultimodalRetriever(HashingMultimodalEncoder()).fit([document])


def test_guarded_genai_accepts_supported_cited_claim():
    generator = StructuredGenAIStoryGenerator(
        FakeBackend(
            '{"title":"Hampi","claims":[{"text":"The ceremonial architecture '
            'includes a stone chariot.","source_ids":["hampi"]}]}'
        )
    )

    result = GuardedMultimodalRAG(_retriever(), generator).answer(
        "stone chariot ceremonial architecture",
        place="Hampi",
        theme="craft",
    )

    assert result.status == "grounded"
    assert result.story is not None
    assert result.story.claims[0].source_ids == ("hampi",)


def test_guarded_genai_rejects_unretrieved_citation():
    generator = StructuredGenAIStoryGenerator(
        FakeBackend(
            '{"title":"Hampi","claims":[{"text":"An invented railway existed.",'
            '"source_ids":["missing"]}]}'
        )
    )

    result = GuardedMultimodalRAG(_retriever(), generator).answer(
        "stone chariot",
        place="Hampi",
        theme="craft",
    )

    assert result.status == "generation_rejected"
    assert result.story is None
