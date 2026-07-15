from __future__ import annotations

import os
import tempfile
import time
import traceback
import subprocess
import json
import collections

import telebot
from telebot import types
import google.generativeai as genai

from bot.config import BOT_TOKEN, MAX_DOWNLOAD_MB, MAX_SEND_MB, GEMINI_API_KEY
from converter import convert, ConverterError
from converter.utils import cleanup, get_extension
from storage import find_documents, list_companies, create_company, save_document, delete_company, list_files, delete_file

if not BOT_TOKEN:
    raise SystemExit("Не задан BOT_TOKEN.")

bot = telebot.TeleBot(BOT_TOKEN)

telebot.apihelper.CONNECT_TIMEOUT = 30
telebot.apihelper.READ_TIMEOUT = 60

user_history = collections.defaultdict(lambda: collections.deque(maxlen=5))
pending_file_company: dict[int, str] = {}

try:
    with open("tools.json", "r", encoding="utf-8") as f:
        TOOLS_DEF = json.load(f)
except Exception as e:
    print(f"Error loading tools.json: {e}")
    TOOLS_DEF = []

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

def _redact(text: str) -> str:
    if BOT_TOKEN and BOT_TOKEN in text:
        return text.replace(BOT_TOKEN, "<TOKEN>")
    return text

def _send_document_with_retry(chat_id, path, retries=3, delay=2):
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            with open(path, "rb") as f:
                bot.send_document(chat_id, f, visible_file_name=os.path.basename(path))
            return
        except Exception as exc:
            last_exc = exc
            if attempt < retries:
                time.sleep(delay)
    raise last_exc

def _send_company_documents(chat_id, company: str) -> bool:
    docs = [path for path in find_documents(company) if not path.endswith(".meta.txt")]
    if not docs:
        return False
    for path in docs:
        _send_document_with_retry(chat_id, path)
    return True

def get_main_keyboard() -> types.ReplyKeyboardMarkup:
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton("🏢 Список компаний"),
        types.KeyboardButton("❓ Помощь")
    )
    return markup

@bot.message_handler(commands=["start", "help"])
def cmd_start(message):
    help_text = (
        "👋 *Привет!*\n"
        "Я AI-бот помощник.\n\n"
        "🛠 *Доступные команды:*\n"
        "• `/create_company <имя>` — Создать компанию\n"
        "• `/delete_company <имя>` — Удалить компанию\n"
        "• `/list_companies` — Список компаний\n"
        "• `/list_files <компания>` — Список файлов компании\n"
        "• `/add_file <компания>` — Добавить следующий отправленный файл в компанию\n"
        "• `/delete_file <компания> <имя_файла>` — Удалить файл\n\n"
        "🤖 *ИИ-режим:*\n"
        "Ты можешь просто писать мне текстом (например, «Удали компанию тексол»), "
        "и я пойму тебя. Отправь мне документ, чтобы сконвертировать его (pdf/docx), "
        "или подпиши файл `в <компания>`, чтобы сохранить его."
    )
    bot.reply_to(message, help_text, parse_mode="Markdown", reply_markup=get_main_keyboard())

# --- Explicit CRUD Commands ---

