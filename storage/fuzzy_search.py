"""
Fuzzy search helpers for company names.

The bot often receives full phrases like "show documents for Teksol Trnas",
not just a clean company name. These helpers compare both the original text
and cleaned word windows against known company names.
"""
from __future__ import annotations

try:
    from rapidfuzz import fuzz, process
except ImportError:
    fuzz = None
    process = None


COMPANY_QUERY_STOPWORDS = {
    "show", "find", "open", "download", "document", "documents", "file", "files",
    "please", "for", "by", "company", "all",
    "покажи", "показать", "найди", "найти", "открой", "открыть", "скачай",
    "скачать", "документ", "документы", "файл", "файлы", "мне", "пожалуйста",
    "по", "для", "про", "все", "всё", "компания", "компании",
}


def _clean_query_parts(query: str) -> list[str]:
    cleaned = "".join(ch.casefold() if ch.isalnum() else " " for ch in query or "")
    return [
        part
        for part in cleaned.split()
        if len(part) > 1 and part not in COMPANY_QUERY_STOPWORDS
    ]


def _candidate_queries(query: str) -> list[str]:
    parts = _clean_query_parts(query)
    candidates: list[str] = []

    raw = (query or "").strip()
    if raw:
        candidates.append(raw)
    if parts:
        candidates.append(" ".join(parts))

    max_window = min(5, len(parts))
    for size in range(max_window, 0, -1):
        for start in range(0, len(parts) - size + 1):
            candidates.append(" ".join(parts[start:start + size]))

    seen: set[str] = set()
    unique: list[str] = []
    for candidate in candidates:
        key = candidate.casefold().strip()
        if key and key not in seen:
            seen.add(key)
            unique.append(candidate)
    return unique


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


def _score_company(candidate: str, company: str) -> int:
    if fuzz is not None:
        return int(max(
            fuzz.WRatio(candidate, company, processor=str.casefold),
            fuzz.token_set_ratio(candidate, company, processor=str.casefold),
            fuzz.partial_ratio(candidate, company, processor=str.casefold),
        ))
    return _similarity(candidate, company)


def find_best_company_match(query: str, companies: list[str], threshold: int = 70) -> str | None:
    if not query or not companies:
        return None

    best_match = None
    best_score = 0
    for candidate in _candidate_queries(query):
        for company in companies:
            score = _score_company(candidate, company)
            if score > best_score:
                best_match, best_score = company, score

    if best_match and best_score >= threshold:
        return best_match
    return None


def find_all_company_matches(
    query: str,
    companies: list[str],
    threshold: int = 70,
    limit: int = 5,
) -> list[tuple[str, int]]:
    if not query or not companies:
        return []

    scores: dict[str, int] = {}
    for candidate in _candidate_queries(query):
        for company in companies:
            scores[company] = max(scores.get(company, 0), _score_company(candidate, company))

    matches = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    return [(company, score) for company, score in matches[:limit] if score >= threshold]
