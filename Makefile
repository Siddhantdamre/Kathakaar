PYTHON ?= python

.PHONY: install lint typecheck test verify evaluate

install:
	$(PYTHON) -m pip install -e ".[dev]"

lint:
	$(PYTHON) -m ruff check src scripts tests

typecheck:
	$(PYTHON) -m mypy src

test:
	$(PYTHON) -m pytest -q

verify: lint typecheck test

evaluate:
	$(PYTHON) scripts/build_grounding_v2.py
	$(PYTHON) -m kathakaar fit-retriever --method hybrid --corpus benchmarks/grounding_v2/corpus.jsonl --output artifacts/hybrid_v2.json
	$(PYTHON) -m kathakaar validate --queries benchmarks/grounding_v2/queries.jsonl --model artifacts/hybrid_v2.json --output results/grounding_v2/robustness.json
	$(PYTHON) scripts/build_knowledge_v3.py
	$(PYTHON) -m kathakaar kb-audit
	$(PYTHON) -m kathakaar fit-multimodal
	$(PYTHON) -m kathakaar validate-multimodal --queries benchmarks/multimodal_v3/queries.jsonl --model artifacts/multimodal_v3.json --output results/multimodal_v3/evaluation.json

demo:
	@python scripts/demo.py
