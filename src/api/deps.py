from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
from src.database.session import AsyncSessionLocal

"""
Зависимость FastAPI для получения асинхронной сессии БД.
Создается сессия для каждого запроса api и автоматически закрывается после его завершения.
"""
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
