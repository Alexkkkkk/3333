FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1

# Копируем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем проект (дизайн в static/ НЕ МЕНЯЕТСЯ)
COPY . .

# Твой коронный запуск
CMD ["python", "main.py"]
