"""
Модуль хранилища документов (Разработчик 1, пока заглушка).

Публичный API:
    from storage import find_documents, list_companies
"""
from .store import find_documents, list_companies, save_document, create_company, delete_company, list_files, delete_file

__all__ = ["find_documents", "list_companies", "save_document", "create_company", "delete_company", "list_files", "delete_file"]
