"""
Базовые тесты конвертера (не требуют LibreOffice).

Запуск:
    pip install pytest
    pytest -q
"""
import pytest

from converter import SUPPORTED, ConverterError, UnsupportedFormatError, convert


def test_matrix_has_pdf_and_docx():
    assert "pdf" in SUPPORTED
    assert "docx" in SUPPORTED


def test_unsupported_direction_raises(tmp_path):
    f = tmp_path / "file.xyz"
    f.write_text("hello")
    with pytest.raises(UnsupportedFormatError):
        convert(str(f), "pdf")


def test_missing_file_raises(tmp_path):
    with pytest.raises(ConverterError):
        convert(str(tmp_path / "nope.docx"), "pdf")


def test_empty_file_raises(tmp_path):
    f = tmp_path / "empty.docx"
    f.write_bytes(b"")
    with pytest.raises(ConverterError):
        convert(str(f), "pdf")


def test_same_format_just_copies(tmp_path):
    # pdf -> pdf: конвертировать нечего, должен вернуть копию (движки не нужны)
    src = tmp_path / "a.pdf"
    src.write_bytes(b"%PDF-1.4 fake")
    out = convert(str(src), "pdf")
    assert out.endswith(".pdf")
