# Используем Python 3.11 для максимальной совместимости с новыми либами TON
FROM python:3.11-slim

# --- УСТАНОВКА СИСТЕМНЫХ ЗАВИСИМОСТЕЙ ---
# gcc, python3-dev и libpq-dev необходимы для компиляции либ (asyncpg, numpy)
# git нужен для установки библиотек напрямую из репозиториев GitHub
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
# Гарантирует, что логи (print) сразу попадают в консоль Bothost без задержек
ENV PYTHONUNBUFFERED=1
# Отключаем создание .pyc файлов для экономии места и чистоты сборки
ENV PYTHONDONTWRITEBYTECODE=1
# Указываем Python искать модули в текущей директории
ENV PYTHONPATH=/app

# --- ПОДГОТОВКА ЗАВИСИМОСТЕЙ ---
# Сначала копируем только requirements.txt для кэширования слоев сборки
COPY requirements.txt .

# Принудительно обновляем pip и устанавливаем пакеты без кэша,
# чтобы избежать использования старых "битых" версий библиотек
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# --- КОПИРОВАНИЕ ПРОЕКТА ---
# Копируем весь проект. Папка static/ с дизайном и картинками копируется полностью.
COPY . .

# Создаем папку для локальных данных (БД, логи) и выставляем права доступа
RUN mkdir -p /app/data && chmod 777 /app/data

# Проверка: выводим структуру для контроля (опционально, полезно при отладке)
RUN ls -R /app/static

# Финальная команда запуска ядра системы
CMD ["python", "main.py"]
