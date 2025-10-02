FROM nvidia/cuda:12.1.0-base-ubuntu22.04

# Устанавливаем переменные окружения для автоматической настройки
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC

# Устанавливаем Python и системные зависимости
RUN apt-get update && apt-get install -y \
    software-properties-common \
    && add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update \
    && apt-get install -y \
    python3.10 \
    python3.10-dev \
    python3.10-distutils \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем pip для Python 3.10
RUN curl -sS https://bootstrap.pypa.io/get-pip.py | python3.10

# Создаем симлинк для python
RUN ln -s /usr/bin/python3.10 /usr/bin/python

# Создаем рабочую директорию
WORKDIR /app

# Копируем requirements и устанавливаем зависимости
COPY requirements.txt .

# Устанавливаем PyTorch с CUDA 12.1 из официального индекса
RUN python3.10 -m pip install --no-cache-dir \
    torch==2.1.0+cu121 \
    torchvision==0.16.0+cu121 \
    torchaudio==2.1.0+cu121 \
    --index-url https://download.pytorch.org/whl/cu121

# Устанавливаем остальные зависимости
RUN python3.10 -m pip install --no-cache-dir -r requirements.txt

# Копируем код приложения
COPY app/ ./app/

# Создаем директорию для модели
RUN mkdir -p models

# Устанавливаем переменные окружения
ENV PYTHONPATH=/app
ENV MODEL_PATH=/app/models/swin_model_weights.pth

# Открываем порт
EXPOSE 8001

# Команда запуска
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
