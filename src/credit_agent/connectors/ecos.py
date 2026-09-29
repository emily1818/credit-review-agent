"""한국은행 ECOS 통계 API. https://ecos.bok.or.kr/api/"""
from datetime import date, timedelta

from .. import config
from .http import get_json

SERIES = {
    "base_rate": ("722Y001", "M", "0101000", "한국은행 기준금리"),
    "cd91": ("817Y002", "D", "010502000", "CD(91일)"),
    "ktb3y": ("817Y002", "D", "010200000", "국고채(3년)"),
    "corp_loan_large": ("121Y006", "M", "BECBLA0201", "예금은행 대기업대출 금리(신규)"),
}


def _range(cycle, today):
    if cycle == "D":
        return (today - timedelta(days=12)).strftime("%Y%m%d"), today.strftime("%Y%m%d")
    m = today.month - 8
    start = date(today.year + (m - 1) // 12, (m - 1) % 12 + 1, 1)
    return start.strftime("%Y%m"), today.strftime("%Y%m")


def latest(series_key, today=None):
    code, cycle, item, name = SERIES[series_key]
    s, e = _range(cycle, today or date.today())
    n = 10 if config.ECOS_API_KEY == "sample" else 100  # sample 키는 최대 10건
    url = "https://ecos.bok.or.kr/api/StatisticSearch/{}/json/kr/1/{}/{}/{}/{}/{}/{}".format(
        config.ECOS_API_KEY, n, code, cycle, s, e, item)
    d = get_json(url)
    rows = d.get("StatisticSearch", {}).get("row") or []
    if not rows:
        raise RuntimeError("ECOS 응답에 데이터 없음: {}".format(d.get("RESULT", d)))
    last = rows[-1]
    return {"key": series_key, "name": name, "value": float(last["DATA_VALUE"]), "time": last["TIME"],
            "unit": last.get("UNIT_NAME", "연%"), "stat_code": code, "item_code": item}
