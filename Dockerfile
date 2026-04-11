# Используем Python 3.11 для максимальной совместимости с новыми либами TON
FROM python:3.11-slim

# --- УСТАНОВКА СИСТЕМНЫХ ЗАВИСИМОСТЕЙ ---
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    libpq-dev \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

# Установка рабочей директории внутри контейнера
WORKDIR /app

# --- НАСТРОЙКИ ОКРУЖЕНИЯ ---
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONPATH=/app
ENV PORT=3000

# --- ПОДГОТОВКА ЗАВИСИМОСТЕЙ ---
COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# --- КОПИРОВАНИЕ ПРОЕКТА ---
# Копируем весь проект (папка static сохранится автоматически)
COPY . .

# Создаем папку для данных (чтобы БД была в сохранности)
RUN mkdir -p /app/data && chmod 777 /app/data

# Проверка структуры статики в логах сборки
RUN ls -R /app/static

# Открываем порт для внешней сети
EXPOSE 3000

# Запуск через основной скрипт
CMD ["python", "main.py"]
