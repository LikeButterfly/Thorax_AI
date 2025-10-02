FROM python:3.10-slim

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Установка рабочей директории
WORKDIR /app

# Копирование файлов зависимостей
COPY requirements/ requirements/

# Установка Python зависимостей с оптимизацией для Docker
RUN pip install --no-cache-dir --timeout 1000 --retries 5 --upgrade pip && \
    pip install --no-cache-dir --timeout 1000 --retries 5 -r requirements/base.txt

# Копирование исходного кода
COPY app/ app/

# Создание директорий
RUN mkdir -p uploads app/static

# Установка переменных окружения
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Открытие порта
EXPOSE 8000

# Команда запуска
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
