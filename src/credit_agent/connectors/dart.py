"""금융감독원 OpenDART. https://opendart.fss.or.kr  (무료 인증키 필요: DART_API_KEY)"""
import io
import re
import zipfile

from .. import config
from .http import get_bytes, get_json

BASE = "https://opendart.fss.or.kr/api/"
ACCOUNTS = {  # DART 계정명 → 내부 필드
    "매출액": "revenue", "수익(매출액)": "revenue", "영업이익": "operating_income", "영업이익(손실)": "operating_income",
    "당기순이익": "net_income", "당기순이익(손실)": "net_income", "자산총계": "total_assets",
    "부채총계": "total_liabilities", "자본총계": "total_equity",
}


def _require_key():
    if not config.DART_API_KEY:
        raise PermissionError("DART_API_KEY 미설정")


def corp_code(stock_code):
    _require_key()
    raw = get_bytes(BASE + "corpCode.xml?crtfc_key=" + config.DART_API_KEY)
    if not raw.startswith(b"PK"):  # 오류 시 zip 대신 XML이 온다
        m = re.search(r"<status>(\d+)</status>\s*<message>([^<]+)</message>", raw.decode("utf-8", "ignore"))
        raise RuntimeError("DART {}: {}".format(*m.groups()) if m else "DART corpCode 응답 오류")
    z = zipfile.ZipFile(io.BytesIO(raw))
    xml = z.read(z.namelist()[0]).decode("utf-8")
    m = re.search(r"<corp_code>(\d+)</corp_code>\s*<corp_name>([^<]+)</corp_name>\s*(?:<corp_eng_name>[^<]*</corp_eng_name>\s*)?<stock_code>"
                  + stock_code + "</stock_code>", xml)
    if not m:
        raise LookupError("corp_code not found for " + stock_code)
    return m.group(1)


def _check(d):
    if d.get("status") != "000":
        raise RuntimeError("DART {}: {}".format(d.get("status"), d.get("message")))
    return d


def company(stock_code):
    cc = corp_code(stock_code)
    d = _check(get_json(BASE + "company.json?crtfc_key={}&corp_code={}".format(config.DART_API_KEY, cc)))
    return {k: d.get(k) for k in ("corp_name", "ceo_nm", "induty_code", "est_dt", "adres", "corp_code")}


def financials(stock_code, years):
    cc = corp_code(stock_code)
    out = {}
    for y in years:
        d = _check(get_json(BASE + "fnlttSinglAcntAll.json?crtfc_key={}&corp_code={}&bsns_year={}&reprt_code=11011&fs_div=CFS"
                            .format(config.DART_API_KEY, cc, y)))
        row = {}
        for a in d.get("list", []):
            f = ACCOUNTS.get(a.get("account_nm", "").strip())
            if f and f not in row and a.get("thstrm_amount"):
                row[f] = round(int(a["thstrm_amount"].replace(",", "")) / 1e8)
        out[str(y)] = row
    return out


def disclosures(stock_code, bgn_de, end_de):
    cc = corp_code(stock_code)
    d = _check(get_json(BASE + "list.json?crtfc_key={}&corp_code={}&bgn_de={}&end_de={}&page_count=20"
                        .format(config.DART_API_KEY, cc, bgn_de, end_de)))
    return [{"date": x["rcept_dt"], "title": x["report_nm"]} for x in d.get("list", [])]
