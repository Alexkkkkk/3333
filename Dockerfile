# Используем Python 3.11 для максимальной совместимости с новыми либами TON
FROM python:3.11-slim

# Установка системных библиотек
# Добавлен git (на случай, если какая-то либа ставится напрямую из репозитория)
RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    libpq-dev \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

# Установка рабочей директории
WORKDIR /app

# Логи бота сразу попадают в панель
ENV PYTHONUNBUFFERED=1
# Отключаем создание .pyc файлов для экономии места
ENV PYTHONDONTWRITEBYTECODE=1

# Копируем requirements.txt
COPY requirements.txt .

# --- КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ ТУТ ---
# Добавляем --upgrade и --no-cache-dir, чтобы Docker не использовал битые старые слои
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Копируем весь проект
# Дизайн, логотипы и структура папки static/ сохраняются без изменений
COPY . .

# Настройка прав для папки данных
RUN mkdir -p /app/data && chmod 777 /app/data

# Запуск ядра
CMD ["python", "main.py"]
