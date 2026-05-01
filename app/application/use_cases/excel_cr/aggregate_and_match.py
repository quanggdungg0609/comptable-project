from dataclasses import dataclass, field
from typing import Any


@dataclass
class AggregatedRow:
    thang: int
    dien_giai: str
    khoan_muc: str
    so_tien: float
    chi_tieu: str | None = None
    match_tier: str | None = None  # llm_confirmed|keyword|direct|None


def aggregate_rows(rows: list[dict[str, Any]]) -> list[AggregatedRow]:
    """Group by (thang, dien_giai, khoan_muc), sum so_tien."""
    totals: dict[tuple, float] = {}
    for r in rows:
        key = (int(r["thang"]), str(r["dien_giai"]).strip(), str(r["khoan_muc"]).strip().lower())
        totals[key] = totals.get(key, 0.0) + float(r["so_tien"])
    return [
        AggregatedRow(thang=k[0], dien_giai=k[1], khoan_muc=k[2], so_tien=v)
        for k, v in totals.items()
    ]


def match_rules(
    rows: list[AggregatedRow], rules: dict[str, Any]
) -> tuple[list[AggregatedRow], list[AggregatedRow]]:
    """Apply 3-tier rule matching. Returns (matched, unmatched)."""
    confirmed_map = {r["dien_giai"].lower(): r["chi_tieu"] for r in rules.get("llm_confirmed", [])}
    keyword_rules = rules.get("keyword", [])
    direct_map = {r["khoan_muc"].lower(): r["chi_tieu"] for r in rules.get("direct", [])}

    matched, unmatched = [], []
    for row in rows:
        dien_giai_lower = row.dien_giai.lower()

        # Tier 1: exact dien_giai match
        if dien_giai_lower in confirmed_map:
            row.chi_tieu = confirmed_map[dien_giai_lower]
            row.match_tier = "llm_confirmed"
            matched.append(row)
            continue

        # Tier 2: khoan_muc + keyword
        kw_match = None
        for rule in keyword_rules:
            if rule["khoan_muc"].lower() == row.khoan_muc:
                if any(kw.lower() in dien_giai_lower for kw in rule.get("keywords", [])):
                    kw_match = rule["chi_tieu"]
                    break
        if kw_match:
            row.chi_tieu = kw_match
            row.match_tier = "keyword"
            matched.append(row)
            continue

        # Tier 3: direct khoan_muc match
        if row.khoan_muc in direct_map:
            row.chi_tieu = direct_map[row.khoan_muc]
            row.match_tier = "direct"
            matched.append(row)
            continue

        unmatched.append(row)

    return matched, unmatched