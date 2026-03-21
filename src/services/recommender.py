import os
import pickle
import asyncio
import numpy as np
import faiss
import openai
import json
import re
from sentence_transformers import SentenceTransformer
from typing import List, Tuple, Dict, Any

class RecommenderService:
    def __init__(self):
        print(">>> [START] Инициализация RecommenderService (Final Filter Edition)...")
        groq_key = os.getenv("GROQ_API_KEY")
        self.models_to_try = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]
        self.llm_client = openai.AsyncOpenAI(api_key=groq_key, base_url="https://api.groq.com/openai/v1")
        self.sentence_model = SentenceTransformer('all-MiniLM-L6-v2')
        
        try:
            self.faiss_index = faiss.read_index('data/movies_faiss.index')
            print(f">>> [OK] FAISS загружен. Векторов: {self.faiss_index.ntotal}")
        except Exception as e:
            print(f"!!! [ERROR] FAISS не загружен: {e}")
            self.faiss_index = None

        self.movie_map, self.user_map, self.movie_inv_map = {}, {}, {}
        self._load_data()

    def _load_data(self):
        try:
            with open('data/movie_map.pkl', 'rb') as f: self.movie_map = pickle.load(f)
            with open('data/user_map.pkl', 'rb') as f: self.user_map = pickle.load(f)
            with open('data/movie_inv_map.pkl', 'rb') as f: self.movie_inv_map = pickle.load(f)
            print(">>> [OK] Данные маппинга загружены.")
        except Exception as e:
            print(f"!!! [ERROR] Ошибка загрузки данных: {e}")

    def _get_faiss_candidates(self, query: str, top_k: int = 50) -> List[Tuple[int, float]]:
        if not self.faiss_index: return []
        query_vec = self.sentence_model.encode([query.lower()]).astype('float32')
        faiss.normalize_L2(query_vec)
        distances, indices = self.faiss_index.search(query_vec, top_k)
        return [(int(self.movie_inv_map.get(idx, idx)), float(d)) for d, idx in zip(distances[0], indices[0]) if idx != -1]

    async def get_recommendations(self, user_id: int, query: str, top_k: int = 30) -> List[int]:
        # Шаг 1: Улучшаем запрос (Translation + Expansion)
        enrich_prompt = f"Convert this movie query to a detailed English description: '{query}'. Example: 'Superheroes' -> 'Action movies about people with superpowers, Marvel, DC, Avengers'."
        try:
            res = await self.llm_client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": enrich_prompt}],
                max_tokens=50
            )
            search_query = res.choices[0].message.content
        except:
            search_query = query

        # Шаг 2: Получаем расширенный пул кандидатов для более точной фильтрации
        candidate_pool_size = max(40, top_k * 6)
        candidates = await asyncio.to_thread(self._get_faiss_candidates, search_query, top_k=candidate_pool_size)
        return [c[0] for c in candidates]

    @staticmethod
    def _keyword_fallback(movie_candidates: List[Dict[str, Any]], query: str, limit: int = 5) -> Dict[str, Any]:
        stopwords = {
            "и", "в", "на", "с", "по", "для", "про", "где", "что", "как", "или", "а", "но",
            "the", "and", "with", "for", "from", "about", "that", "this", "movie", "film",
        }
        tokens = [t.lower() for t in re.findall(r"[A-Za-zА-Яа-я0-9]+", query) if len(t) >= 3]
        tokens = [t for t in tokens if t not in stopwords]

        scored = []
        for movie in movie_candidates:
            haystack = " ".join([
                str(movie.get("title", "")),
                str(movie.get("overview", "")),
                str(movie.get("genres", "")),
            ]).lower()
            score = sum(1 for t in tokens if t in haystack)
            if score > 0:
                scored.append((score, movie))

        scored.sort(key=lambda x: x[0], reverse=True)
        recs = []
        for _, movie in scored[:limit]:
            recs.append({
                "title": movie.get("title", "Untitled"),
                "description": (movie.get("overview") or "Описание отсутствует")[:400],
                "reason": "Совпадение по ключевым словам запроса в описании/жанрах.",
            })

        return {"recommendations": recs}

    async def get_explanation(self, movie_candidates: List[Dict[str, Any]], query: str, user_history_str: str = "") -> str:
        if not movie_candidates:
            return json.dumps({"recommendations": []}, ensure_ascii=False)

        compact_candidates = [
            {
                "title": m.get("title", ""),
                "overview": (m.get("overview") or "")[:600],
                "genres": m.get("genres", ""),
            }
            for m in movie_candidates[:30]
        ]
        candidates_json = json.dumps(compact_candidates, ensure_ascii=False)
        
        prompt = f"""Запрос пользователя: "{query}".
История пользователя (если есть): "{user_history_str}".
Список кандидатов от алгоритма (title + overview + genres): {candidates_json}

Твоя задача:
1. Выбери из списка ТОЛЬКО те фильмы, которые действительно подходят под запрос.
2. Оценивай по смыслу overview и жанрам, а не только по title.
3. Оставь максимум 5 лучших совпадений.
4. Если ни один фильм не подходит, верни пустой список.

Ответь СТРОГО в формате JSON на русском:
{{"recommendations": [{{"title": "название", "description": "описание", "reason": "почему это ИДЕАЛЬНО подходит"}}]}}"""

        for model_name in self.models_to_try:
            try:
                response = await self.llm_client.chat.completions.create(
                    model=model_name,
                    messages=[{"role": "system", "content": "Ты — строгий кинокритик. Ты либо находишь идеал, либо не рекомендуешь ничего."},
                              {"role": "user", "content": prompt}],
                    temperature=0.1
                )
                content = response.choices[0].message.content
                match = re.search(r'\{.*\}', content, re.DOTALL)
                if match:
                    parsed = json.loads(match.group(0))
                    if parsed.get("recommendations"):
                        return json.dumps(parsed, ensure_ascii=False)
            except:
                continue

        fallback = self._keyword_fallback(movie_candidates, query, limit=5)
        return json.dumps(fallback, ensure_ascii=False)

recommender_service = RecommenderService()