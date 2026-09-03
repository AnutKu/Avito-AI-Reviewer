.PHONY: install dev up down logs test demo probe fmt

install:               ## поставить зависимости (uv)
	uv sync --extra dev

dev:                   ## локальный запуск с автоперезагрузкой, оффлайн-LLM
	TASKCREATER_LLM_FAKE=1 TASKCREATER_DATABASE_URL=sqlite+aiosqlite:///./taskcreater.db \
		uv run uvicorn app.main:app --reload

up:                    ## поднять сервис + Postgres в docker-compose
	docker compose up --build -d
	@echo "→ http://localhost:$${TASKCREATER_PORT:-8000}/docs"

up-fake:               ## то же, но без вызовов LLM (демо без ключей)
	TASKCREATER_LLM_FAKE=1 docker compose up --build -d

down:                  ## остановить и снести том БД
	docker compose down -v

logs:
	docker compose logs -f api

test:                  ## тесты (оффлайн-LLM, sqlite)
	TASKCREATER_LLM_FAKE=1 TASKCREATER_DATABASE_URL=sqlite+aiosqlite:///./.pytest.db \
		uv run pytest

demo:                  ## сквозной сценарий против запущенного сервиса
	uv run python scripts/demo.py

probe:                 ## прогон по основным эндпоинтам: вход → выход (python3 scripts/probe.py --help)
	python3 scripts/probe.py

fmt:
	uv run ruff check --fix . && uv run ruff format .
