# Используем Python 3.11 для максимальной совместимости с новыми либами TON
FROM python:3.11-slim

# Установка системных библиотек для работы с PostgreSQL и компиляции математических модулей (numpy/fft)
RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    libpq-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Установка рабочей директории
WORKDIR /app

# PYTHONUNBUFFERED гарантирует, что логи бота сразу попадают в панель Bothost
ENV PYTHONUNBUFFERED=1

# Сначала копируем только requirements для кэширования слоев сборки (ускоряет редеплой)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь проект. 
# ВАЖНО: папка static/ с logo.png и дизайном копируется как есть и не меняется.
# Согласно твоим правилам, index.html останется в папке static.
COPY . .

# Создаем папку для логов/данных, если она нужна скрипту
RUN mkdir -p /app/data && chmod 777 /app/data

# Скоростной запуск с лимитами производительности Bothost
# NODE_OPTIONS прописываются в настройках контейнера Bothost, здесь запускаем Python
CMD ["python", "main.py"]
