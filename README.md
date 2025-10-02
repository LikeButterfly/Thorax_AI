# ThoraxAI - Система анализа КТ органов грудной клетки

## Описание

ThoraxAI - это система автоматического анализа компьютерных томографий органов грудной клетки с использованием искусственного интеллекта. Основная цель системы - обнаружение патологий в КТ исследованиях с использованием модели Swin Transformer

## Основные возможности

- **Автоматическая классификация КТ исследований** на два класса: «без патологии» и «с патологией»
- **Обработка DICOM файлов** из ZIP архивов с поддержкой различных структур
- **Веб-интерфейс** для загрузки и просмотра результатов
- **API для интеграции** с внешними системами
- **Генерация отчетов** в формате Excel с детальной статистикой
- **Визуализация патологий** с возможностью скачивания изображений и DICOM файлов
- **Управление файлами** с возможностью массовой очистки
- **Отслеживание батчей** загрузки с детальной статистикой

## Архитектура системы

### Компоненты

1. **Основной сервис (FastAPI)** - веб-приложение и API
2. **ML сервис** - сервис машинного обучения на основе Swin Transformer
3. **База данных PostgreSQL** - хранение метаданных и результатов
4. **Файловое хранилище** - DICOM файлы и извлеченные изображения

### ML Модель

- **Архитектура**: Swin Transformer (swin_base_patch4_window7_224)
- **Классы**: 2 (норма, патология)
- **Метрики качества**:
  - F1 Score: **0.999**
  - ROC AUC: **0.995**

### Алгоритм анализа

1. **Извлечение изображений** из DICOM файлов с применением различных контрастов по WW WL
2. **Предсказание на уровне кадров** с порогом вероятности 0.6
3. **Агрегация на уровне исследования** с минимальной долей положительных кадров 12%
4. **Доверительные интервалы** для статистической надежности

## Системные требования

### Аппаратные требования

- **GPU**: NVIDIA GPU с поддержкой CUDA
- **RAM**: минимум 8GB, рекомендуется 16GB+
- **Дисковое пространство**: зависит от объема данных

### Программные требования

- Docker и Docker Compose
- NVIDIA Container Toolkit (для GPU)

## Быстрый старт

### Установка NVIDIA Container Toolkit (для GPU)

