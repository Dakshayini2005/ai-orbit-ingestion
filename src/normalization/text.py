from __future__ import annotations


def normalize_category(raw: str) -> str:
    return raw.strip().lower().replace(" ", "-")


def normalize_categories(raw_list: list[str]) -> list[str]:
    seen: list[str] = []
    for item in raw_list:
        if not item:
            continue
        norm = normalize_category(item)
        if norm and norm not in seen:
            seen.append(norm)
    return seen
