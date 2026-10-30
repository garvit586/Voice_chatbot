.PHONY: dev dev-api dev-web install lint type test check smoke migrate

install:
	pip install -e ".[dev]"
	cd web && npm install

migrate:
	python -m server.db.migrations

dev-api:
	uvicorn server.app.main:app --reload --port 8000

dev-web:
	cd web && npm run dev

dev:
	make migrate
	$(MAKE) -j2 dev-api dev-web

lint:
	ruff check server
	cd web && npm run lint

type:
	mypy server

test:
	pytest

check: lint type test

smoke:
	python scripts/smoke.py

docker-up:
	docker compose up --build -d

docker-down:
	docker compose down
