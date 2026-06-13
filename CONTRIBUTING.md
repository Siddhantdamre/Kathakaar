# Contributing to Kathakaar

Kathakaar treats provenance, abstention, and reproducible evaluation as product
requirements. Contributions should preserve those contracts.

## Development setup

```bash
python -m pip install -e ".[dev]"
make verify
```

On Windows without `make`, run:

```powershell
python -m ruff check src scripts tests
python -m mypy src
python -m pytest -q
```

## Evaluation

Run `make evaluate` after changing retrieval, knowledge normalization,
multimodal fusion, generation, or abstention behavior. Commit benchmark fixture
changes separately from implementation changes and explain why labels changed.

Every reported proportion should include its sample count and, where supported
by the evaluator, a 95% confidence interval. Perfect scores on compact fixtures
must be described as regression evidence rather than open-domain accuracy.

## Pull requests

- Add focused tests for behavioral changes and adversarial failures.
- Keep source URLs, rights metadata, and attribution attached to new records.
- Do not weaken place, citation, or claim-consistency checks to improve coverage.
- Do not commit downloaded model weights, generated caches, credentials, or
  private cultural records.
- Update the relevant evaluation note when a benchmark result changes.

By contributing, you agree that your contribution is licensed under the MIT
License.