@bot.message_handler(commands=["create_company"])
def cmd_create_company(message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2: return bot.reply_to(message, "Использование: /create_company <имя>")
    if create_company(parts[1]): bot.reply_to(message, f"✅ Создана {parts[1]}")
    else: bot.reply_to(message, "❌ Ошибка (уже существует?)")

@bot.message_handler(commands=["delete_company"])
def cmd_delete_company(message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2: return bot.reply_to(message, "Использование: /delete_company <имя>")
    if delete_company(parts[1]): bot.reply_to(message, f"✅ Удалена {parts[1]}")
    else: bot.reply_to(message, "❌ Не найдена")

@bot.message_handler(commands=["list_companies", "companies"])
def cmd_list_companies(message):
    comps = list_companies()
    if not comps: return bot.reply_to(message, "Компаний нет.")
    bot.reply_to(message, "Компании:\n" + "\n".join(comps))

@bot.message_handler(commands=["list_files"])
def cmd_list_files(message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2: return bot.reply_to(message, "Использование: /list_files <компания>")
    files = list_files(parts[1])
    if not files: return bot.reply_to(message, "Файлов нет.")
    bot.reply_to(message, f"Файлы в {parts[1]}:\n" + "\n".join(files))

@bot.message_handler(commands=["delete_file"])
def cmd_delete_file(message):
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3: return bot.reply_to(message, "Использование: /delete_file <компания> <файл>")
    if delete_file(parts[1], parts[2]): bot.reply_to(message, "✅ Файл удален.")
    else: bot.reply_to(message, "❌ Файл не найден.")

@bot.message_handler(commands=["add_file"])
def cmd_add_file(message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return bot.reply_to(message, "Использование: /add_file <компания>")

    company = parts[1].strip()
    if not company:
        return bot.reply_to(message, "Использование: /add_file <компания>")

    pending_file_company[message.chat.id] = company
    bot.reply_to(message, f"Ок. Отправь файл, я сохраню его в «{company}».")

# --- Document Handling ---

@bot.message_handler(content_types=["document", "photo"])
def on_document(message):
    is_photo = message.content_type == "photo"
    doc = message.photo[-1] if is_photo else message.document
    src_ext = "jpg" if is_photo else get_extension(doc.file_name or "")
    file_name = f"photo_{doc.file_id}.jpg" if is_photo else (doc.file_name or f"input.{src_ext or 'bin'}")
    
    caption = (message.caption or "").strip()
    caption_lower = caption.lower()
    
    is_save_request = False
    company_to_save = pending_file_company.pop(message.chat.id, "")
    if company_to_save:
        is_save_request = True

    for prefix in ("store to ", "store ", "сохранить в ", "сохранить ", "в ", "save to ", "save "):
        if caption_lower.startswith(prefix):
            is_save_request = True
            company_to_save = caption[len(prefix):].strip()
            break

    target = caption_lower.lstrip(".")
    if not target and not is_save_request:
        target = "docx" if src_ext == "pdf" else "pdf"

    if doc.file_size and doc.file_size > MAX_DOWNLOAD_MB * 1024 * 1024:
        return bot.reply_to(message, "Файл слишком большой.")

    if is_save_request and company_to_save:
        bot.reply_to(message, f"💾 Сохраняю файл в «{company_to_save}»…")
    else:
        bot.reply_to(message, f"⚙️ Конвертирую {src_ext or '?'} → {target}…")

    src_path = out_path = None
    try:
        file_info = bot.get_file(doc.file_id)
        data = bot.download_file(file_info.file_path)
        in_dir = tempfile.mkdtemp(prefix="in_")
        src_path = os.path.join(in_dir, file_name)
        with open(src_path, "wb") as f:
            f.write(data)

        if is_save_request and company_to_save:
            dest = save_document(company_to_save, src_path, file_name)
            bot.reply_to(message, f"✅ Сохранён:\n`{os.path.basename(dest)}`", parse_mode="Markdown")
            
            # Gemini Metadata
            if GEMINI_API_KEY:
                try:
                    bot.send_message(message.chat.id, "🤖 Анализирую файл (AI Metadata)...")
                    uploaded = genai.upload_file(path=src_path, display_name=file_name)
                    model = genai.GenerativeModel("gemini-flash-latest")
                    resp = model.generate_content([uploaded, "Опиши этот документ 1-2 предложениями."])
                    meta_path = dest + ".meta.txt"
                    with open(meta_path, "w", encoding="utf-8") as fmeta:
                        fmeta.write(resp.text)
                    bot.send_message(message.chat.id, f"📝 **Описание ИИ:**\n{resp.text}", parse_mode="Markdown")
                except Exception as e:
                    bot.send_message(message.chat.id, f"⚠️ Не удалось сгенерировать метаданные: {e}")
            return

        out_path = convert(src_path, target)
        if os.path.getsize(out_path) > MAX_SEND_MB * 1024 * 1024:
            return bot.reply_to(message, "Результат слишком большой.")
        _send_document_with_retry(message.chat.id, out_path)

    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}")
    finally:
        cleanup(src_path, out_path)
        if src_path: cleanup(os.path.dirname(src_path))
        if out_path: cleanup(os.path.dirname(out_path))

# --- AI Text Routing ---

@bot.message_handler(func=lambda m: True, content_types=["text"])
def on_text(message):
    text = message.text.strip()
    low = text.lower()
    
    if low in ("❓ помощь", "помощь", "🏢 список компаний", "список компаний"):
        if "список" in low: cmd_list_companies(message)
        else: cmd_start(message)
        return

    if not GEMINI_API_KEY:
        # Manual fallback when Gemini is not configured.
        if low in ("список компаний", "компании", "list companies"):
            cmd_list_companies(message)
            return

        for prefix in ("создай компанию ", "создать компанию ", "create company "):
            if low.startswith(prefix):
                name = text[len(prefix):].strip()
                if create_company(name):
                    bot.reply_to(message, f"✅ Создана {name}")
                else:
                    bot.reply_to(message, "❌ Ошибка (уже существует?)")
                return

        for prefix in ("удали компанию ", "удалить компанию ", "delete company "):
            if low.startswith(prefix):
                name = text[len(prefix):].strip()
                if delete_company(name):
                    bot.reply_to(message, f"✅ Удалена {name}")
                else:
                    bot.reply_to(message, "❌ Не найдена")
                return

        for prefix in ("файлы ", "документы ", "документы по ", "files ", "documents "):
            if low.startswith(prefix):
                query = text[len(prefix):].strip()
                if _send_company_documents(message.chat.id, query):
                    bot.reply_to(message, f"Нашел документы для «{query}».")
                else:
                    bot.reply_to(message, "Документы не найдены.")
                return

        if low.startswith("документы по"):
            query = text[len("документы по"):].strip()
            if _send_company_documents(message.chat.id, query):
                bot.reply_to(message, "Нашел:")
            else:
                bot.reply_to(message, "Документы не найдены.")
            return

        bot.reply_to(
            message,
            "Gemini API key не задан. Работают команды /create_company, "
            "/list_companies, /list_files, /delete_file и сохранение файла "
            "с подписью `save to <компания>`.",
            parse_mode="Markdown",
        )
        return

    history = user_history[message.chat.id]
    
    comp_list = list_companies()
    companies_str = ", ".join(comp_list) if comp_list else "Пока нет компаний"
    prompt = (
        f"Ты умный AI-помощник. Существующие компании: {companies_str}.\n"
        f"Твоя задача: выбрать нужный инструмент ИЛИ ответить текстом.\n"
        f"Если пользователь ошибся в названии компании, исправь опечатку на существующую.\n"
        f"Если пользователь просит файлы компании, выбери инструмент list_files.\n\n"
        f"Инструменты:\n{json.dumps(TOOLS_DEF, ensure_ascii=False, indent=2)}\n\nИстория:\n"
    )
    for h in history: prompt += f"- {h}\n"
    prompt += f"\nТекущий запрос: {text}\n\nВерни СТРОГО JSON формата: {{\"tool\": \"имя\", \"parameters\": {{\"k\":\"v\"}}}} ИЛИ {{\"reply\": \"ответ\"}}. Без Markdown блоков (без ```json)."

    try:
        bot.send_chat_action(message.chat.id, 'typing')
        model = genai.GenerativeModel("gemini-flash-latest")
        resp = model.generate_content(prompt)
        raw = resp.text.strip()
        if raw.startswith("```json"): raw = raw[7:-3].strip()
        elif raw.startswith("```"): raw = raw[3:-3].strip()
        
        data = json.loads(raw)
        history.append(f"User: {text}")
        
        if "reply" in data:
            reply = data["reply"]
            history.append(f"Bot: {reply}")
            bot.reply_to(message, reply)
            return
            
        tool_name = data.get("tool")
        params = data.get("parameters", {})
        
        tool = next((t for t in TOOLS_DEF if t["name"] == tool_name), None)
        if not tool:
            bot.reply_to(message, f"❌ ИИ выбрал неизвестный инструмент: {tool_name}")
            return
            
        cmd = []
        for c in tool["command"]:
            try: cmd.append(c.format(**params))
            except: cmd.append(c)
            
        res = subprocess.run(cmd, capture_output=True, text=True, cwd="/app")
        
        if res.returncode == 0:
            out_data = json.loads(res.stdout)
            
            if tool_name == "list_files":
                comp = params.get("company_name", "")
                docs = find_documents(comp)
                if docs:
                    reply_text = f"📂 Документы компании '{comp}':"
                    bot.reply_to(message, reply_text)
                    for f in docs:
                        if not f.endswith(".meta.txt"):
                            try: _send_document_with_retry(message.chat.id, f)
                            except Exception as e: print("Fail send", e)
                    history.append(f"Bot: Отправлены файлы компании {comp}")
                    return
                else:
                    reply_text = f"🤷‍♂️ В компании '{comp}' файлы не найдены."
            elif tool_name == "create_company":
                if out_data.get("success"): reply_text = f"✅ Компания '{params.get('company_name')}' успешно создана!"
                else: reply_text = f"❌ Ошибка создания: {out_data.get('error')}"
            elif tool_name == "delete_company":
                if out_data.get("success"): reply_text = f"🗑 Компания '{params.get('company_name')}' удалена."
                else: reply_text = f"❌ Не удалось удалить: {out_data.get('error')}"
            elif tool_name == "delete_file":
                if out_data.get("success"): reply_text = f"🗑 Файл '{params.get('file_name')}' удален."
                else: reply_text = f"❌ Ошибка удаления: {out_data.get('error')}"
            elif tool_name == "list_companies":
                comps = out_data.get("companies", [])
                if comps: reply_text = "🏢 Существующие компании:\n" + "\n".join(f"- {c}" for c in comps)
                else: reply_text = "🤷‍♂️ Компаний пока нет."
            else:
                reply_text = f"✅ Инструмент {tool_name} выполнен успешно."
        else:
            reply_text = f"❌ Системная ошибка."
            
        history.append(f"Bot: {reply_text}")
        bot.reply_to(message, reply_text)
        
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка ИИ: {e}\n{traceback.format_exc()[-200:]}")

def run():
    print("Бот запущен. Ctrl+C — остановить.")
    bot.infinity_polling(skip_pending=True)

if __name__ == "__main__":
    run()
