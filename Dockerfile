FROM python:3.11-slim

WORKDIR /app

# Настройки для скоростной работы Python
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Установка зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем проект (дизайн в static/ не меняется)
COPY . .

# Запуск с твоими лимитами производительности
CMD ["python", "main.py"]
