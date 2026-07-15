"""
Ядро конвертера (Разработчик 2).

ЕДИНСТВЕННАЯ публичная точка входа для бота — функция convert().
Бот не должен знать, КАК именно конвертируется файл. Он делает:

    from converter import convert
    out_path = convert("/tmp/file.docx", "pdf")

и получает путь к готовому файлу во временной папке.
"""
from __future__ import annotations

import os
import shutil
import tempfile

from . import engines, utils
from .exceptions import EngineNotAvailable, UnsupportedFormatError

# Матрица поддержки: ключ — целевой формат, значение — исходные форматы.
SUPPORTED = {
    "pdf": {
        "docx", "doc", "odt", "rtf", "txt",   # текстовые/офисные
        "xlsx", "xls", "ods", "csv",          # таблицы
        "pptx", "ppt", "odp",                 # презентации
        "png", "jpg", "jpeg", "bmp", "tiff",  # картинки
    },
    "docx": {"pdf"},
}

# Форматы-картинки — для них есть отдельный (более качественный) путь.
_IMAGE_EXTS = {"png", "jpg", "jpeg", "bmp", "tiff"}

# Лимит входного файла. Telegram-бот скачивает файлы через getFile до ~20 МБ.
MAX_INPUT_MB = 20

# Все известные форматы (объединение источников и целей матрицы).
# Нужно для идемпотентной копии, когда вход и выход — один формат.
_KNOWN_FORMATS = set(SUPPORTED) | {ext for exts in SUPPORTED.values() for ext in exts}


def convert(input_path: str, target_format: str) -> str:
    """
    Сконвертировать файл в target_format.

    :param input_path:    путь к исходному файлу
    :param target_format: желаемый формат без точки, например "pdf"
    :return:              путь к готовому файлу (лежит во временной папке —
                          вызывающий обязан удалить его после отправки)
    :raises UnsupportedFormatError: направление не поддержано
    :raises FileTooLargeError:      файл больше лимита
    :raises ConversionFailedError:  движок упал/завис
    :raises EngineNotAvailable:     не установлена нужная библиотека/LibreOffice
    """
    target = target_format.lower().lstrip(".")
    src_ext = utils.get_extension(input_path)

    # --- проверки входа ---
    utils.ensure_exists(input_path)
    utils.ensure_size(input_path, MAX_INPUT_MB)

    # идемпотентность: вход и выход — один и тот же известный формат.
    # Конвертировать нечего, просто отдаём копию (движки не трогаем).
    if src_ext == target and target in _KNOWN_FORMATS:
        return _copy_as_result(input_path, target)

    if target not in SUPPORTED or src_ext not in SUPPORTED[target]:
        raise UnsupportedFormatError(
            f"Не умею конвертировать {src_ext or '?'} -> {target}. "
            f"Доступно: {utils.describe_matrix(SUPPORTED)}"
        )

    out_dir = tempfile.mkdtemp(prefix="conv_")

    # --- маршрутизация по движкам ---

    # 1) PDF -> Word: специализированная библиотека
    if src_ext == "pdf" and target == "docx":
        out_path = os.path.join(out_dir, utils.result_name(input_path, "docx"))
        return engines.pdf_to_docx(input_path, out_path)

    # 2) Картинка -> PDF: img2pdf качественнее; если его нет — падаем на LibreOffice
    if src_ext in _IMAGE_EXTS and target == "pdf":
        out_path = os.path.join(out_dir, utils.result_name(input_path, "pdf"))
        try:
            return engines.image_to_pdf(input_path, out_path)
        except EngineNotAvailable:
            return engines.libreoffice_convert(input_path, "pdf", out_dir)

    # 3) Всё остальное (office -> pdf и т.п.) — через LibreOffice
    return engines.libreoffice_convert(input_path, target, out_dir)


def _copy_as_result(input_path: str, target: str) -> str:
    """Исходный и целевой формат совпали — конвертировать нечего, копируем."""
    out_dir = tempfile.mkdtemp(prefix="conv_")
    out_path = os.path.join(out_dir, utils.result_name(input_path, target))
    shutil.copy2(input_path, out_path)
    return out_path
