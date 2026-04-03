FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1

# Установка зависимостей ядра
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем проект (дизайн и logo.png в static/ НЕ МЕНЯЮТСЯ)
COPY . .

# Твой скоростной запуск с лимитами производительности
CMD ["python", "main.py"]
