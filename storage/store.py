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


# Secure storage implementation. Definitions below intentionally override the
# initial filesystem stub while keeping the same public function names.
import json
import shutil
import uuid
from pathlib import Path

DOCUMENTS_DIR = Path(BASE_DIR)
SECURE_DIR = Path(__file__).resolve().parent / "secure_files"
INDEX_PATH = Path(__file__).resolve().parent / "index.json"
README_NAME = "readme.md"


def _clean_name(value: str) -> str:
    value = (value or "").strip()
    value = value.replace("\\", "_").replace("/", "_")
    value = value.replace("\x00", "")
    return value


def _norm(value: str) -> str:
    return (value or "").casefold().strip()


def _load_index() -> dict:
    if not INDEX_PATH.exists():
        return {"companies": {}, "documents": []}
    try:
        with INDEX_PATH.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {"companies": {}, "documents": []}

    if not isinstance(data, dict):
        return {"companies": {}, "documents": []}
    data.setdefault("companies", {})
    data.setdefault("documents", [])
    return data


def _save_index(data: dict) -> None:
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = INDEX_PATH.with_suffix(".json.tmp")
    with tmp_path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2, sort_keys=True)
    tmp_path.replace(INDEX_PATH)


def _secure_path(file_id: str) -> Path:
    return SECURE_DIR / file_id[:2] / file_id[2:4] / file_id


def _delete_secure_path(path: str) -> None:
    if not path or not os.path.isfile(path):
        return
    file_path = Path(path)
    file_path.unlink()
    for parent in (file_path.parent, file_path.parent.parent):
        if parent == SECURE_DIR or not parent.exists():
            continue
        try:
            parent.rmdir()
        except OSError:
            break


def _legacy_company_dirs() -> list[str]:
    if not DOCUMENTS_DIR.is_dir():
        return []
    return sorted(
        path.name
        for path in DOCUMENTS_DIR.iterdir()
        if path.is_dir() and path.name != "__pycache__"
    )


def _legacy_files(company: str | None = None) -> list[tuple[str, str, Path]]:
    if not DOCUMENTS_DIR.is_dir():
        return []

    companies = [company] if company else _legacy_company_dirs()
    items: list[tuple[str, str, Path]] = []
    for company_name in companies:
        if not company_name:
            continue
        root = DOCUMENTS_DIR / company_name
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.name.casefold() == README_NAME:
                continue
            items.append((company_name, path.name, path))
    return items


def _company_key(name: str) -> str:
    return _norm(name)


def create_company(name: str) -> bool:
    name = _clean_name(name)
    if not name:
        return False

    data = _load_index()
    key = _company_key(name)
    existed = key in data["companies"] or (DOCUMENTS_DIR / name).is_dir()
    data["companies"].setdefault(key, {"name": name})
    _save_index(data)
    (DOCUMENTS_DIR / name).mkdir(parents=True, exist_ok=True)
    return not existed


def list_companies() -> list[str]:
    data = _load_index()
    names = {entry.get("name", "") for entry in data["companies"].values()}
    names.update(_legacy_company_dirs())
    return sorted(name for name in names if name)


def save_document(company: str, temp_file_path: str, file_name: str) -> str:
    company = _clean_name(company)
    file_name = _clean_name(file_name)
    if not company:
        raise ValueError("company is required")
    if not file_name:
        raise ValueError("file_name is required")

    source = Path(temp_file_path)
    if not source.is_file():
        raise FileNotFoundError(temp_file_path)

    data = _load_index()
    data["companies"].setdefault(_company_key(company), {"name": company})

    file_id = uuid.uuid4().hex
    target = _secure_path(file_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)

    data["documents"].append(
        {
            "id": file_id,
            "company": company,
            "original_name": file_name,
            "secure_path": str(target),
            "size": target.stat().st_size,
        }
    )
    _save_index(data)
    return str(target)


def find_documents(query: str) -> list[str]:
    query_norm = _norm(query)
    if not query_norm:
        return []

    data = _load_index()
    results: list[str] = []
    seen: set[str] = set()

    for doc in data.get("documents", []):
        company = doc.get("company", "")
        name = doc.get("original_name", "")
        path = doc.get("secure_path", "")
        haystack = f"{company} {name}".casefold()
        if query_norm in haystack and path and os.path.isfile(path):
            results.append(path)
            seen.add(os.path.abspath(path))

    for company, filename, path in _legacy_files():
        haystack = f"{company} {filename}".casefold()
        path_str = str(path)
        if query_norm in haystack and os.path.abspath(path_str) not in seen:
            results.append(path_str)

    return results


def list_files(company: str) -> list[str]:
    company_norm = _norm(company)
    if not company_norm:
        return []

    data = _load_index()
    files = {
        doc.get("original_name", "")
        for doc in data.get("documents", [])
        if _norm(doc.get("company", "")) == company_norm
        and doc.get("secure_path")
        and os.path.isfile(doc["secure_path"])
    }
    files.update(name for _company, name, _path in _legacy_files(company))
    return sorted(name for name in files if name)


def delete_file(company: str, filename: str) -> bool:
    company_norm = _norm(company)
    filename_norm = _norm(filename)
    if not company_norm or not filename_norm:
        return False

    data = _load_index()
    kept_docs = []
    deleted = False

    for doc in data.get("documents", []):
        if (
            _norm(doc.get("company", "")) == company_norm
            and _norm(doc.get("original_name", "")) == filename_norm
        ):
            path = doc.get("secure_path", "")
            _delete_secure_path(path)
            deleted = True
            continue
        kept_docs.append(doc)

    if deleted:
        data["documents"] = kept_docs
        _save_index(data)

    for legacy_company, legacy_name, path in _legacy_files(company):
        if _norm(legacy_company) == company_norm and _norm(legacy_name) == filename_norm:
            path.unlink()
            deleted = True

    return deleted


def delete_company(name: str) -> bool:
    name_norm = _norm(name)
    if not name_norm:
        return False

    data = _load_index()
    existed = data["companies"].pop(name_norm, None) is not None
    kept_docs = []

    for doc in data.get("documents", []):
        if _norm(doc.get("company", "")) == name_norm:
            path = doc.get("secure_path", "")
            _delete_secure_path(path)
            existed = True
            continue
        kept_docs.append(doc)

    data["documents"] = kept_docs
    _save_index(data)

    for company_name in _legacy_company_dirs():
        if _norm(company_name) == name_norm:
            shutil.rmtree(DOCUMENTS_DIR / company_name)
            existed = True

    return existed
