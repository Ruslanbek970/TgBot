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
