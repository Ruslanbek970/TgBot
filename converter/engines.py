"""
Обёртки над конкретными движками конвертации.

Здесь вся «грязь»: запуск LibreOffice, вызовы pdf2docx и img2pdf.
core.py вызывает эти функции и не знает деталей реализации.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import threading
import uuid

from .exceptions import ConversionFailedError, EngineNotAvailable

# ---------------------------------------------------------------------------
# LibreOffice
# ---------------------------------------------------------------------------
# Готча №1: два процесса soffice с одним профилем падают
#   ("another instance is running"). Решаем двумя приёмами:
#     1) на каждый вызов — свой профиль (-env:UserInstallation);
#     2) сериализуем вызовы локом (перестраховка).
# Если позже нужна настоящая параллельность — убрать лок, профили уже уникальны.
_LO_LOCK = threading.Lock()

# Готча №2: битый файл может подвесить soffice навсегда -> жёсткий таймаут.
_TIMEOUT_SEC = 120


def _find_soffice() -> str:
    """Найти бинарь LibreOffice кроссплатформенно."""
    # 1) явно заданный путь (переменная окружения SOFFICE_PATH)
    env_path = os.environ.get("SOFFICE_PATH")
    if env_path and os.path.exists(env_path):
        return env_path
    # 2) в PATH
    for name in ("soffice", "libreoffice"):
        found = shutil.which(name)
        if found:
            return found
    # 3) типичные места установки
    for path in (
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
        "/usr/bin/soffice",
        "/usr/bin/libreoffice",
        "/snap/bin/libreoffice",
    ):
        if os.path.exists(path):
            return path
    raise EngineNotAvailable(
        "LibreOffice не найден. Установите его (см. README) "
        "или задайте путь в переменной окружения SOFFICE_PATH."
    )


def _to_file_uri(path: str) -> str:
    """Путь -> file:/// URI (нужно LibreOffice для UserInstallation)."""
    return "file:///" + path.replace("\\", "/").lstrip("/")


def libreoffice_convert(input_path: str, target_format: str, out_dir: str) -> str:
    """
    Конвертация через LibreOffice headless.
    Тянет: docx/doc/odt/rtf/txt/xlsx/xls/pptx/ppt/картинки -> pdf и др.
    """
    soffice = _find_soffice()

    # отдельный профиль на вызов -> безопасно при параллельных запросах
    profile = os.path.join(tempfile.gettempdir(), f"lo_profile_{uuid.uuid4().hex}")

    cmd = [
        soffice,
        "--headless", "--norestore", "--nologo", "--nofirststartwizard",
        f"-env:UserInstallation={_to_file_uri(profile)}",
        "--convert-to", target_format,
        "--outdir", out_dir,
        input_path,
    ]

    with _LO_LOCK:
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=_TIMEOUT_SEC)
        except subprocess.TimeoutExpired:
            raise ConversionFailedError(
                f"Конвертация превысила {_TIMEOUT_SEC} c (возможно, битый файл)."
            )
        finally:
            shutil.rmtree(profile, ignore_errors=True)

    # LibreOffice сохраняет результат с исходным именем, но новым расширением
    base = os.path.splitext(os.path.basename(input_path))[0]
    out_path = os.path.join(out_dir, f"{base}.{target_format}")

    if proc.returncode != 0 or not os.path.exists(out_path):
        stderr = proc.stderr.decode(errors="ignore")[:300]
        raise ConversionFailedError(
            f"LibreOffice не смог сконвертировать файл. Детали: {stderr or 'нет'}"
        )
    return out_path


# ---------------------------------------------------------------------------
# PDF -> Word (pdf2docx)
# ---------------------------------------------------------------------------
def pdf_to_docx(input_path: str, out_path: str) -> str:
    """PDF -> .docx через библиотеку pdf2docx (разбирает текст и таблицы)."""
    try:
        from pdf2docx import Converter
    except ImportError:
        raise EngineNotAvailable("Не установлен pdf2docx. Установите: pip install pdf2docx")

    try:
        cv = Converter(input_path)
        cv.convert(out_path)
        cv.close()
    except Exception as exc:  # noqa: BLE001 — pdf2docx кидает разные типы
        raise ConversionFailedError(f"pdf2docx не справился: {exc}")
    return out_path


# ---------------------------------------------------------------------------
# Картинка -> PDF (img2pdf, без потери качества)
# ---------------------------------------------------------------------------
def image_to_pdf(input_path: str, out_path: str) -> str:
    """Картинка -> PDF через img2pdf (не пережимает изображение)."""
    try:
        import img2pdf
    except ImportError:
        raise EngineNotAvailable("Не установлен img2pdf. Установите: pip install img2pdf")

    try:
        with open(out_path, "wb") as f:
            f.write(img2pdf.convert(input_path))
    except Exception as exc:  # noqa: BLE001
        raise ConversionFailedError(f"img2pdf не справился: {exc}")
    return out_path
