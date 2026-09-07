FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
# Данные курса и команды обслуживания — часть образа, а не только репозитория.
# Без data/ контейнер не находит сохранённые разборы и молча поднимается с
# демонстрационным курсом; без scripts/ внутрь нельзя зайти и перезагрузить
# курс руками. И то и другое уже случилось на живом стенде.
COPY data ./data
COPY scripts ./scripts

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
