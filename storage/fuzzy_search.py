"""
Нечеткий поиск по названиям компаний с помощью RapidFuzz.

Позволяет находить компании даже при опечатках и неточном вводе названия.
"""
from __future__ import annotations

try:
    from rapidfuzz import process, fuzz
except ImportError:
    process = None
    fuzz = None


def _similarity(left: str, right: str) -> int:
    left = left.casefold().strip()
    right = right.casefold().strip()
    if not left or not right:
        return 0
    if left == right:
        return 100

    previous = list(range(len(right) + 1))
    for i, left_char in enumerate(left, start=1):
        current = [i]
        for j, right_char in enumerate(right, start=1):
            insert_cost = current[j - 1] + 1
            delete_cost = previous[j] + 1
            replace_cost = previous[j - 1] + (left_char != right_char)
            current.append(min(insert_cost, delete_cost, replace_cost))
        previous = current

    distance = previous[-1]
    max_len = max(len(left), len(right))
    return int((1 - distance / max_len) * 100)


def find_best_company_match(query: str, companies: list[str], threshold: int = 70) -> str | None:
    """
    Найти наиболее подходящую компанию по нечеткому поиску.
    
    :param query: запрос пользователя (например, "Тексол Транс")
    :param companies: список доступных компаний
    :param threshold: минимальный процент совпадения (0-100)
    :return: название компании или None, если совпадение не найдено
    """
    if not query or not companies:
        return None
    
    query = query.strip()
    # Используем ratio для полного сравнения строк
    if process is not None and fuzz is not None:
        best_match, score, _ = process.extractOne(
            query,
            companies,
            scorer=fuzz.WRatio,
            processor=str.casefold
        )
    else:
        best_match = max(companies, key=lambda company: _similarity(query, company))
        score = _similarity(query, best_match)
    
    if score >= threshold:
        return best_match
    return None


def find_all_company_matches(
    query: str,
    companies: list[str],
    threshold: int = 70,
    limit: int = 5
) -> list[tuple[str, int]]:
    """
    Найти несколько подходящих компаний по нечеткому поиску.
    
    :param query: запрос пользователя
    :param companies: список доступных компаний
    :param threshold: минимальный процент совпадения (0-100)
    :param limit: максимальное количество результатов
    :return: список кортежей (компания, процент_совпадения)
    """
    if not query or not companies:
        return []
    
    query = query.strip()
    if process is not None and fuzz is not None:
        matches = process.extract(
            query,
            companies,
            scorer=fuzz.WRatio,
            processor=str.casefold,
            limit=limit
        )
        return [(company, score) for company, score in matches if score >= threshold]

    matches = sorted(
        ((company, _similarity(query, company)) for company in companies),
        key=lambda item: item[1],
        reverse=True,
    )
    return [(company, score) for company, score in matches[:limit] if score >= threshold]
