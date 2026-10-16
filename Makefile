.PHONY: up down logs dev-frontend test

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f

dev-frontend:
	cd frontend && npm run dev

test:
	uv run pytest -q
