from prometheus_fastapi_instrumentator import Instrumentator
from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.future import select
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

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

# 1. Настройка MLflow
mlflow.set_tracking_uri("http://mlflow_server:5000")
mlflow.set_experiment("Movie_Recommendations")

app = FastAPI(
    title="Hybrid RecSys API",
    description="API для рекомендаций фильмов с использованием FAISS, ALS и LLM.",
    version="1.0.0"
)

# 2. Метрики Prometheus
instrumentator = Instrumentator().instrument(app)
instrumentator.expose(app)

@app.post("/api/v1/recommend", response_model=RecommendationResponse)
async def get_recommendations(
    request: RecommendationRequest,
    db: AsyncSession = Depends(get_db)
):
    start_time = time.time()
    
    # Оборачиваем MLflow в try-except, чтобы падение сервера логов не вешало всё приложение
    try:
        run = mlflow.start_run(nested=True)
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
    
    if not movie_ids:
        if run: mlflow.end_run()
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
    
    # Сохраняем порядок ранжирования
    for mid in movie_ids:
        if mid in movies_map:
            m = movies_map[mid]
            recommendations_list.append(MovieSchema(id=m.id, title=m.title, overview=m.overview))
            movie_titles.append(m.title)

    # 3. История пользователя
    user_history_titles = []
    user_history_str = ""
    try:
        history_query = (
            select(Movie.title, Rating.rating)
            .join(Movie, Movie.id == Rating.movie_id)
            .where(Rating.user_id == request.user_id)
            .order_by(desc(Rating.rating)).limit(5)
        )
        h_result = await db.execute(history_query)
        h_rows = h_result.all()
        user_history_titles = [r[0] for r in h_rows]
        user_history_str = ", ".join([f"{r[0]} ({r[1]})" for r in h_rows])
    except Exception as e:
        logger.warning(f"History fetch error: {e}")

    # 4. Получение объяснения от LLM
    explanation = await recommender_service.get_explanation(
        movie_titles, request.query_text, user_history_str
    )
    
    # 5. Завершаем логирование в MLflow
    if run:
        try:
            process_time = time.time() - start_time
            mlflow.log_metric("latency_seconds", process_time)
            mlflow.end_run()
        except Exception as e:
            logger.error(f"MLflow end_run error: {e}")
    
    return RecommendationResponse(
        recommendations=recommendations_list,
        explanation=explanation,
        user_history=user_history_titles
    )