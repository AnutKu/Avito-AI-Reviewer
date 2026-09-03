# Запуск через docker — из КОРНЯ репозитория (единый docker-compose.yml, единый .env).
# Здесь — только локальная разработка сервиса без докера.
.PHONY: install dev test demo probe fmt up down logs

install:               ## поставить зависимости (uv)
	uv sync --extra dev

dev:                   ## локальный запуск с автоперезагрузкой, оффлайн-LLM, sqlite
	TASKCREATER_LLM_FAKE=1 TASKCREATER_DATABASE_URL=sqlite+aiosqlite:///./taskcreater.db \
		uv run uvicorn app.main:app --reload

test:                  ## тесты (оффлайн-LLM, sqlite, без сети)
	TASKCREATER_LLM_FAKE=1 TASKCREATER_DATABASE_URL=sqlite+aiosqlite:///./.pytest.db \
		uv run pytest

demo:                  ## сквозной сценарий против запущенного сервиса (BASE_URL, дефолт :8082)
	BASE_URL=$${BASE_URL:-http://127.0.0.1:8082} uv run python scripts/demo.py

probe:                 ## прогон по основным эндпоинтам (python3 scripts/probe.py --help)
	python3 scripts/probe.py --base-url $${BASE_URL:-http://127.0.0.1:8082}

fmt:
	uv run ruff check --fix . && uv run ruff format .

# Обёртки над корневым compose — просто чтобы не выходить из каталога.
up:                    ## поднять только task-creater (+ общий postgres) из корневого compose
	cd .. && docker compose up -d --build postgres taskcreater
	@echo "→ http://localhost:$${TASKCREATER_PORT:-8082}/healthz  (Swagger: /task-creater/docs через кабинет)"

down:
	cd .. && docker compose down

logs:
	cd .. && docker compose logs -f taskcreater
