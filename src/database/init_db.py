import asyncio
from src.database.session import engine
from src.database.models import Base

"""
Асинхронная инициализация базы данных.
Создает таблицы, если они не существуют.
Синхронные методы run_sync выполняются внутри асинхронного контекста подключения.
"""
async def init_db():
    async with engine.begin() as conn:
        """
        Удаление таблиц (закомментировано, так как очистит данные).
        await conn.run_sync(Base.metadata.drop_all)
        """
        await conn.run_sync(Base.metadata.create_all)
    print("Инициализация базы данных завершена.")

if __name__ == "__main__":
    asyncio.run(init_db())
