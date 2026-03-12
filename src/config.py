"""
Файл конфигурации приложения.
Использует pydantic-settings для автоматической загрузки данных из .env.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    """
    Класс настроек проекта. 
    Поля должны соответствовать ключам в файле .env (регистр не важен).
    """
    
    """ Настройки базы данных PostgreSQL """
    POSTGRES_USER: str = Field(default="myuser")
    POSTGRES_PASSWORD: str = Field(default="mypassword")
    POSTGRES_DB: str = Field(default="movie_recsys")
    POSTGRES_HOST: str = Field(default="localhost")
    POSTGRES_PORT: int = Field(default=5433)
    
    """ 
    Поля, на которые ругался валидатор. 
    Добавляем их в класс, чтобы Pydantic знал, как их обрабатывать.
    """
    DATABASE_URL: str = Field(default="")
    OPENROUTER_API_KEY: str = Field(default="")

    """ 
    Настройка поведения Pydantic.
    env_file - имя файла, откуда брать данные.
    extra='ignore' - заставляет программу не падать, если в .env есть лишние переменные.
    """
    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8",
        extra="ignore"
    )

""" Инициализация глобального объекта настроек """
settings = Settings()