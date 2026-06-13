from __future__ import annotations

from kathakaar.cli import main


def test_cli_fit_and_evaluate(tmp_path):
    corpus = tmp_path / "corpus.jsonl"
    queries = tmp_path / "queries.jsonl"
    model = tmp_path / "model.json"
    report = tmp_path / "report.json"
    corpus.write_text(
        '{"source_id":"s1","title":"Temple","place":"Hampi",'
        '"url":"https://example","text":"A stone chariot stands in the temple."}\n',
        encoding="utf-8",
    )
    queries.write_text(
        '{"id":"q1","query":"Hampi stone chariot","place":"Hampi",'
        '"expected_source_ids":["s1"],"theme":"craft"}\n',
        encoding="utf-8",
    )

    fit_status = main(["fit-retriever", "--corpus", str(corpus), "--output", str(model)])
    evaluate_status = main(
        [
            "evaluate",
            "--queries",
            str(queries),
            "--model",
            str(model),
            "--output",
            str(report),
        ]
    )

    assert fit_status == 0
    assert evaluate_status == 0
    assert model.exists()
    assert report.exists()
