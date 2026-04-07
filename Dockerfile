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

# --- ПОДГОТОВКА ЗАВИСИМОСТЕЙ ---
COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# --- КОПИРОВАНИЕ ПРОЕКТА ---
# Копируем весь проект (папка static сохранится автоматически)
COPY . .

# Создаем папку для данных
RUN mkdir -p /app/data && chmod 777 /app/data

# Проверка структуры статики в логах сборки
RUN ls -R /app/static

# Запуск
CMD ["python", "main.py"]
