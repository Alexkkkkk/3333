# Используем Python 3.11 для максимальной совместимости с новыми либами TON
FROM python:3.11-slim

# Установка системных библиотек для работы с PostgreSQL и компиляции математических модулей (numpy/fft)
# gcc, python3-dev и libpq-dev необходимы для корректной установки asyncpg и numpy
RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    libpq-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Установка рабочей директории внутри контейнера
WORKDIR /app

# PYTHONUNBUFFERED=1 гарантирует, что логи бота (print) сразу попадают в панель Bothost
ENV PYTHONUNBUFFERED=1

# Сначала копируем только requirements.txt для кэширования слоев сборки.
# Это значительно ускоряет последующие редеплои, если зависимости не менялись.
COPY requirements.txt .

# Установка зависимостей (включая pytoniq, numpy, asyncpg)
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь проект целиком. 
# ВАЖНО: папка static/ с logo.png, index.html и всем дизайном копируется "как есть".
# Мы строго соблюдаем правило: дизайн и картинки не меняются.
COPY . .

# Создаем папку для локальных данных или логов, если скрипту нужно писать файлы
RUN mkdir -p /app/data && chmod 777 /app/data

# Финальная команда запуска. 
# Параметры NODE_OPTIONS из твоего .env будут применены самой платформой Bothost,
# а этот CMD запускает основное ядро системы.
CMD ["python", "main.py"]
