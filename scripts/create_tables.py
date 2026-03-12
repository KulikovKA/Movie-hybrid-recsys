"""
Скрипт для инициализации структуры базы данных.
Создает таблицы на основе моделей SQLAlchemy.
"""
import asyncio
import sys
import os

""" Добавляем корень проекта в путь, чтобы импорты из src работали """
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database.session import engine
from src.database.models import Base

async def init_models():
    """
    Асинхронная функция для создания таблиц.
    """
    async with engine.begin() as conn:
        """ 
        Удаляем старые таблицы (если нужно) и создаем новые.
        Внимание: run_sync вызывает синхронную функцию создания метаданных.
        """
        print("Создание таблиц в базе данных...")
        await conn.run_sync(Base.metadata.create_all)
    
    print("Таблицы успешно созданы!")

if __name__ == "__main__":
    asyncio.run(init_models())