from __future__ import annotations

import collections
import json
import os
import sys
import tempfile
import time
import traceback
import urllib.error
import urllib.request

import google.generativeai as genai
import telebot
from telebot import types

from bot.config import (
    AI_PROVIDER,
    BOT_TOKEN,
    GEMINI_API_KEY,
    MAX_DOWNLOAD_MB,
    MAX_SEND_MB,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    OLLAMA_TIMEOUT_SEC,
)
from converter import convert
from converter.utils import get_extension
from storage import (
    create_company,
    delete_company,
    delete_file,
    find_documents,
    get_document,
    list_companies,
    list_files,
    save_document,
)
from storage.zip_utils import extract_zip, is_supported_file, validate_zip

if not BOT_TOKEN:
    raise SystemExit("\u041d\u0435 \u0437\u0430\u0434\u0430\u043d BOT_TOKEN.")

bot = telebot.TeleBot(BOT_TOKEN)
telebot.apihelper.CONNECT_TIMEOUT = 30
telebot.apihelper.READ_TIMEOUT = 60

COMMON_DOCUMENTS_COMPANY = "Common"
user_history = collections.defaultdict(lambda: collections.deque(maxlen=5))
pending_file_company: dict[int, str] = {}

try:
    with open("tools.json", "r", encoding="utf-8") as f:
        TOOLS_DEF = json.load(f)
except Exception as exc:
    print(f"Error loading tools.json: {exc}")
    TOOLS_DEF = []

if AI_PROVIDER == "gemini" and GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)


def _redact(text: str) -> str:
    if BOT_TOKEN and BOT_TOKEN in text:
        return text.replace(BOT_TOKEN, "<TOKEN>")
    return text


def _log(message: str, level: str = "INFO") -> None:
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level}] {message}", flush=True)
    sys.stdout.flush()
    sys.stderr.flush()


def _cleanup_temp_file(path: str | None) -> None:
    if not path:
        return
    try:
        if os.path.exists(path):
            os.remove(path)
        parent = os.path.dirname(path)
        if parent and os.path.isdir(parent) and not os.listdir(parent):
            os.rmdir(parent)
    except Exception as exc:
        _log(f"Temporary cleanup failed for {path}: {exc}", "DEBUG")


def _send_document_with_retry(
    chat_id: int,
    path: str,
    retries: int = 3,
    delay: int = 2,
    visible_file_name: str | None = None,
) -> None:
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            with open(path, "rb") as f:
                bot.send_document(
                    chat_id,
                    f,
                    visible_file_name=visible_file_name or os.path.basename(path),
                )
            return
        except Exception as exc:
            last_exc = exc
            if attempt < retries:
                time.sleep(delay)
    if last_exc:
        raise last_exc


def _send_found_documents(chat_id: int, query: str) -> bool:
    docs = [path for path in find_documents(query) if not path.endswith(".meta.txt")]
    if not docs:
        return False

    sent = 0
    for path in docs[:20]:
        if not os.path.isfile(path):
            continue
        if os.path.getsize(path) > MAX_SEND_MB * 1024 * 1024:
            bot.send_message(chat_id, f"\u0424\u0430\u0439\u043b \u0441\u043b\u0438\u0448\u043a\u043e\u043c \u0431\u043e\u043b\u044c\u0448\u043e\u0439: {os.path.basename(path)}")
            continue
        _send_document_with_retry(chat_id, path)
        sent += 1

    if len(docs) > 20:
        bot.send_message(chat_id, f"\u041f\u043e\u043a\u0430\u0437\u0430\u043d\u044b \u043f\u0435\u0440\u0432\u044b\u0435 20 \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u043e\u0432 \u0438\u0437 {len(docs)}.")
    return sent > 0


def _parse_company_and_file(text: str) -> tuple[str, str] | None:
    value = text.strip()
    if not value:
        return None

    value_norm = value.casefold()
    for company in sorted(list_companies(), key=len, reverse=True):
        company_norm = company.casefold()
        if value_norm == company_norm:
            return None
        if value_norm.startswith(company_norm + " "):
            return company, value[len(company):].strip()

    parts = value.split(maxsplit=1)
    if len(parts) == 2:
        return parts[0], parts[1].strip()
    return None


