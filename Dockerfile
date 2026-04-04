FROM python:3.11-slim

# Установка системных библиотек для работы с PostgreSQL и компиляции математических модулей
RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV PYTHONUNBUFFERED=1

# Сначала копируем только requirements для кэширования слоев сборки
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь проект. 
# ВАЖНО: папка static/ с logo.png и дизайном копируется как есть и не меняется.
COPY . .

# Создаем папку для логов/данных, если она нужна скрипту
RUN mkdir -p /app/data && chmod 777 /app/data

# Скоростной запуск с лимитами производительности Bothost
CMD ["python", "main.py"]
