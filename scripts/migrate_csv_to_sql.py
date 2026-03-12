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

async def main():
    """ Основная функция миграции """
    print("=== ЗАПУСК МИГРАЦИИ ===")
    async with AsyncSessionLocal() as session:
        try:
            await migrate_movies(session)
            print("=== МИГРАЦИЯ ЗАВЕРШЕНА УСПЕШНО ===")
        except Exception as e:
            print(f"!!! ПРОИЗОШЛА ОШИБКА: {e}")
            await session.rollback()

if __name__ == "__main__":
    # Это обязательный блок для запуска скрипта из терминала
    asyncio.run(main())
    