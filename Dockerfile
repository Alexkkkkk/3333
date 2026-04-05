# Используем Python 3.11 для максимальной совместимости с новыми либами TON
FROM python:3.11-slim

# Установка системных библиотек
# gcc, python3-dev и libpq-dev необходимы для корректной установки asyncpg и numpy
# git добавлен для поддержки установки либ напрямую из репозиториев
RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    libpq-dev \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

# Установка рабочей директории внутри контейнера
WORKDIR /app

# PYTHONUNBUFFERED=1 гарантирует, что логи бота (print) сразу попадают в панель Bothost
ENV PYTHONUNBUFFERED=1
# Отключаем создание .pyc файлов для экономии места и чистоты сборки
ENV PYTHONDONTWRITEBYTECODE=1

# Сначала копируем только requirements.txt для кэширования слоев сборки.
COPY requirements.txt .

# --- КРИТИЧЕСКОЕ ОБНОВЛЕНИЕ ЗАВИСИМОСТЕЙ ---
# Мы принудительно обновляем pip и устанавливаем пакеты без кэша,
# чтобы Bothost не подтягивал старые "битые" версии библиотек.
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Копируем весь проект целиком. 
# ВАЖНО: папка static/ с твоим дизайном и картинками копируется полностью.
COPY . .

# Создаем папку для локальных данных и выставляем права доступа
RUN mkdir -p /app/data && chmod 777 /app/data

# Финальная команда запуска ядра системы
CMD ["python", "main.py"]
