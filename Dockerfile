 
# Используем легкий образ Python 

FROM python:3.11-slim

# Устанавливаем рабочую директорию внутри контейнера 
WORKDIR /app


# Устанавливаем системные зависимости для работы с PostgreSQL и FAISS

RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Копируем файл с зависимостями 
COPY requirements.txt .

# Устанавливаем библиотеки 
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь код проекта и данные
COPY . .

 
# Открываем порт 8000 для FastAPI 

EXPOSE 8000

#Команда для запуска сервера 
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]