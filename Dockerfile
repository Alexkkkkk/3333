FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1

# Копируем требования
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем всё (дизайн в static/ НЕ МЕНЯЕТСЯ)
COPY . .

# Твой скоростной запуск с лимитами V8
CMD ["python", "main.py"]
