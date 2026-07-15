"""
Модуль конвертера файлов (Разработчик 2).

Публичный API — одна функция convert():

    from converter import convert
    out_path = convert("/path/file.docx", "pdf")

Всё остальное (движки, утилиты) — внутренняя кухня, бот туда не лезет.
"""
from .core import MAX_INPUT_MB, SUPPORTED, convert
from .exceptions import (
    ConversionFailedError,
    ConverterError,
    EngineNotAvailable,
    FileTooLargeError,
    UnsupportedFormatError,
)

__all__ = [
    "convert",
    "SUPPORTED",
    "MAX_INPUT_MB",
    "ConverterError",
    "UnsupportedFormatError",
    "ConversionFailedError",
    "EngineNotAvailable",
    "FileTooLargeError",
]
