FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Маскирование ставится отдельным слоем и по флагу сборки: torch с
# transformers весят больше, чем всё остальное вместе, и образу без
# MASKING_ENABLED они не нужны. Веса модели в образ НЕ кладутся — бандл
# монтируется снаружи (см. docker-compose.yml): 700 МБ в слое образа
# пересобирались бы при каждой правке кода.
ARG WITH_MASKING=true
COPY requirements-masking.txt .
RUN if [ "$WITH_MASKING" = "true" ]; then \
        pip install --no-cache-dir -r requirements-masking.txt; \
    fi

COPY app ./app

EXPOSE 8010
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8010"]
