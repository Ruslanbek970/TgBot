"""
Вспомогательные функции конвертера: расширения, проверки, имена, очистка.
Ничего «тяжёлого» — только чистая логика без внешних движков.
"""
from __future__ import annotations

import os
import shutil

from .exceptions import ConverterError, FileTooLargeError


def get_extension(path: str) -> str:
    """Расширение файла в нижнем регистре без точки. '/a/B.PDF' -> 'pdf'."""
    return os.path.splitext(path)[1].lower().lstrip(".")


def ensure_exists(path: str) -> None:
    """Проверить, что файл существует и не пустой."""
    if not os.path.isfile(path):
        raise ConverterError(f"Файл не найден: {path}")
    if os.path.getsize(path) == 0:
        raise ConverterError("Файл пустой.")


def ensure_size(path: str, max_mb: int) -> None:
    """Проверить лимит размера входного файла."""
    size_mb = os.path.getsize(path) / (1024 * 1024)
    if size_mb > max_mb:
        raise FileTooLargeError(
            f"Файл {size_mb:.1f} МБ больше лимита {max_mb} МБ."
        )


def result_name(input_path: str, target_format: str) -> str:
    """Имя результата: то же имя, новое расширение. 'doc.docx' + 'pdf' -> 'doc.pdf'."""
    base = os.path.splitext(os.path.basename(input_path))[0]
    return f"{base}.{target_format}"


def describe_matrix(matrix: dict) -> str:
    """Человекочитаемое описание поддерживаемых направлений (для сообщений об ошибке)."""
    parts = []
    for target, sources in matrix.items():
        parts.append(f"{'/'.join(sorted(sources))} -> {target}")
    return "; ".join(parts)


def cleanup(*paths: str) -> None:
    """
    Удалить временные файлы/папки.

    Важно для конфиденциальности (не оставляем чужие документы на диске)
    и чтобы не забить диск. Ошибки удаления глотаем — это не критично.
    """
    for p in paths:
        if not p:
            continue
        try:
            if os.path.isdir(p):
                shutil.rmtree(p, ignore_errors=True)
            elif os.path.isfile(p):
                os.remove(p)
        except OSError:
            pass