Для работы с GPU необходимо [установить NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html#with-apt-ubuntu-debian):

```bash
# 1. Configure the production repository:
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg \
  && curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
    sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
    sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
```

```bash
# Optionally, configure the repository to use experimental packages:
sudo sed -i -e '/experimental/ s/^#//g' /etc/apt/sources.list.d/nvidia-container-toolkit.list
```

```bash
# 2. Update the packages list from the repository:
sudo apt-get update
```

```bash
# 3. Install the NVIDIA Container Toolkit packages:
export NVIDIA_CONTAINER_TOOLKIT_VERSION=1.17.8-1
  sudo apt-get install -y \
      nvidia-container-toolkit=${NVIDIA_CONTAINER_TOOLKIT_VERSION} \
      nvidia-container-toolkit-base=${NVIDIA_CONTAINER_TOOLKIT_VERSION} \
      libnvidia-container-tools=${NVIDIA_CONTAINER_TOOLKIT_VERSION} \
      libnvidia-container1=${NVIDIA_CONTAINER_TOOLKIT_VERSION}
```

### Запуск с GPU (рекомендуется)

```bash
# Клонируйте репозиторий
git clone <repository-url>
```

```bash
cd Thorax_AI
```

```bash
# Запустите систему
docker-compose up -d
```

### Запуск с CPU

Для запуска на CPU необходимо внести изменения в `docker-compose.yml`:

1. Удалите строку `runtime: nvidia` из сервиса `ml-service`
2. Измените переменную окружения `DEVICE=cuda` на `DEVICE=cpu`

Также в `ml-service/Dockerfile` замените установку PyTorch на CPU версию:

```dockerfile
FROM ubuntu:22.04

# ... остальные инструкции ...

RUN python3.10 -m pip install --no-cache-dir \
    torch==2.1.0 \
    torchvision==0.16.0 \
    torchaudio==2.1.0 \
    --index-url https://download.pytorch.org/whl/cpu
```

## Использование

### Веб-интерфейс

1. Откройте браузер и перейдите по адресу `http://localhost:8000`
2. Загрузите ZIP архивы с DICOM исследованиями (до 400 файлов)
3. Дождитесь завершения обработки
4. Просмотрите результаты и скачайте отчеты

#### Доступные страницы:
- **Главная** (`/`) - загрузка новых исследований
- **Исследования** (`/studies`) - просмотр всех исследований с фильтрацией
- **Загрузки** (`/batches`) - история загрузок и батчей
- **Файлы** (`/cleanup`) - управление файлами и очистка

## Структура проекта

```
Thorax_AI/
├── app/                   # Основное приложение FastAPI
│   ├── api/               # API endpoints
│   ├── core/              # Конфигурация и middleware
│   ├── db/                # База данных
│   ├── models/            # SQLAlchemy модели
│   ├── schemas/           # Pydantic схемы
│   ├── services/          # Бизнес-логика
│   ├── static/            # Статические файлы
│   └── templates/         # HTML шаблоны
├── ml-service/            # ML сервис
│   ├── app/               # ML приложение
│   ├── models/            # Веса модели
│   └── Dockerfile         # Контейнер ML сервиса
├── data/                  # Данные исследований
├── uploads/               # Загруженные файлы
├── docker-compose.yml     # Конфигурация Docker
└── Dockerfile            # Основной контейнер
```

## Формат выходных данных

Система генерирует Excel отчеты со следующими колонками:

| Колонка | Описание | Формат |
|---------|----------|--------|
| `path_to_study` | Путь к исследованию | String |
| `study_uid` | Идентификатор исследования (DICOM) | String |
| `series_uid` | Идентификатор серии (DICOM) | String |
| `probability_of_pathology` | Вероятность патологии (0.0-1.0) | Float |
| `pathology` | Норма/патология (0/1) | Integer |
| `processing_status` | Статус обработки | String |
| `time_of_processing` | Время обработки (секунды) | Float |
| `ci_95` | Предельные вероятности для 95% доверительного интервала | Object |

### Дополнительные колонки (при наличии патологий)

| Колонка | Описание | Формат |
|---------|----------|--------|
| `most_dangerous_pathology_type` | Тип наиболее опасной патологии | String |
| `pathology_localization` | Локализация патологии (x_min,x_max,y_min,y_max,z_min,z_max) | Float Array |

## Производительность

- **Время обработки**: ≤ 10 минут на исследование
- **Поддерживаемые форматы**: DICOM файлы в ZIP архивах
- **Максимальный размер файла**: 2GB
- **Максимальное количество файлов**: 400 за раз

## Мониторинг и логирование

- Логи доступны через Docker Compose: `docker-compose logs -f`
- Health check endpoints:
  - Основной сервис: `http://localhost:8000/health`
  - ML сервис: `http://localhost:8001/health`

## Развертывание на сервере

Система развернута на сервере с процессором Intel Ice Lake и 500GB дискового пространства. Время обработки исследований на сервере может быть значильно больше, чем на GPU (RTX 3090), но остается в пределах требований (≤ 10 минут)

**Важно**: Из-за ограниченного дискового пространства (500GB) рекомендуется регулярно очищать файлы исследований

## Технические особенности

- **Автоматическое определение оптимальной серии** для анализа
- **Поддержка multi-frame DICOM** файлов
- **Статистический анализ** с доверительными интервалами
- **Масштабируемая архитектура** с возможностью горизонтального масштабирования
- **Управление файлами** с возможностью массовой очистки
- **Отслеживание активных загрузок** для предотвращения конфликтов
