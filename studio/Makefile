.PHONY: install run test docker
install:
	pip install -r requirements.txt && pip install pytest httpx
run:
	uvicorn app.main:app --reload --port 8000
test:
	pytest -q
docker:
	docker compose up --build
