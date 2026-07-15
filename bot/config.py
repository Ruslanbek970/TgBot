"""
Настройки бота (Разработчик 3).

Токен читается из переменной окружения BOT_TOKEN (или из файла .env).
Никаких токенов в коде — .env в git не коммитим (см. .gitignore).
"""
import os

try:
    from dotenv import load_dotenv
    load_dotenv()  # подхватит .env из корня проекта, если он есть
except ImportError:
    pass  # python-dotenv не обязателен, можно задать переменную вручную

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# Лимит на скачивание файла ботом (Telegram getFile ~20 МБ).
MAX_DOWNLOAD_MB = 20

# Лимит на отправку файла ботом (Telegram Bot API — до 50 МБ).
MAX_SEND_MB = 50
