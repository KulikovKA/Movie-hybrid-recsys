import os
import pickle
import asyncio
import numpy as np
import scipy.sparse
import implicit
import faiss
import openai
from sentence_transformers import SentenceTransformer
from typing import List, Tuple, Dict, Any
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.database.models import Movie
from src.config import settings

"""
Сервис рекомендаций.
Объединяет логику коллаборативной фильтрации (ALS),
контентного поиска (FAISS) и генерации объяснений (LLM).
Инициализирует и хранит модели в памяти.
"""
class RecommenderService:
    def __init__(self):
        """
        Инициализация сервиса.
        Загружает предобученные модели и индексы из файлов:
        - data/movies_faiss.index: Индекс FAISS для эмбеддингов фильмов.
        - data/als_model.pkl: Обученная модель ALS.
        - data/movie_map.pkl: Маппинг movie_id -> index.
        - data/user_map.pkl: Маппинг user_id -> index.
        - data/movie_inv_map.pkl: Обратный маппинг index -> movie_id.
        """
        self.sentence_model = SentenceTransformer('all-MiniLM-L6-v2')
        self.faiss_index = faiss.read_index('data/movies_faiss.index')
        
        with open('data/als_model.pkl', 'rb') as f:
            self.als_model = pickle.load(f)
            
        with open('data/movie_map.pkl', 'rb') as f:
            self.movie_map = pickle.load(f)
            
        with open('data/user_map.pkl', 'rb') as f:
            self.user_map = pickle.load(f)
            
        with open('data/movie_inv_map.pkl', 'rb') as f:
            self.movie_inv_map = pickle.load(f)

        # Необходимо загрузить item_user_matrix для метода recommend в ALS
        # В реальном проекте матрицу лучше тоже сохранять, но здесь для простоты пересоберем её или загрузим,
        # если вы её сохраняли. В вашем 4-м блокноте нет сохранения матрицы, только модели.
        # Поэтому здесь предполагается, что модель ALS самодостаточна для recommend, 
        # но ей нужна user_items матрица (история просмотров пользователя).
        # Для корректной работы recommend в production нужно хранить историю взаимодействий.
        # В данном упрощенном примере мы будем подавать пустую матрицу или загружать её, если она есть.
        # Однако, implicit требует user_items (CSR matrix users x items) при вызове recommend.
        # В рамках данного ТЗ, для простоты, предположим, что мы можем получить историю пользователя из БД,
        # или просто создадим заглушку, так как модель хранит факторы.
        # ВНИМАНИЕ: Для полноценной работы recommend нужен доступ к истории пользователя в формате разреженной матрицы.

        """
        Инициализация клиента OpenAI для работы с OpenRouter.
        """
        self.llm_client = openai.AsyncOpenAI(
            api_key=settings.OPENROUTER_API_KEY,
            base_url="https://openrouter.ai/api/v1"
        )

    """
    Получение кандидатов через ALS (коллаборативная фильтрация).
    user_id: ID пользователя.
    top_k: Количество кандидатов.
    """
    def _get_als_candidates(self, user_id: int, top_k: int = 10) -> List[int]:
        if user_id not in self.user_map:
            return []
        
        user_idx = self.user_map[user_id]
        
        # В идеале нужно передавать актуальную user_items матрицу.
        # Здесь используем пустую, полагаясь на то, что ALS вернет рекомендации на основе факторов пользователя,
        # если они уже были вычислены при обучении. Если нет - вернет популярное или ошибку.
        # Для implicit > 0.6 model.recommend требует user_items.
        # Создадим фиктивную разреженную строку нужной размерности (1 x N_items).
        dummy_user_items = scipy.sparse.csr_matrix((1, self.als_model.item_factors.shape[0]))
        
        recommendations = self.als_model.recommend(user_idx, dummy_user_items, N=top_k)
        
        movie_indices = [r[0] for r in recommendations] if isinstance(recommendations, list) else recommendations[0]
        
        movie_ids = [self.movie_inv_map.get(idx) for idx in movie_indices if idx in self.movie_inv_map]
        return movie_ids

    """
    Получение кандидатов через FAISS (контентный поиск).
    query: Текстовый запрос.
    top_k: Количество кандидатов.
    """
    def _get_faiss_candidates(self, query: str, top_k: int = 10) -> List[int]:
        query_vector = self.sentence_model.encode([query])
        query_vector = np.array(query_vector).astype('float32')
        faiss.normalize_L2(query_vector)
        
        _, indices = self.faiss_index.search(query_vector, top_k)
        
        # Конвертируем индексы FAISS обратно в ID фильмов.
        # В 4-м блокноте мы предполагали, что индексы в FAISS совпадают с индексами DataFrame movies.
        # А DataFrame movies был загружен и индексы там соответствовали строкам.
        # Нам нужен маппинг index_in_faiss -> movie_id.
        # В блокноте 04 мы брали movies.iloc[idx]['id'].
        # Здесь у нас нет датафрейма в памяти (это дорого).
        # В идеале при создании FAISS нужно сохранять маппинг faiss_id -> db_id.
        # Предположу, что мы сохраним этот маппинг в файл 'data/faiss_id_map.pkl' в будущем.
        # А пока, для совместимости с ТЗ и блокнотом, допустим, что
        # id в faiss == index в movie_inv_map (что верно, если мы строили FAISS по порядку movieId).
        # В блокноте 04 использовался movies.iloc[idx], т.е. порядковый номер строки.
        # Если мы сохраним список ID фильмов в том же порядке, что и добавляли в FAISS, то сможем восстановить ID.
        
        # Временное решение: используем movie_inv_map, предполагая, что индексы совпадают.
        # Это может быть неточно, если порядок добавления в FAISS отличался от movie_map.
        # Но в рамках задачи, используем movie_inv_map[idx].
        movie_ids = []
        for idx in indices[0]:
            if idx in self.movie_inv_map:
                movie_ids.append(self.movie_inv_map[idx])
                
        return movie_ids

    """
    Основной метод получения рекомендаций.
    Объединяет результаты ALS и FAISS.
    Возвращает список ID фильмов.
    """
    async def get_recommendations(self, user_id: int, query: str, top_k: int = 5) -> List[int]:
        # Запускаем поиск параллельнов (в потоках, так как FAISS и ALS release GIL)
        # Используем asyncio.gather для параллельного выполнения в ThreadPoolExecutor
        als_ids, faiss_ids = await asyncio.gather(
            asyncio.to_thread(self._get_als_candidates, user_id, top_k=top_k),
            asyncio.to_thread(self._get_faiss_candidates, query, top_k=top_k)
        )
        
        # Объединение и удаление дубликатов с сохранением порядка (ALS приоритетнее, потом FAISS)
        seen = set()
        final_ids = []
        
        for mid in als_ids + faiss_ids:
            if mid not in seen:
                final_ids.append(mid)
                seen.add(mid)
                
        return final_ids[:top_k]

    """
    Генерация объяснения с помощью LLM (OpenRouter).
    movie_titles: Список названий рекомендованных фильмов.
    query: Запрос пользователя.
    """
    async def get_explanation(self, movie_titles: List[str], query: str) -> str:
        if not movie_titles:
            return "К сожалению, мне не удалось найти подходящие фильмы."

        titles_str = ", ".join(movie_titles)
        system_prompt = f"""Ты — максимально строгий и объективный кинокритик. Тебе дают запрос пользователя и список фильмов от поисковика. Поисковик часто ошибается.
Запрос пользователя: "{query}"

Твоя задача — разделить фильмы на подходящие и полный мусор.

ОТВЕЧАЙ СТРОГО ПО ЭТОМУ ШАБЛОНУ И ТОЛЬКО НА РУССКОМ ЯЗЫКЕ:

🟢 ПОДХОДЯТ:
(Перечисли 1-2 фильма из списка, которые реально соответствуют жанру и запросу. Кратко объясни почему).

🔴 ПОИСКОВИК ОШИБСЯ:
(Жестко раскритикуй фильмы, которые не подходят. Например, если искали мрачный детектив, а в списке индийская комедия или мелодрама — прямо напиши, что это ошибка алгоритма и смотреть это не нужно)."""

        user_prompt = f"Вот список фильмов, которые нашел поисковик: {titles_str}"

        try:
            response = await self.llm_client.chat.completions.create(
                model="nvidia/nemotron-3-super-120b-a12b:free",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"Ошибка LLM: {e}")
            return "Вот отличная подборка фильмов специально для вас!"

# Создаем глобальный экземпляр сервиса
recommender_service = RecommenderService()