def get_main_keyboard() -> types.ReplyKeyboardMarkup:
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton("\u2753 \u041f\u043e\u043c\u043e\u0449\u044c"),
        types.KeyboardButton("\U0001f4c4 \u041c\u043e\u0438 \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u044b"),
    )
    return markup


@bot.message_handler(commands=["start", "help"])
def cmd_start(message):
    help_text = (
        "👋 Привет! Я помогаю хранить, искать, скачивать и конвертировать документы.\n\n"
        "📥 Как добавить файл\n"
        "- Отправьте документ, фото или ZIP-архив - я сохраню его в общее хранилище.\n"
        "- Чтобы сохранить в компанию, сначала напишите: /add_file <компания>\n"
        "- Или прикрепите файл с подписью: сохранить в <компания>\n\n"
        "🔄 Конвертация\n"
        "- Прикрепите файл и укажите в подписи нужный формат: pdf, docx, doc, txt, jpg, jpeg или png.\n\n"
        "🔎 Поиск\n"
        "- Пишите обычным текстом, например: Покажи документы по ТОО Тексол Транс\n"
        "- Кнопка \"📄 Мои документы\" покажет файлы из общего хранилища.\n\n"
        "📋 Команды\n"
        "/help - показать эту помощь\n"
        "/create_company <имя> - создать компанию\n"
        "/delete_company <имя> - удалить компанию\n"
        "/list_companies - список компаний\n"
        "/list_files <запрос> - список файлов по запросу\n"
        "/download <компания> <файл> - скачать файл\n"
        "/add_file <компания> - сохранить следующий файл в компанию\n"
        "/delete_file <компания> <файл> - удалить файл"
    )
    bot.reply_to(message, help_text, reply_markup=get_main_keyboard())


