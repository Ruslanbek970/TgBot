# Образ для бота: Python + LibreOffice (движок конвертации) уже внутри.
# Благодаря этому «поставил и тестишь» — LibreOffice отдельно ставить не нужно.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# LibreOffice (Word/Excel/PPT -> PDF) + шрифты (латиница + кириллица, чтобы
# документы рендерились корректно). --no-install-recommends -> образ легче.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libreoffice-writer \
        libreoffice-calc \
        libreoffice-impress \
        fonts-liberation \
        fonts-dejavu \
        fonts-noto-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Сначала зависимости — этот слой кешируется отдельно от кода
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Затем код
COPY . .

# BOT_TOKEN приходит из окружения (docker compose env_file / -e), не зашит в образ
CMD ["python", "run.py"]
