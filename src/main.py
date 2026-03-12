from prometheus_fastapi_instrumentator import Instrumentator
from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from src.config import settings
from src.database.session import AsyncSessionLocal
from src.database.models import Movie
from src.api.deps import get_db
from src.api.schemas import RecommendationRequest, RecommendationResponse, MovieSchema
from src.services.recommender import recommender_service

import time
import mlflow

app = FastAPI(
    title="Hybrid RecSys API",
    description="API для рекомендаций фильмов с использованием FAISS, ALS и LLM.",
    version="1.0.0"
)

# 1. Включаем метрики Prometheus СРАЗУ после создания app
instrumentator = Instrumentator().instrument(app)
instrumentator.expose(app)

# 2. Настраиваем MLflow
mlflow.set_tracking_uri("http://mlflow_server:5000")
mlflow.set_experiment("Movie_Recommendations")
app = FastAPI(
    title="Hybrid RecSys API",
    description="API для рекомендаций фильмов с использованием FAISS, ALS и LLM.",
    version="1.0.0"
)


"""
Определяем эндпоинт POST /api/v1/recommend.
Принимает JSON запрос (RecommendationRequest).
Возвращает JSON ответ (RecommendationResponse).
Использует асинхронную сессию БД через dependency (get_db).
"""
@app.post("/api/v1/recommend", response_model=RecommendationResponse)
async def get_recommendations(
    request: RecommendationRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Основная логика эндпоинта:
    1. Получить ID рекомендованных фильмов через RecommenderService (ALS + FAISS).
    2. Извлечь данные о фильмах (название, описание) из PostgreSQL по этим ID.
    3. Сформировать список названий фильмов.
    4. Получить текстовое объяснение от LLM (OpenRouter).
    5. Залогировать параметры и метрики в MLflow.
    6. Вернуть структурированный ответ.
    """
    
    start_time = time.time()
    
    """ Начинаем запись в MLflow """
    with mlflow.start_run():
        
        """ Логируем параметры запроса """
        mlflow.log_param("user_id", request.user_id)
        mlflow.log_param("query", request.query_text)
        mlflow.log_param("top_k", request.top_k)
        
        """ 1. Получение ID фильмов из ML-сервиса """
        movie_ids = await recommender_service.get_recommendations(
            request.user_id, 
            request.query_text, 
            request.top_k
        )
        
        if not movie_ids:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Не найдено подходящих фильмов."
            )
            
        """ 2. Получение данных о фильмах из БД """
        query = select(Movie).where(Movie.id.in_(movie_ids))
        result = await db.execute(query)
        movies = result.scalars().all()
        
        movies_map = {m.id: m for m in movies}
        
        recommendations_list = []
        movie_titles = []
        
        for mid in movie_ids:
            if mid in movies_map:
                movie = movies_map[mid]
                recommendations_list.append(
                    MovieSchema(
                        id=movie.id,
                        title=movie.title,
                        overview=movie.overview
                    )
                )
                movie_titles.append(movie.title)
                
        if not recommendations_list:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Фильмы найдены в индексе, но отсутствуют в базе данных."
            )

        """ 4. Получение объяснения от LLM """
        explanation = await recommender_service.get_explanation(
            movie_titles, 
            request.query_text
        )
        
        """ 5. Считаем время выполнения и логируем метрики """
        process_time = time.time() - start_time
        mlflow.log_metric("latency_seconds", process_time)
        mlflow.log_metric("movies_returned", len(recommendations_list))
        
        """ 6. Возврат ответа """
        return RecommendationResponse(
            movies=recommendations_list,
            explanation=explanation
        )
    
if __name__ == "__main__":
    import uvicorn
    """
    Запуск сервера uvicorn для разработки.
    В продакшене лучше запускать через gunicorn или docker entrypoint.
    """
    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=True)
