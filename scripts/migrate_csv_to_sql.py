"""
Скрипт миграции данных из CSV в PostgreSQL.
"""


import sys
import os

""" 
Добавляем родительскую директорию (корень проекта) в пути поиска модулей.
Это позволяет Python находить пакет 'src', даже если скрипт запущен из папки 'scripts'.
"""
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Теперь твои импорты будут работать:
from src.database.session import AsyncSessionLocal
from src.database.models import Movie, Rating


import os
import asyncio
import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.database.session import AsyncSessionLocal
from src.database.models import Movie, Rating
async def migrate_movies(session: AsyncSession):
    """ Миграция фильмов с защитой от пустых данных во всех полях """
    print(">>> Проверка файла movies_cleaned.csv...")
    file_path = 'data/movies_cleaned.csv'
    
    if not os.path.exists(file_path):
        print(f"!!! Ошибка: Файл {file_path} не найден!")
        return

    df = pd.read_csv(file_path)
    
    # 1. Удаляем дубликаты
    df = df.drop_duplicates(subset=['id'], keep='first')

    # 2. КРИТИЧЕСКИЙ ШАГ: Исправляем ВСЕ текстовые колонки сразу
    # Заменяем NaN на пустые строки или понятные заглушки
    df['title'] = df['title'].fillna('Unknown Title')
    df['overview'] = df['overview'].fillna('')
    df['genres'] = df['genres'].fillna('[]')
    
    movies_data = df.to_dict('records')
    
    print(f">>> Начинаем вставку {len(movies_data)} уникальных фильмов...")
    
    batch_size = 1000
    for i in range(0, len(movies_data), batch_size):
        batch = movies_data[i:i + batch_size]
        objects = []
        
        for item in batch:
            objects.append(Movie(
                id=int(item['id']),
                title=str(item['title']),
                overview=str(item['overview']),
                genres=str(item['genres']),
                is_processed=True
            ))
        
        session.add_all(objects)
        try:
            await session.commit()
            print(f"--- Загружено фильмов: {i + len(batch)} / {len(movies_data)}")
        except Exception as e:
            await session.rollback()
            print(f"!!! Ошибка в пачке на индексе {i}: {e}")
            # Если одна пачка битая, мы ее пропускаем и идем дальше
            continue


async def migrate_ratings(session: AsyncSession):
    """
    Миграция рейтингов из CSV в PostgreSQL.
    Для скорости используем pandas + sql alchemy (синхронный движок, так как to_sql не поддерживает асинхронность).
    """
    print(">>> Проверка файла ratings.csv...")
    # При старте скрипта из корня, путь data/ratings.csv.
    # Если запускаем из папки scripts, то ../data/ratings.csv
    file_path = 'data/ratings.csv'
    
    if not os.path.exists(file_path):
        print(f"!!! Ошибка: Файл {file_path} не найден! Пропускаем загрузку рейтингов.")
        return

    # Создаем синхронный движок для pandas
    from sqlalchemy import create_engine
    from src.config import settings

    # Получаем URL и меняем драйвер на синхронный (postgresql+psycopg2 или просто postgresql)
    # settings.DATABASE_URL обычно имеет вид postgresql+asyncpg://...
    # Нам нужен postgresql://... для pandas
    sync_db_url = settings.DATABASE_URL.replace("postgresql+asyncpg", "postgresql")
    
    # Если URL был relative/sqlite (вряд ли), это не сработает, но у нас postgres.
    engine = create_engine(sync_db_url)

    print(">>> Загрузка списка ID фильмов из базы для фильтрации...")
    try:
        valid_movie_ids = pd.read_sql("SELECT id FROM movies", con=engine)['id'].values
        valid_movie_set = set(valid_movie_ids)
        print(f"--- Найдено {len(valid_movie_set)} фильмов в базе.")
    except Exception as e:
        print(f"!!! Ошибка при чтении списка фильмов: {e}")
        return

    print(">>> Чтение ratings.csv с помощью pandas...")
    # Загружаем только нужные колонки
    chunks = pd.read_csv(file_path, usecols=['userId', 'movieId', 'rating'], chunksize=100000)
    
    print(">>> Начинаем вставку рейтингов (chunk by chunk)...")
    total_loaded = 0
    
    for chunk in chunks:
        # Переименовываем колонки под модель
        chunk = chunk.rename(columns={
            'userId': 'user_id',
            'movieId': 'movie_id'
        })

        # Фильтруем рейтинги, оставляем только те, что относятся к существующим фильмам
        original_len = len(chunk)
        chunk = chunk[chunk['movie_id'].isin(valid_movie_set)]
        filtered_len = len(chunk)
        if original_len != filtered_len:
            print(f"--- Отфильтровано {original_len - filtered_len} рейтингов (нет фильма в базе).")
        
        if chunk.empty:
            continue
        
        # Вставляем данные. if_exists='append' добавит строки.
        # index=False, чтобы не писать индекс pandas как колонку.
        try:
            chunk.to_sql('ratings', con=engine, if_exists='append', index=False, method='multi', chunksize=1000)
            total_loaded += len(chunk)
            print(f"--- Загружено рейтингов: {total_loaded}")
        except Exception as e:
            print(f"!!! Ошибка при загрузке чанка рейтингов: {e}")

async def main():
    """ Основная функция миграции """
    print("=== ЗАПУСК МИГРАЦИИ ===")
    
    print("1. Создаем таблицы (если их нет)...")
    # Импортируем создание таблиц
    from src.database.session import engine
    from src.database.models import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    async with AsyncSessionLocal() as session:
        try:
            await migrate_movies(session)
            # Миграция рейтингов (она внутри создает свой engine)
            await migrate_ratings(session)
            
            print("=== МИГРАЦИЯ ЗАВЕРШЕНА УСПЕШНО ===")
        except Exception as e:
            print(f"!!! ПРОИЗОШЛА ОШИБКА: {e}")
            await session.rollback()

if __name__ == "__main__":
    # Это обязательный блок для запуска скрипта из терминала
    asyncio.run(main())
    