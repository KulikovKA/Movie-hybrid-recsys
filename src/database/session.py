from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from src.config import settings

"""
Инициализация асинхронного движка SQLAlchemy.
Используем URL из настроек.
"""
engine = create_async_engine(settings.DATABASE_URL, echo=True)

"""
Создание фабрики сессий.
Используется для получения новых сессий в приложении и при миграциях.
"""
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False
)
