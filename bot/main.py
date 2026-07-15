"""
Телеграм-бот — МИНИМАЛЬНАЯ РАБОЧАЯ ВЕРСИЯ (зона Разработчика 3).

Уже умеет:
  • принять файл и сконвертировать (Word->PDF, PDF->Word, картинка->PDF ...)
    через модуль converter;
  • по запросу "документы по <компания>" выдать доки из модуля storage.

Разработчик 3 дальше расширяет команды/логику. Соседние модули трогать не нужно —
достаточно их публичного API: converter.convert() и storage.find_documents().
"""
from __future__ import annotations

import os
import tempfile
import time
import traceback

import telebot

from bot.config import BOT_TOKEN, MAX_DOWNLOAD_MB, MAX_SEND_MB
from converter import convert, ConverterError
from converter.utils import cleanup, get_extension
from storage import find_documents, list_companies

if not BOT_TOKEN:
    raise SystemExit(
        "Не задан BOT_TOKEN. Скопируйте .env.example в .env и впишите токен от @BotFather."
    )

bot = telebot.TeleBot(BOT_TOKEN)

# Больше времени на скачивание/отдачу крупных документов.
telebot.apihelper.CONNECT_TIMEOUT = 30
telebot.apihelper.READ_TIMEOUT = 60

# Префиксы, по которым распознаём запрос документов из хранилища.
_DOC_PREFIXES = ("документы по", "документы", "/docs")


def _redact(text: str) -> str:
    """Вырезать токен из текста, чтобы он не утёк в чат или логи."""
    if BOT_TOKEN and BOT_TOKEN in text:
        return text.replace(BOT_TOKEN, "<TOKEN>")
    return text


def _send_document_with_retry(chat_id, path, retries=3, delay=2):
    """
    Отправить документ с повтором.

    Сглаживает разовые сетевые сбои (SSLWantWriteError, таймауты) при отдаче
    файла в Telegram. На стабильном сервере такое редко, но с домашней сети
    случается.
    """
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            with open(path, "rb") as f:
                bot.send_document(chat_id, f, visible_file_name=os.path.basename(path))
            return
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            print(f"[warn] отправка не удалась, попытка {attempt}/{retries}: {type(exc).__name__}")
            if attempt < retries:
                time.sleep(delay)
    raise last_exc


@bot.message_handler(commands=["start", "help"])
def cmd_start(message):
    companies = ", ".join(list_companies()) or "пока пусто"
    bot.reply_to(
        message,
        "Привет! Я умею:\n\n"
        "📄 *Конвертировать файлы.* Пришли документ, в подписи укажи формат "
        "(`pdf` или `docx`). По умолчанию: Word/Excel/картинка → PDF, PDF → Word.\n\n"
        "🔎 *Выдавать документы по компании.* Напиши: `документы по <название>`\n"
        f"Компании в базе: {companies}",
        parse_mode="Markdown",
    )


@bot.message_handler(content_types=["document"])
def on_document(message):
    doc = message.document
    src_ext = get_extension(doc.file_name or "")

    # целевой формат: из подписи к файлу, иначе — по умолчанию
    target = (message.caption or "").strip().lower().lstrip(".")
    if not target:
        target = "docx" if src_ext == "pdf" else "pdf"

    # готча: Telegram не даёт боту скачать файл больше ~20 МБ
    if doc.file_size and doc.file_size > MAX_DOWNLOAD_MB * 1024 * 1024:
        bot.reply_to(message, f"Файл больше {MAX_DOWNLOAD_MB} МБ — я не могу его скачать.")
        return

    bot.reply_to(message, f"Конвертирую {src_ext or '?'} → {target}…")

    src_path = out_path = None
    try:
        # 1) скачиваем файл во временную папку
        file_info = bot.get_file(doc.file_id)
        data = bot.download_file(file_info.file_path)
        in_dir = tempfile.mkdtemp(prefix="in_")
        src_path = os.path.join(in_dir, doc.file_name or f"input.{src_ext or 'bin'}")
        with open(src_path, "wb") as f:
            f.write(data)

        # 2) конвертируем (вся логика — в модуле Разработчика 2)
        out_path = convert(src_path, target)

        # 3) проверяем лимит на отдачу
        if os.path.getsize(out_path) > MAX_SEND_MB * 1024 * 1024:
            bot.reply_to(message, f"Результат больше {MAX_SEND_MB} МБ — не могу отправить.")
            return

        # 4) отправляем результат (с повтором на случай сетевого сбоя)
        _send_document_with_retry(message.chat.id, out_path)

    except ConverterError as exc:
        bot.reply_to(message, f"Не получилось: {exc}")
    except Exception:  # бот не должен падать от одного файла
        # НЕ показываем сырую ошибку пользователю — в её тексте может быть токен
        # (Telegram включает токен в URL запроса). В консоль пишем без токена.
        print("[error]", _redact(traceback.format_exc()))
        bot.reply_to(message, "Не удалось отправить результат — похоже, сетевой сбой. Попробуй ещё раз.")
    finally:
        # чистим временные файлы (конфиденциальность + диск)
        cleanup(src_path, out_path)
        if src_path:
            cleanup(os.path.dirname(src_path))
        if out_path:
            cleanup(os.path.dirname(out_path))


@bot.message_handler(func=lambda m: True, content_types=["text"])
def on_text(message):
    text = message.text.strip()
    low = text.lower()

    # распознаём "документы по X" / "документы X" / "/docs X"
    query = None
    for prefix in _DOC_PREFIXES:
        if low.startswith(prefix):
            query = text[len(prefix):].strip(" :«»\"'@")
            break

    if query is None:
        bot.reply_to(
            message,
            "Не понял. Напиши `документы по <компания>` или пришли файл на конвертацию.",
            parse_mode="Markdown",
        )
        return

    if not query:
        companies = ", ".join(list_companies()) or "пусто"
        bot.reply_to(message, f"Уточни компанию. В базе: {companies}")
        return

    files = find_documents(query)
    if not files:
        bot.reply_to(message, f"По запросу «{query}» ничего не нашёл.")
        return

    bot.reply_to(message, f"Нашёл {len(files)} документ(ов) по «{query}»:")
    for path in files:
        try:
            _send_document_with_retry(message.chat.id, path)
        except Exception:  # noqa: BLE001
            print("[error]", _redact(traceback.format_exc()))
            bot.send_message(message.chat.id, f"Не смог отправить: {os.path.basename(path)}")


def run():
    """Запустить бота (long polling)."""
    print("Бот запущен. Ctrl+C — остановить.")
    bot.infinity_polling(skip_pending=True)


if __name__ == "__main__":
    run()
