from sqlalchemy import Column, Integer, String, Text, Boolean, Float, ForeignKey
from sqlalchemy.orm import DeclarativeBase, relationship

"""
Базовый класс для определения моделей SQLAlchemy.
Все модели приложения должны наследовать этот класс.
"""
class Base(DeclarativeBase):
    pass

"""
Модель таблицы фильмов.
Содержит информацию о фильме: название, описание, жанры.
Флаг is_processed указывает, был ли фильм обработан (например, для эмбеддингов).
"""
class Movie(Base):
    __tablename__ = "movies"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    overview = Column(Text)
    genres = Column(String)
    is_processed = Column(Boolean, default=False)

"""
Модель таблицы рейтингов.
Содержит оценки пользователей.
Связь Many-to-One с фильмом.
"""
class Rating(Base):
    __tablename__ = "ratings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, index=True)
    movie_id = Column(Integer, ForeignKey("movies.id"), index=True)
    rating = Column(Float)
