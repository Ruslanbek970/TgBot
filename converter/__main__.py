"""
CLI для быстрого теста конвертера БЕЗ бота и без токена.

    python -m converter <файл> <целевой_формат>

Примеры:
    python -m converter report.docx pdf
    python -m converter scan.pdf docx

Удобно гонять в Docker, чтобы проверить, что LibreOffice на месте:
    docker compose run --rm bot python -m converter <файл> pdf
"""
import sys

from . import ConverterError, convert


def main() -> None:
    if len(sys.argv) != 3:
        print("Использование: python -m converter <файл> <формат>")
        print("Пример:        python -m converter report.docx pdf")
        sys.exit(2)

    src, target = sys.argv[1], sys.argv[2]
    try:
        out_path = convert(src, target)
    except ConverterError as exc:
        print(f"Ошибка: {exc}")
        sys.exit(1)

    print(f"Готово: {out_path}")


if __name__ == "__main__":
    main()
