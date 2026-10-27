install:
	pip install -e ".[dev]"

run:
	uvicorn app.main:app --reload

test:
	pytest -q

test-ui:
	node --test "tests/js/*.test.mjs"

lint:
	ruff check .
	ruff format --check .

format:
	ruff format .

docker-up:
	docker compose up --build

pull-model:
	docker compose exec ollama ollama pull qwen2.5:7b
