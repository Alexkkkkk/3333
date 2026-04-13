FROM python:3.11-slim

# Установка системных утилит
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    libpq-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Копируем и устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir python-dotenv

# Копируем проект
COPY . .

# Права на папку данных
RUN mkdir -p /app/data && chmod 777 /app/data

EXPOSE 3000

CMD ["python", "main.py"]
