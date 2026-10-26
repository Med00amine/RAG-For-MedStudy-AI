install:
	pip install -e ".[dev]"

run:
	uvicorn app.main:app --reload

test:
	pytest -q

lint:
	ruff check .
	ruff format --check .

format:
	ruff format .

docker-up:
	docker compose up --build

pull-model:
	docker compose exec ollama ollama pull llama3.2
