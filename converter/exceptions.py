"""
Исключения конвертера.

Бот ловит ConverterError (базовый класс) и отвечает пользователю понятным
текстом, вместо того чтобы падать с трейсбеком.
"""


class ConverterError(Exception):
    """Базовая ошибка конвертера. Всё остальное наследуется от неё."""


class UnsupportedFormatError(ConverterError):
    """Такое направление конвертации не поддерживается."""


class ConversionFailedError(ConverterError):
    """Движок конвертации упал, завис или вернул ошибку."""


class EngineNotAvailable(ConversionFailedError):
    """Нужный движок/библиотека не установлены (например, нет pdf2docx)."""


class FileTooLargeError(ConverterError):
    """Файл больше допустимого размера."""
