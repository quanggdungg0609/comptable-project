import pytest
from app.application.use_cases.excel_cr.aggregate_and_match import (
    aggregate_rows,
    match_rules,
    AggregatedRow
)

SAMPLE_ROWS = [
    {"thang": 1, "dien_giai": "Thưởng sáng kiến", "so_tien": 58_900_000.0, "khoan_muc": "cpk"},
    {"thang": 1, "dien_giai": "Trợ cấp TNLĐ",     "so_tien":  9_336_600.0, "khoan_muc": "cpk"},
    {"thang": 1, "dien_giai": "Thưởng sáng kiến", "so_tien": 12_000_000.0, "khoan_muc": "cpk"},
    {"thang": 2, "dien_giai": "Thưởng sáng kiến", "so_tien":  5_000_000.0, "khoan_muc": "cpk"},
]

RULES = {
    "llm_confirmed": [{"dien_giai": "Thưởng sáng kiến", "chi_tieu": "Chi khác"}],
    "keyword": [{"khoan_muc": "cpk", "keywords": ["trợ cấp"], "chi_tieu": "Chi phí lao động"}],
    "direct": [],
}

def test_aggregate_sums_same_thang_dien_giai():
    rows = aggregate_rows(SAMPLE_ROWS)
    t1_thuong = [r for r in rows if r.thang == 1 and r.dien_giai == "Thưởng sáng kiến"]
    assert len(t1_thuong) == 1
    assert t1_thuong[0].so_tien == pytest.approx(70_900_000.0)

def test_aggregate_keeps_separate_thang():
    rows = aggregate_rows(SAMPLE_ROWS)
    months = {r.thang for r in rows}
    assert months == {1, 2}

def test_match_llm_confirmed():
    rows = aggregate_rows(SAMPLE_ROWS)
    matched, unmatched = match_rules(rows, RULES)
    thuong = [r for r in matched if r.dien_giai == "Thưởng sáng kiến"]
    assert all(r.chi_tieu == "Chi khác" for r in thuong)

def test_match_keyword():
    rows = aggregate_rows(SAMPLE_ROWS)
    matched, unmatched = match_rules(rows, RULES)
    trocap = [r for r in matched if "Trợ cấp" in r.dien_giai]
    assert len(trocap) == 1
    assert trocap[0].chi_tieu == "Chi phí lao động"

def test_unmatched_rows_have_no_chi_tieu():
    rules_empty = {"llm_confirmed": [], "keyword": [], "direct": []}
    rows = aggregate_rows(SAMPLE_ROWS)
    _, unmatched = match_rules(rows, rules_empty)
    assert len(unmatched) == len(rows)