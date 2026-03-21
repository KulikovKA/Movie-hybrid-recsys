# Hybrid Movie Recommendation System

Гибридная рекомендательная система фильмов на основе FAISS, ALS и LLM. Проект использует FastAPI для API-слоя, Open WebUI как основной пользовательский интерфейс и стек наблюдаемости Prometheus + Grafana + MLflow.

## Что делает система

Сервис принимает пользовательский запрос и профиль пользователя, затем строит рекомендации в несколько шагов:
1. Контентный поиск по эмбеддингам через FAISS.
2. Коллаборативный сигнал по истории оценок через ALS.
3. Реранжирование и объяснение рекомендаций через LLM.

Результат: список фильмов и объяснение, почему именно эти фильмы подходят под запрос.

## Датасет

Источник данных:
https://www.kaggle.com/datasets/rounakbanik/the-movies-dataset

Используемые файлы из датасета:
- movies_metadata.csv
- ratings.csv
- keywords.csv
- credits.csv
- links.csv
- links_small.csv

После скачивания разместите CSV-файлы в директории data.

## Архитектура

Основная UML-диаграмма (единая):
- docs/uml/system_overview.puml

Рендер диаграммы для README:
- docs/uml/system_overview.png

![Unified System Diagram](docs/uml/system_overview.png)

## Основные возможности

- Гибридные рекомендации: FAISS + ALS.
- Персонализация по user_id.
- LLM-объяснения в ответе API.
- Интеграция с Open WebUI через tool/function.
- Метрики и мониторинг в Prometheus/Grafana.
- Трекинг параметров и latency в MLflow.

## Технологии

- Python 3.11
- FastAPI, SQLAlchemy, PostgreSQL
- sentence-transformers, FAISS, implicit (ALS)
- OpenAI-compatible LLM providers (Groq)
- Docker, Docker Compose
- Prometheus, Grafana, MLflow

## Структура проекта

```text
recsys_project/
├─ src/                          # backend API и сервисы рекомендаций
├─ scripts/                      # миграция CSV в PostgreSQL
├─ docs/uml/                     # UML-код диаграмм (PlantUML)
├─ docs/openwebui/               # интеграция Open WebUI tool/function
├─ data/                         # CSV, FAISS index, артефакты маппингов
├─ grafana/                      # provisioning и dashboards
├─ prometheus/                   # конфиг Prometheus
├─ docker-compose.yml
└─ requirements.txt
```

## Быстрый запуск

1. Подготовьте .env в корне проекта:

```env
POSTGRES_USER=myuser
POSTGRES_PASSWORD=mypassword
POSTGRES_DB=movie_recsys
GROQ_API_KEY=your_groq_key
# OPENROUTER_API_KEY=optional
# OPENAI_API_KEY=optional
```

В текущей конфигурации проекта достаточно `GROQ_API_KEY`. Ключи OpenRouter/OpenAI необязательны.

2. Убедитесь, что CSV из Kaggle лежат в data.

3. Поднимите сервисы:

```bash
docker compose up -d --build
```

4. Откройте сервисы:

- Open WebUI: http://localhost:3000
- FastAPI docs: http://localhost:8000/docs
- Grafana: http://localhost:3001
- Prometheus: http://localhost:9090
- MLflow: http://localhost:5000

## Open WebUI

Файл для интеграции:
- docs/openwebui/movie_recsys_tool.py

Инструкция:
- docs/openwebui/README.md

## Мониторинг

- Prometheus собирает метрики backend с endpoint /metrics.
- Grafana загружает дашборды из grafana/dashboards.
- MLflow хранит параметры и метрики запросов в эксперименте Movie_Recommendations.

## Локальная разработка без Docker

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn src.main:app --reload
```

## FAQ

**Почему мы не пушим "контейнеры Docker" в Git?**

Потому что в Git хранятся исходники и конфиги (`Dockerfile`, `docker-compose.yml`), а не сами контейнеры/образы. Контейнеры собираются локально командой `docker compose up --build`.

Если нужно распространять готовый образ, его публикуют в Docker Registry (например, Docker Hub/GHCR), а не в Git-репозиторий.

[^1]: Одноразовая миграция CSV в БД: `docker exec movie_backend python scripts/migrate_csv_to_sql.py`
