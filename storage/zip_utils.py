"""
Утилиты для работы с ZIP-архивами и массовой загрузки документов.
"""
from __future__ import annotations

import os
import zipfile
import tempfile
from pathlib import Path


# Поддерживаемые форматы документов
SUPPORTED_FORMATS = {
    ".pdf", ".docx", ".doc", ".txt", ".xlsx", ".xls",
    ".pptx", ".ppt", ".jpg", ".jpeg", ".png", ".bmp", ".gif"
}


def is_supported_file(filename: str) -> bool:
    """Проверить, поддерживается ли формат файла."""
    _, ext = os.path.splitext(filename.lower())
    return ext in SUPPORTED_FORMATS


def extract_zip(zip_path: str, extract_to: str | None = None) -> dict[str, str]:
    """
    Распаковать ZIP-архив и вернуть информацию о файлах.
    
    :param zip_path: путь к ZIP-файлу
    :param extract_to: директория для распаковки (если None, используется временная)
    :return: словарь {original_name: full_path} для поддерживаемых файлов
    """
    if not extract_to:
        extract_to = tempfile.mkdtemp(prefix="zip_extract_")
    
    os.makedirs(extract_to, exist_ok=True)
    extracted_files = {}
    
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            for file_info in zf.infolist():
                # Пропускаем директории и служебные файлы
                if file_info.is_dir() or file_info.filename.startswith('__MACOSX') or file_info.filename.endswith('.DS_Store'):
                    continue
                
                # Проверяем, поддерживается ли формат
                if not is_supported_file(file_info.filename):
                    continue
                
                # Извлекаем файл
                extracted_path = zf.extract(file_info, extract_to)
                original_name = os.path.basename(file_info.filename)
                extracted_files[original_name] = extracted_path
    
    except zipfile.BadZipFile:
        raise ValueError("Некорректный ZIP-архив")
    except Exception as e:
        raise RuntimeError(f"Ошибка при распаковке архива: {e}")
    
    return extracted_files


def validate_zip(zip_path: str) -> tuple[bool, str]:
    """
    Проверить корректность ZIP-архива и наличие поддерживаемых файлов.
    
    :param zip_path: путь к ZIP-файлу
    :return: кортеж (is_valid, message)
    """
    if not os.path.isfile(zip_path):
        return False, "Файл не найден"
    
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            # Проверяем целостность
            if zf.testzip() is not None:
                return False, "ZIP-архив повреждён"
            
            # Проверяем наличие файлов
            supported_files = []
            for file_info in zf.infolist():
                if not file_info.is_dir() and is_supported_file(file_info.filename):
                    supported_files.append(file_info.filename)
            
            if not supported_files:
                return False, "В архиве нет поддерживаемых форматов файлов"
            
            return True, f"Найдено {len(supported_files)} файлов для загрузки"
    
    except zipfile.BadZipFile:
        return False, "Это не ZIP-архив"
    except Exception as e:
        return False, f"Ошибка при проверке архива: {e}"
