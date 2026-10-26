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
