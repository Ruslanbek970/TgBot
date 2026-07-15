"""
Точка входа проекта.

Запуск:
    python run.py

Перед запуском:
    1) pip install -r requirements.txt
    2) установить LibreOffice (см. README)
    3) скопировать .env.example в .env и вписать BOT_TOKEN
"""
from bot.main import run

if __name__ == "__main__":
    run()
