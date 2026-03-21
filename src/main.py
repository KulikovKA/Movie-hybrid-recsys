from prometheus_fastapi_instrumentator import Instrumentator
from prometheus_client import Counter, Histogram
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.future import select
from sqlalchemy import desc, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
import re

from src.config import settings
from src.database.session import AsyncSessionLocal
from src.database.models import Movie, Rating
from src.api.deps import get_db
from src.api.schemas import RecommendationRequest, RecommendationResponse, MovieSchema
from src.services.recommender import recommender_service
import json
import time
import mlflow
import logging

# Настраиваем логирование, чтобы видеть ошибки в консоли docker
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Custom Prometheus metrics for recommender quality and performance.
RECS_REQUESTS_TOTAL = Counter(
    "movie_recs_requests_total",
    "Total number of recommendation API requests.",
)
RECS_LLM_LATENCY_SECONDS = Histogram(
    "movie_recs_llm_latency_seconds",
    "LLM explanation generation latency in seconds.",
    buckets=(0.1, 0.25, 0.5, 1, 2, 3, 5, 8, 13, 21, 34),
)
RECS_RETURNED_COUNT = Histogram(
    "movie_recs_returned_count",
    "Number of recommendations returned by API.",
    buckets=(0, 1, 2, 3, 5, 8, 10, 15, 20, 30),
)
RECS_LLM_EMPTY_TOTAL = Counter(
    "movie_recs_llm_empty_total",
    "Number of responses where LLM returned an empty recommendations list.",
)

# 1. Настройка MLflow
mlflow.set_tracking_uri("http://mlflow_server:5000")
mlflow.set_experiment("Movie_Recommendations")

app = FastAPI(
    title="Hybrid RecSys API",
    description="API для рекомендаций фильмов с использованием FAISS, ALS и LLM.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8501",
        "http://127.0.0.1:8501",
        "http://localhost:3000",
        "http://127.0.0.1:3000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. Метрики Prometheus
instrumentator = Instrumentator().instrument(app)
instrumentator.expose(app)

@app.post("/api/v1/recommend", response_model=RecommendationResponse)
async def get_recommendations(
    request: RecommendationRequest,
    db: AsyncSession = Depends(get_db)
):
    RECS_REQUESTS_TOTAL.inc()
    start_time = time.time()
    run = None

    try:
        # Оборачиваем MLflow в try-except, чтобы падение сервера логов не вешало всё приложение.
        # Не используем nested run, чтобы в UI не копились «висящие» parent RUNNING run.
        try:
            run = mlflow.start_run()
            mlflow.log_param("user_id", request.user_id)
            mlflow.log_param("query", request.query_text)
        except Exception as e:
            logger.error(f"MLflow error: {e}")
            run = None

        # 1. Получение ID фильмов от сервиса
        movie_ids = await recommender_service.get_recommendations(
            request.user_id,
            request.query_text,
            request.top_k
        )

        # 1.1 Lexical rescue: добавляем кандидатов по ключевым словам из title/overview/genres.
        # Это повышает recall для четких запросов вроде "зомби", "вампиры", "постапокалипсис".
        stopwords = {
            "и", "в", "на", "с", "по", "для", "про", "где", "что", "как", "или", "а", "но",
            "the", "and", "with", "for", "from", "about", "that", "this", "movie", "film",
        }
        tokens = [t.lower() for t in re.findall(r"[A-Za-zА-Яа-я0-9]+", request.query_text) if len(t) >= 4]
        tokens = [t for t in tokens if t not in stopwords]

        if tokens:
            conditions = []
            for t in tokens[:6]:
                pattern = f"%{t}%"
                conditions.extend([
                    Movie.title.ilike(pattern),
                    Movie.overview.ilike(pattern),
                    Movie.genres.ilike(pattern),
                ])

            lexical_query = select(Movie.id).where(or_(*conditions)).limit(max(40, request.top_k * 4))
            lexical_result = await db.execute(lexical_query)
            lexical_ids = [row[0] for row in lexical_result.all()]

            merged_ids = []
            seen = set()
            for mid in movie_ids + lexical_ids:
                if mid not in seen:
                    seen.add(mid)
                    merged_ids.append(mid)
            movie_ids = merged_ids

        if not movie_ids:
            RECS_RETURNED_COUNT.observe(0)
            return RecommendationResponse(
                recommendations=[],
                explanation=json.dumps({"recommendations": []}),
                user_history=[]
            )
        
        # 2. Получение данных о фильмах из БД
        query = select(Movie).where(Movie.id.in_(movie_ids))
        result = await db.execute(query)
        movies = result.scalars().all()

        movies_map = {m.id: m for m in movies}
        recommendations_list = []
        movie_titles = []
        movie_candidates = []

        # Сохраняем порядок ранжирования
        for mid in movie_ids:
            if mid in movies_map:
                m = movies_map[mid]
                recommendations_list.append(MovieSchema(id=m.id, title=m.title, overview=m.overview))
                movie_titles.append(m.title)
                movie_candidates.append({
                    "id": m.id,
                    "title": m.title,
                    "overview": m.overview,
                    "genres": m.genres,
                })

        # 3. История пользователя
        user_history_titles = []
        user_history_str = ""
        try:
            history_query = (
                select(Movie.id, Movie.title, func.max(Rating.rating).label("max_rating"))
                .join(Movie, Movie.id == Rating.movie_id)
                .where(Rating.user_id == request.user_id)
                .group_by(Movie.id, Movie.title)
                .order_by(desc("max_rating"))
                .limit(5)
            )
            h_result = await db.execute(history_query)
            h_rows = h_result.all()
            user_history_titles = [r[1] for r in h_rows]
            user_history_str = ", ".join([f"{r[1]} ({r[2]})" for r in h_rows])
        except Exception as e:
            logger.warning(f"History fetch error: {e}")

        # 4. Получение объяснения от LLM
        llm_start_time = time.time()
        explanation = await recommender_service.get_explanation(
            movie_candidates, request.query_text, user_history_str
        )
        RECS_LLM_LATENCY_SECONDS.observe(time.time() - llm_start_time)

        llm_rec_count = 0
        try:
            explanation_obj = json.loads(explanation) if explanation else {}
            llm_rec_count = len(explanation_obj.get("recommendations", []) or [])
        except Exception:
            llm_rec_count = 0
        if llm_rec_count == 0:
            RECS_LLM_EMPTY_TOTAL.inc()

        # 5. Логирование метрик в MLflow
        if run:
            try:
                process_time = time.time() - start_time
                mlflow.log_metric("latency_seconds", process_time)
                mlflow.log_metric("llm_latency_seconds", time.time() - llm_start_time)
                mlflow.log_metric("returned_recommendations_count", len(recommendations_list))
            except Exception as e:
                logger.error(f"MLflow metric logging error: {e}")

        RECS_RETURNED_COUNT.observe(len(recommendations_list))

        return RecommendationResponse(
            recommendations=recommendations_list,
            explanation=explanation,
            user_history=user_history_titles
        )
    finally:
        if run:
            try:
                active_run = mlflow.active_run()
                if active_run and active_run.info.run_id == run.info.run_id:
                    mlflow.end_run()
            except Exception as e:
                logger.error(f"MLflow end_run error: {e}")