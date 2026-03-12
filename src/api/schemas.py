from typing import List, Optional
from pydantic import BaseModel

"""
Pydantic схемы для API запросов и ответов.
Определяют структуру входных и выходных данных для эндпоинтов.
"""

"""
Схема входящего запроса на рекомендации.
user_id: Идентификатор пользователя.
query_text: Текст поискового запроса.
top_k: Количество желаемых рекомендаций (по умолчанию 5).
"""
class RecommendationRequest(BaseModel):
    user_id: int
    query_text: str
    top_k: int = 5

"""
Схема отдельного рекомендованного фильма.
id: Идентификатор фильма в БД.
title: Название фильма.
overview: Краткое описание фильма.
"""
class MovieSchema(BaseModel):
    id: int
    title: str
    overview: Optional[str] = None

"""
Схема полного ответа с рекомендациями.
movies: Список объектов фильмов.
explanation: Текстовое объяснение рекомендаций от LLM.
"""
class RecommendationResponse(BaseModel):
    movies: List[MovieSchema]
    explanation: str
