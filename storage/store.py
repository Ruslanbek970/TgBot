"""
Хранилище документов — МИНИМАЛЬНАЯ ЗАГЛУШКА (зона Разработчика 1).

Идея концепции бота: "нужны документы по ТОО «Тексол Транс»" -> бот возвращает
протокол, сертификаты и т.д. этой компании.

Здесь это сделано в лоб: документы лежат по папкам-компаниям в
storage/documents/. find_documents("Тексол Транс") возвращает пути к её докам.

Разработчик 1 дальше заменяет файловое хранилище на нормальное (БД/индекс,
шифрование, права доступа) — но по возможности СОХРАНЯЕТ сигнатуру
find_documents(query) -> list[str], чтобы бот не переписывать.
"""
from __future__ import annotations

import os

# Папка с документами. Рядом с этим файлом: storage/documents/<Компания>/<файлы>
BASE_DIR = os.path.join(os.path.dirname(__file__), "documents")


def find_documents(query: str) -> list[str]:
    """
    Найти документы по названию компании / запросу.

    Простой регистронезависимый поиск: совпадение подстроки в имени папки
    (компании) ИЛИ в имени файла.

    :param query: например "Тексол Транс" или "Тексол"
    :return: список путей к найденным файлам (может быть пустым)
    """
    query = (query or "").strip().lower()
    if not query:
        return []

    results: list[str] = []
    if not os.path.isdir(BASE_DIR):
        return results

    for root, _dirs, files in os.walk(BASE_DIR):
        folder_match = query in os.path.basename(root).lower()
        for name in files:
            if name.lower() == "readme.md":
                continue  # служебный файл, не выдаём
            if folder_match or query in name.lower():
                results.append(os.path.join(root, name))
    return results


def list_companies() -> list[str]:
    """Список компаний (папок верхнего уровня) — для подсказок в боте."""
    if not os.path.isdir(BASE_DIR):
        return []
    return sorted(
        name for name in os.listdir(BASE_DIR)
        if os.path.isdir(os.path.join(BASE_DIR, name))
    )

def create_company(name: str) -> bool:
    """Создать новую компанию (папку)."""
    name = name.strip()
    if not name:
        return False
    path = os.path.join(BASE_DIR, name)
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)
        return True
    return False

def save_document(company: str, temp_file_path: str, file_name: str) -> str:
    """Сохранить документ в папку компании."""
    import shutil
    company = company.strip()
    path = os.path.join(BASE_DIR, company)
    os.makedirs(path, exist_ok=True)
    
    dest_path = os.path.join(path, file_name)
    shutil.copy2(temp_file_path, dest_path)
    return dest_path

def delete_company(name: str) -> bool:
    import shutil
    name = name.strip()
    if not name:
        return False
    path = os.path.join(BASE_DIR, name)
    if os.path.isdir(path):
        shutil.rmtree(path)
        return True
    return False

def list_files(company: str) -> list[str]:
    company = company.strip()
    path = os.path.join(BASE_DIR, company)
    if not os.path.isdir(path):
        return []
    return sorted(f for f in os.listdir(path) if os.path.isfile(os.path.join(path, f)))

def delete_file(company: str, filename: str) -> bool:
    company = company.strip()
    filename = filename.strip()
    path = os.path.join(BASE_DIR, company, filename)
    if os.path.isfile(path):
        os.remove(path)
        return True
    return False