@bot.message_handler(commands=["create_company"])
def cmd_create_company(message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return bot.reply_to(message, "\u0418\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d\u0438\u0435: /create_company <\u0438\u043c\u044f>")
    if create_company(parts[1]):
        bot.reply_to(message, f"\u2705 \u041a\u043e\u043c\u043f\u0430\u043d\u0438\u044f \u0441\u043e\u0437\u0434\u0430\u043d\u0430: {parts[1]}")
    else:
        bot.reply_to(message, "\u274c \u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0441\u043e\u0437\u0434\u0430\u0442\u044c \u043a\u043e\u043c\u043f\u0430\u043d\u0438\u044e.")


@bot.message_handler(commands=["delete_company"])
def cmd_delete_company(message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return bot.reply_to(message, "\u0418\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d\u0438\u0435: /delete_company <\u0438\u043c\u044f>")
    if delete_company(parts[1]):
        bot.reply_to(message, f"\u2705 \u041a\u043e\u043c\u043f\u0430\u043d\u0438\u044f \u0443\u0434\u0430\u043b\u0435\u043d\u0430: {parts[1]}")
    else:
        bot.reply_to(message, "\u274c \u041a\u043e\u043c\u043f\u0430\u043d\u0438\u044f \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u0430.")


@bot.message_handler(commands=["list_companies", "companies"])
def cmd_list_companies(message):
    companies = list_companies()
    if not companies:
        return bot.reply_to(message, "\u041a\u043e\u043c\u043f\u0430\u043d\u0438\u0439 \u043f\u043e\u043a\u0430 \u043d\u0435\u0442.")
    bot.reply_to(message, "\u041a\u043e\u043c\u043f\u0430\u043d\u0438\u0438:\n" + "\n".join(companies))


@bot.message_handler(commands=["list_files"])
def cmd_list_files(message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return bot.reply_to(message, "\u0418\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d\u0438\u0435: /list_files <\u0437\u0430\u043f\u0440\u043e\u0441>")
    files = list_files(parts[1])
    if not files:
        return bot.reply_to(message, "\u0424\u0430\u0439\u043b\u044b \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u044b.")
    bot.reply_to(message, f"\u0424\u0430\u0439\u043b\u044b \u043f\u043e \u0437\u0430\u043f\u0440\u043e\u0441\u0443 \"{parts[1]}\":\n" + "\n".join(files[:100]))


@bot.message_handler(commands=["delete_file"])
def cmd_delete_file(message):
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        return bot.reply_to(message, "\u0418\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d\u0438\u0435: /delete_file <\u043a\u043e\u043c\u043f\u0430\u043d\u0438\u044f> <\u0444\u0430\u0439\u043b>")
    if delete_file(parts[1], parts[2]):
        bot.reply_to(message, "\u2705 \u0424\u0430\u0439\u043b \u0443\u0434\u0430\u043b\u0435\u043d.")
    else:
        bot.reply_to(message, "\u274c \u0424\u0430\u0439\u043b \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d.")


@bot.message_handler(commands=["download"])
def cmd_download(message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return bot.reply_to(message, "\u0418\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d\u0438\u0435: /download <\u043a\u043e\u043c\u043f\u0430\u043d\u0438\u044f> <\u0444\u0430\u0439\u043b>")

    parsed = _parse_company_and_file(parts[1])
    if not parsed:
        return bot.reply_to(message, "\u0418\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d\u0438\u0435: /download <\u043a\u043e\u043c\u043f\u0430\u043d\u0438\u044f> <\u0444\u0430\u0439\u043b>")

    company, filename = parsed
    document = get_document(company, filename)
    if not document:
        return bot.reply_to(message, "\u274c \u0424\u0430\u0439\u043b \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d.")

    path, original_name = document
    if os.path.getsize(path) > MAX_SEND_MB * 1024 * 1024:
        return bot.reply_to(message, "\u0424\u0430\u0439\u043b \u0441\u043b\u0438\u0448\u043a\u043e\u043c \u0431\u043e\u043b\u044c\u0448\u043e\u0439 \u0434\u043b\u044f \u043e\u0442\u043f\u0440\u0430\u0432\u043a\u0438.")
    _send_document_with_retry(message.chat.id, path, visible_file_name=original_name)


@bot.message_handler(commands=["add_file"])
def cmd_add_file(message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return bot.reply_to(message, "\u0418\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d\u0438\u0435: /add_file <\u043a\u043e\u043c\u043f\u0430\u043d\u0438\u044f>")
    pending_file_company[message.chat.id] = parts[1].strip()
    bot.reply_to(message, f"\u041e\u043a. \u0421\u043b\u0435\u0434\u0443\u044e\u0449\u0438\u0439 \u0444\u0430\u0439\u043b \u0441\u043e\u0445\u0440\u0430\u043d\u044e \u0432 \"{parts[1].strip()}\".")


@bot.message_handler(content_types=["document", "photo"])
def on_document(message):
    _log(f"Received file from chat {message.chat.id}")

    is_photo = message.content_type == "photo"
    doc = message.photo[-1] if is_photo else message.document
    src_ext = "jpg" if is_photo else get_extension(doc.file_name or "")
    file_name = f"photo_{doc.file_id}.jpg" if is_photo else (doc.file_name or f"input.{src_ext or 'bin'}")
    caption = (message.caption or "").strip()
    caption_lower = caption.lower()
    is_zip = file_name.lower().endswith(".zip")

    if doc.file_size and doc.file_size > MAX_DOWNLOAD_MB * 1024 * 1024:
        return bot.reply_to(message, "\u274c \u0424\u0430\u0439\u043b \u0441\u043b\u0438\u0448\u043a\u043e\u043c \u0431\u043e\u043b\u044c\u0448\u043e\u0439.")

    if not is_zip and not is_supported_file(file_name):
        return bot.reply_to(
            message,
            "\u274c \u041d\u0435\u043f\u043e\u0434\u0434\u0435\u0440\u0436\u0438\u0432\u0430\u0435\u043c\u044b\u0439 \u0444\u043e\u0440\u043c\u0430\u0442. "
            "\u041f\u043e\u0434\u0434\u0435\u0440\u0436\u0438\u0432\u0430\u044e\u0442\u0441\u044f PDF, DOC/DOCX, TXT, XLS/XLSX, PPT/PPTX \u0438 \u0438\u0437\u043e\u0431\u0440\u0430\u0436\u0435\u043d\u0438\u044f.",
        )

    src_path: str | None = None
    try:
        file_info = bot.get_file(doc.file_id)
        data = bot.download_file(file_info.file_path)
        in_dir = tempfile.mkdtemp(prefix="in_")
        src_path = os.path.join(in_dir, file_name)
        with open(src_path, "wb") as f:
            f.write(data)

        if is_zip:
            is_valid, validation_msg = validate_zip(src_path)
            if not is_valid:
                return bot.reply_to(message, f"\u274c \u041e\u0448\u0438\u0431\u043a\u0430 \u0430\u0440\u0445\u0438\u0432\u0430: {validation_msg}")

            bot.reply_to(message, f"\U0001f4e6 {validation_msg}\n\u0420\u0430\u0441\u043f\u0430\u043a\u043e\u0432\u044b\u0432\u0430\u044e \u0438 \u0438\u043c\u043f\u043e\u0440\u0442\u0438\u0440\u0443\u044e...")
            extracted_files = extract_zip(src_path)
            if not extracted_files:
                return bot.reply_to(message, "\u274c \u0412 \u0430\u0440\u0445\u0438\u0432\u0435 \u043d\u0435\u0442 \u043f\u043e\u0434\u0434\u0435\u0440\u0436\u0438\u0432\u0430\u0435\u043c\u044b\u0445 \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u043e\u0432.")

            success_count = 0
            failed_files: list[tuple[str, str]] = []
            for original_name, file_path in extracted_files.items():
                try:
                    save_document(COMMON_DOCUMENTS_COMPANY, file_path, original_name)
                    success_count += 1
                except Exception as exc:
                    failed_files.append((original_name, str(exc)[:80]))

            report = f"\u2705 \u0418\u043c\u043f\u043e\u0440\u0442\u0438\u0440\u043e\u0432\u0430\u043d\u043e: {success_count}/{len(extracted_files)}"
            if failed_files:
                report += f"\n\n\u041e\u0448\u0438\u0431\u043a\u0438 ({len(failed_files)}):"
                for name, error in failed_files[:5]:
                    report += f"\n- {name}: {error}"
            return bot.reply_to(message, report)

        company_to_save = pending_file_company.pop(message.chat.id, "")
        for prefix in ("store to ", "store ", "\u0441\u043e\u0445\u0440\u0430\u043d\u0438\u0442\u044c \u0432 ", "\u0441\u043e\u0445\u0440\u0430\u043d\u0438\u0442\u044c ", "\u0432 ", "save to ", "save "):
            if caption_lower.startswith(prefix):
                company_to_save = caption[len(prefix):].strip()
                break

        target = caption_lower.lstrip(".")
        known_targets = {"pdf", "docx", "doc", "txt", "jpg", "jpeg", "png"}
        if target and target in known_targets and not company_to_save:
            bot.reply_to(message, f"\u2699\ufe0f \u041a\u043e\u043d\u0432\u0435\u0440\u0442\u0438\u0440\u0443\u044e {src_ext or '?'} -> {target}...")
            out_path = convert(src_path, target)
            try:
                if os.path.getsize(out_path) > MAX_SEND_MB * 1024 * 1024:
                    return bot.reply_to(message, "\u274c \u0420\u0435\u0437\u0443\u043b\u044c\u0442\u0430\u0442 \u0441\u043b\u0438\u0448\u043a\u043e\u043c \u0431\u043e\u043b\u044c\u0448\u043e\u0439.")
                _send_document_with_retry(message.chat.id, out_path)
            finally:
                _cleanup_temp_file(out_path)
            return

        company = company_to_save or COMMON_DOCUMENTS_COMPANY
        save_document(company, src_path, file_name)
        if company == COMMON_DOCUMENTS_COMPANY:
            bot.reply_to(message, f"\u2705 \u0424\u0430\u0439\u043b \u0437\u0430\u0433\u0440\u0443\u0436\u0435\u043d:\n`{file_name}`", parse_mode="Markdown")
        else:
            bot.reply_to(message, f"\u2705 \u0424\u0430\u0439\u043b \u0441\u043e\u0445\u0440\u0430\u043d\u0435\u043d \u0432 \"{company}\":\n`{file_name}`", parse_mode="Markdown")

    except Exception as exc:
        error_msg = _redact(str(exc))[:200]
        _log(f"File processing error: {error_msg}\n{traceback.format_exc()[-500:]}", "ERROR")
        bot.reply_to(message, f"\u274c \u041e\u0448\u0438\u0431\u043a\u0430 \u043e\u0431\u0440\u0430\u0431\u043e\u0442\u043a\u0438: {error_msg}")
    finally:
        _cleanup_temp_file(src_path)


@bot.callback_query_handler(func=lambda call: call.data.startswith("save_to_"))
def handle_document_classification(call):
    bot.answer_callback_query(call.id, "\u0424\u0430\u0439\u043b\u044b \u0442\u0435\u043f\u0435\u0440\u044c \u0441\u043e\u0445\u0440\u0430\u043d\u044f\u044e\u0442\u0441\u044f \u0430\u0432\u0442\u043e\u043c\u0430\u0442\u0438\u0447\u0435\u0441\u043a\u0438. \u041e\u0442\u043f\u0440\u0430\u0432\u044c\u0442\u0435 \u0444\u0430\u0439\u043b \u0437\u0430\u043d\u043e\u0432\u043e.")


def _ai_enabled() -> bool:
    if AI_PROVIDER == "ollama":
        return bool(OLLAMA_BASE_URL and OLLAMA_MODEL)
    if AI_PROVIDER == "gemini":
        return bool(GEMINI_API_KEY)
    return False


def _generate_ai_text(prompt: str) -> str:
    if AI_PROVIDER == "ollama":
        url = f"{OLLAMA_BASE_URL}/v1/chat/completions"
        payload = {
            "model": OLLAMA_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": """
        Ты помощник по документообороту.

        Всегда отвечай только валидным JSON.

        Если нужно искать документы:

        {"tool":"find_documents","parameters":{"query":"..."}}

        Во всех остальных случаях:

        {"reply":"..."}

        Никогда не добавляй пояснений.
        Никогда не используй Markdown.
        Никогда не используй ```json.
        """
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0,
            "stream": False,
        }
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=OLLAMA_TIMEOUT_SEC) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Ollama недоступна: {exc}") from exc

        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError("Ollama вернула пустой ответ")
        return choices[0].get("message", {}).get("content", "").strip()

    if AI_PROVIDER == "gemini":
        model = genai.GenerativeModel("gemini-flash-latest")
        resp = model.generate_content(prompt)
        return resp.text.strip()

    raise RuntimeError(f"Неизвестный AI_PROVIDER: {AI_PROVIDER}")


def _strip_json_fence(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```json"):
        return raw[7:-3].strip()
    if raw.startswith("```"):
        return raw[3:-3].strip()
    return raw


@bot.message_handler(func=lambda m: True, content_types=["text"])
def on_text(message):
    text = message.text.strip()
    low = text.lower()

    if low in ("\u2753 \u043f\u043e\u043c\u043e\u0449\u044c", "\u043f\u043e\u043c\u043e\u0449\u044c", "help", "/help"):
        cmd_start(message)
        return

    if low in ("\U0001f4c4 \u043c\u043e\u0438 \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u044b", "\u043c\u043e\u0438 \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u044b"):
        if _send_found_documents(message.chat.id, COMMON_DOCUMENTS_COMPANY):
            bot.reply_to(message, "\u041f\u043e\u043a\u0430\u0437\u0430\u043b \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u044b \u0438\u0437 \u043e\u0431\u0449\u0435\u0433\u043e \u0445\u0440\u0430\u043d\u0438\u043b\u0438\u0449\u0430.")
        else:
            bot.reply_to(message, "\u0414\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u044b \u043f\u043e\u043a\u0430 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u044b.")
        return

    search_words = (
        "\u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442", "\u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u044b",
        "\u0444\u0430\u0439\u043b", "\u0444\u0430\u0439\u043b\u044b", "\u043f\u043e\u043a\u0430\u0436\u0438", "\u043d\u0430\u0439\u0434\u0438",
        "show", "find", "documents", "files",
    )
    if any(word in low for word in search_words):
        if _send_found_documents(message.chat.id, text):
            bot.reply_to(message, "\u041d\u0430\u0448\u0435\u043b \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u044b \u043f\u043e \u0437\u0430\u043f\u0440\u043e\u0441\u0443.")
        else:
            bot.reply_to(message, "\u0414\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u044b \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u044b.")
        return

    if not _ai_enabled():
        bot.reply_to(
            message,
            "\u041d\u0430\u043f\u0438\u0448\u0438\u0442\u0435 \u0437\u0430\u043f\u0440\u043e\u0441 \u0432\u0440\u043e\u0434\u0435 \"\u041f\u043e\u043a\u0430\u0436\u0438 \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u044b \u043f\u043e \u0422\u0435\u043a\u0441\u043e\u043b \u0422\u0440\u0430\u043d\u0441\" "
            "\u0438\u043b\u0438 \u043e\u0442\u043f\u0440\u0430\u0432\u044c\u0442\u0435 \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442/ZIP.",
        )
        return

    try:
        bot.send_chat_action(message.chat.id, "typing")
        companies = ", ".join(list_companies()) or "no companies"
        companies = list_companies()
        companies_text = "\n".join(f"- {c}" for c in companies) or "Нет компаний"

        prompt = f"""
        Ты работаешь в системе хранения документов.

        Компании:

        {companies_text}

        Запрос пользователя:

        {text}

        Определи намерение пользователя.

        Если он хочет найти, показать, скачать или открыть документы,
        верни JSON:

        {{
        "tool": "find_documents",
        "parameters": {{
            "query": "<запрос>"
        }}
        }}

        Если пользователь просто общается или задает вопрос,
        верни:

        {{
        "reply": "<ответ>"
        }}

        Ответ должен содержать только JSON.
        """
        raw = _strip_json_fence(_generate_ai_text(prompt))

        data = json.loads(raw)
        if data.get("tool") == "find_documents":
            query = data.get("parameters", {}).get("query", text)
            if _send_found_documents(message.chat.id, query):
                bot.reply_to(message, "\u041d\u0430\u0448\u0435\u043b \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u044b \u043f\u043e \u0437\u0430\u043f\u0440\u043e\u0441\u0443.")
            else:
                bot.reply_to(message, "\u0414\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u044b \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u044b.")
            return

        bot.reply_to(message, data.get("reply", "\u041d\u0435 \u043f\u043e\u043d\u044f\u043b \u0437\u0430\u043f\u0440\u043e\u0441. \u041f\u043e\u043f\u0440\u043e\u0431\u0443\u0439\u0442\u0435 \u043d\u0430\u043f\u0438\u0441\u0430\u0442\u044c \u043f\u0440\u043e\u0449\u0435."))
    except Exception as exc:
        bot.reply_to(message, f"\u274c \u041e\u0448\u0438\u0431\u043a\u0430 \u0418\u0418: {exc}")


def run():
    print("\u0411\u043e\u0442 \u0437\u0430\u043f\u0443\u0449\u0435\u043d. Ctrl+C - \u043e\u0441\u0442\u0430\u043d\u043e\u0432\u0438\u0442\u044c.")
    bot.infinity_polling(skip_pending=True)


if __name__ == "__main__":
    run()
