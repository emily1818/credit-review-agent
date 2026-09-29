"""데모 사례 6건의 가상 업로드 서류와 은행 내부 DB를 만든다.

  python3 data/cases/generate.py

사례별 폴더(C1~C6)에 차주가 제출하는 서류 5종이 생긴다. 업로드 화면에서 이 파일들을 직접 넣으면 된다.
모든 수치는 시연용 가상 데이터이며 실제 기업의 재무·신용상태와 무관하다.
"""
import json
from pathlib import Path

HERE = Path(__file__).parent
BANK = HERE.parent / "bank"

CASES = [
    dict(id="C1", borrower="HDC랩스", code="039570", industry="부동산 관리·스마트홈 솔루션",
         project="HDC랩스 스마트빌딩 R&D센터 신축", site="경기도 성남시 분당구 ○○동", scale="지하 4층 / 지상 12층, 연면적 18,520㎡",
         use="업무시설(사옥 60%, 임대 40%)", months=26,
         contractor="GS건설", ccode="006360", architect="○○종합건축사사무소",
         loan=480, tenor=5, grace=2, amort=10, spread=1.80,
         costs={"토지비": 230, "공사비": 475, "설계·감리비": 28, "기타 부대비용": 47, "금융비용": 40},
         extra={"임대수입(억원/년)": 18, "비용절감(억원/년)": 22},
         contract=468, adj_clause=True, guarantee="스캔본(인감증명서 미첨부)", liability="대출원금 전액",
         appraisal=dict(land=265, completed=1050),
         fin={"2023": [6850, 210, 148, 5420, 3190, 2230, 890, 46, 70, 295, 820, 88],
              "2024": [7120, 245, 171, 5610, 3180, 2430, 960, 57, 72, 318, 760, 92],
              "2025": [7410, 268, 190, 5850, 3240, 2610, 1050, 65, 74, 341, 710, 95]},
         grade=("BBB+", 71, 0.92), since=2014, loans=240, deposits=210),
    dict(id="C2", borrower="CJ대한통운", code="000120", industry="종합물류",
         project="CJ대한통운 이천 스마트 물류센터 신축", site="경기도 이천시 마장면 ○○리", scale="지하 1층 / 지상 5층, 연면적 42,300㎡",
         use="창고시설(자가사용 100%)", months=20,
         contractor="DL이앤씨", ccode="375500", architect="△△건축사사무소",
         loan=280, tenor=7, grace=2, amort=12, spread=1.50,
         costs={"토지비": 150, "공사비": 290, "설계·감리비": 15, "기타 부대비용": 20, "금융비용": 25},
         extra={"임대수입(억원/년)": 0, "비용절감(억원/년)": 45},
         contract=290, adj_clause=False, guarantee="원본(인감증명서 첨부)", liability="대출원금 전액",
         appraisal=dict(land=170, completed=650),
         fin={"2023": [117000, 4800, 1900, 90000, 55000, 35000, 25000, 1100, 4200, 7500, 5200, 6500],
              "2024": [118500, 4950, 2000, 92000, 55500, 36500, 25500, 1150, 4300, 7700, 5400, 6500],
              "2025": [121000, 5100, 2100, 94000, 56000, 38000, 26000, 1150, 4400, 7900, 5600, 6500]},
         grade=("A", 82, 0.35), since=2010, loans=1200, deposits=900),
    dict(id="C3", borrower="호텔신라", code="008770", industry="호텔·면세",
         project="호텔신라 제주 별관 증축", site="제주특별자치도 서귀포시 ○○동", scale="지하 2층 / 지상 8층, 객실 180실",
         use="숙박시설", months=24,
         contractor="삼성물산", ccode="028260", architect="□□건축사사무소",
         loan=420, tenor=6, grace=2, amort=10, spread=1.60,
         costs={"토지비": 0, "공사비": 520, "설계·감리비": 30, "기타 부대비용": 35, "금융비용": 35},
         extra={"임대수입(억원/년)": 0, "비용절감(억원/년)": 0, "객실수입 증가(억원/년)": 55},
         contract=548, adj_clause=True, guarantee="스캔본(인감증명서 미첨부)", liability="대출원금 전액",
         appraisal=dict(land=380, completed=900),
         fin={"2023": [38000, 900, 500, 30000, 21000, 9000, 12000, 450, 1300, 2000, 1800, 2100],
              "2024": [41000, 1100, 650, 30500, 20300, 10200, 12300, 480, 1350, 2200, 1900, 2100],
              "2025": [43000, 1250, 760, 30500, 19500, 11000, 12500, 500, 1400, 2400, 2000, 2100]},
         grade=("A-", 76, 0.55), since=2008, loans=900, deposits=600),
    dict(id="C4", borrower="오리온", code="271560", industry="식품 제조",
         project="오리온 진천 제2생산공장 신축", site="충청북도 진천군 ○○산업단지", scale="지상 3층, 연면적 36,000㎡",
         use="공장(자가사용 100%)", months=22,
         contractor="대우건설", ccode="047040", architect="◇◇건축사사무소",
         loan=700, tenor=7, grace=2, amort=12, spread=1.30,
         costs={"토지비": 90, "공사비": 720, "설계·감리비": 25, "기타 부대비용": 35, "금융비용": 60},
         extra={"임대수입(억원/년)": 0, "비용절감(억원/년)": 60},
         contract=720, adj_clause=False, guarantee="원본(인감증명서 첨부)", liability="대출원금 전액",
         appraisal=dict(land=110, completed=900),
         fin={"2023": [29000, 4900, 3500, 38000, 8000, 30000, 2500, 90, 1500, 6000, 9000, 500],
              "2024": [30500, 5300, 3900, 41000, 8200, 32800, 2400, 85, 1550, 6300, 9800, 500],
              "2025": [31500, 5500, 4100, 44000, 8300, 35700, 2300, 80, 1600, 6500, 10500, 500]},
         grade=("AA", 91, 0.08), since=2017, loans=300, deposits=1500),
    dict(id="C5", borrower="카카오", code="035720", industry="인터넷 플랫폼",
         project="카카오 안산 데이터센터 2단계 신축", site="경기도 안산시 상록구 ○○동", scale="지하 1층 / 지상 6층, IT 부하 40MW",
         use="방송통신시설(데이터센터)", months=28,
         contractor="현대건설", ccode="000720", architect="☆☆건축사사무소",
         loan=850, tenor=7, grace=3, amort=10, spread=1.50,
         costs={"토지비": 200, "공사비": 820, "설계·감리비": 40, "기타 부대비용": 90, "금융비용": 80},
         extra={"임대수입(억원/년)": 0, "비용절감(억원/년)": 70},
         contract=820, adj_clause=True, guarantee="원본(인감증명서 첨부)", liability="대출원금의 50%",
         appraisal=dict(land=210, completed=1500),
         fin={"2023": [75000, 4600, 1500, 250000, 105000, 145000, 40000, 1500, 9000, 14000, 50000, 11000],
              "2024": [78000, 4900, 1800, 255000, 104000, 151000, 39000, 1450, 9300, 14500, 52000, 11000],
              "2025": [80000, 5200, 2300, 258000, 103000, 155000, 38000, 1400, 9500, 15000, 53000, 11000]},
         grade=("A", 80, 0.40), since=2019, loans=600, deposits=2200),
    dict(id="C6", borrower="이마트", code="139480", industry="대형 유통",
         project="이마트 하남 복합쇼핑몰 증축", site="경기도 하남시 ○○동", scale="지하 3층 / 지상 6층, 연면적 58,000㎡",
         use="판매시설(자가 70%, 임대 30%)", months=24,
         contractor="HDC현대산업개발", ccode="294870", architect="▽▽건축사사무소",
         loan=550, tenor=5, grace=2, amort=10, spread=2.00,
         costs={"토지비": 260, "공사비": 560, "설계·감리비": 28, "기타 부대비용": 42, "금융비용": 45},
         extra={"임대수입(억원/년)": 38, "비용절감(억원/년)": 0},
         contract=560, adj_clause=True, guarantee="미제출", liability="-",
         appraisal=None,  # 감정평가서 미제출
         fin={"2023": [290000, 1300, 200, 280000, 160000, 120000, 70000, 1000, 13000, 16000, 12000, 11000],
              "2024": [295000, 1000, -300, 279000, 162000, 119000, 71000, 1000, 13000, 15500, 11500, 11000],
              "2025": [298000, 1700, 600, 282000, 161000, 121000, 70000, 1000, 13000, 16500, 12500, 11000]},
         grade=("A-", 74, 0.60), since=2011, loans=1500, deposits=800),
]

CONTRACTORS = {
    "GS건설": dict(limit=5000, used=4380, sanctions=[{"year": 2023, "event": "인천 검단 아파트 지하주차장 붕괴사고 관련 행정처분", "source": "공개 보도"}]),
    "DL이앤씨": dict(limit=6000, used=2100, sanctions=[]),
    "삼성물산": dict(limit=8000, used=3000, sanctions=[]),
    "대우건설": dict(limit=4000, used=1800, sanctions=[]),
    "현대건설": dict(limit=9000, used=7600, sanctions=[]),
    "HDC현대산업개발": dict(limit=5000, used=2600, sanctions=[{"year": 2022, "event": "광주 화정 아이파크 외벽 붕괴사고 관련 행정처분", "source": "공개 보도"}]),
}
FIN_KEYS = ["revenue", "operating_income", "net_income", "total_assets", "total_liabilities", "total_equity",
            "borrowings", "interest_expense", "depreciation", "operating_cf", "cash", "annual_debt_service"]
NOTE = "> 이 문서는 AI 여신심사 PoC 시연용 가상 서류입니다. 실제 기업의 계약·재무 내용과 무관합니다.\n"


def application(c):
    return """# 여신거래신청서

{note}
## 기본 정보
- 신청번호: CR-2026-{id}
- 차주: ㈜{borrower}
- 종목코드: {code}
- 업종: {industry}
- 여신과목: 시설자금대출 (신규)
- 신청금액(억원): {loan}
- 대출기간(년): {tenor}
- 거치기간(년): {grace}
- 연간분할상환비율(%): {amort}
- 신청금리: CD(91일) + {spread:.2f}%p
- 자금용도: {project} 공사비 및 부대비용
- 담보: 사업부지 및 신축건물 1순위 근저당
- 시공사: {contractor}
- 설계사: {architect}

## 상환 방식
거치기간 {grace}년 후 매년 대출금의 {amort}%를 분할상환하고, 만기 잔액은 일시상환한다.

## 신청인 확인
위 내용이 사실과 다름없음을 확인합니다.  2026-09-15  ㈜{borrower} 대표이사 (인)
""".format(note=NOTE, **c)


def plan(c):
    total = sum(c["costs"].values())
    equity = total - c["loan"]
    cost_rows = "\n".join("| {} | {:,} |".format(k, v) for k, v in c["costs"].items())
    extra_txt = "\n".join("- {}: {}".format(k, v) for k, v in c["extra"].items())
    return """# 사업계획서

{note}
## 1. 사업 개요
- 사업명: {project}
- 위치: {site}
- 규모: {scale}
- 용도: {use}
- 공사기간(개월): {months}
- 시공사: {contractor}
- 설계사: {architect}

## 2. 총사업비 (억원)
| 항목 | 금액 |
|---|---:|
{cost_rows}
| **합계** | **{total:,}** |

## 3. 자금조달 (억원)
| 항목 | 금액 |
|---|---:|
| 시설자금대출 (신청) | {loan:,} |
| 자기자금 | {equity:,} |
| **합계** | **{total:,}** |

## 4. 상환재원
기존 사업의 영업현금흐름을 주 상환재원으로 하고, 신축 시설에서 아래 추가 현금흐름을 기대한다.
{extra_txt}
""".format(note=NOTE, cost_rows=cost_rows, total=total, equity=equity, extra_txt=extra_txt, **c)


def contract(c):
    adj = ("- 제15조(설계변경 및 물가변동): 도급인의 요청에 의한 설계변경 또는 착공 후 90일 경과 시점의 주요자재 가격이 3% 이상 변동한 경우 계약금액을 조정할 수 있다."
           if c["adj_clause"] else "- 제15조(계약금액의 고정): 본 계약은 총액확정계약으로 설계변경·물가변동에 따른 계약금액 조정을 하지 않는다.")
    return """# 공사도급계약서 (요약본)

{note}
## 기본 정보
- 공사명: {project} 공사
- 도급인: ㈜{borrower}
- 수급인: {contractor}
- 계약금액(억원): {contract}
- 계약방식: 총액계약
- 공사기간(개월): {months}
- 기성지급: 월 1회, 감리자 확인 기성의 95% 지급, 5% 유보

## 주요 조항
- 제9조(지체상금): 지연 1일당 계약금액의 0.05%, 상한 계약금액의 10%
- 제12조(하자담보): 준공 후 공종별 1~10년
{adj}
- 제18조(책임준공): 수급인은 불가항력을 제외하고 약정 준공일까지 사용승인을 받아야 한다.
- 제21조(계약해지): 수급인의 부도·영업정지 등으로 공사 수행이 불가능한 경우 도급인은 계약을 해지할 수 있다.

## 책임준공 확약 (대주 앞)
- 확약서 제출: {guarantee}
- 배상한도: {liability}
""".format(note=NOTE, adj=adj, **c)


def appraisal(c):
    a = c["appraisal"]
    return """# 감정평가서 (요약)

{note}
## 기본 정보
- 평가대상: {project} 사업부지 및 준공 예정 건물
- 평가기관: (가상) □□감정평가법인
- 기준일: 2026-08-31
- 토지가치(억원): {land}
- 준공후가치(억원): {completed}
- 평가방법: 토지 공시지가기준법 / 준공 후 수익환원법·원가법 병용

## 비고
준공 후 가치는 사업계획서상 운영조건을 전제로 한 조건부 평가임.
""".format(note=NOTE, project=c["project"], **a)


def financials(c):
    return {"_meta": {"title": "재무제표 요약(연결) 2023~2025", "company": "㈜" + c["borrower"], "unit": "억원", "synthetic": True,
                      "note": "PoC 시연용 가상 수치. DART 연결 시 공시 수치로 대체·대사됨"},
            "years": {y: dict(zip(FIN_KEYS, v)) for y, v in c["fin"].items()}}


def main():
    borrowers, index = {}, []
    for c in CASES:
        d = HERE / c["id"]
        d.mkdir(exist_ok=True)
        for f in d.glob("0*"):
            f.unlink()
        (d / "01_여신거래신청서.md").write_text(application(c), encoding="utf-8")
        (d / "02_사업계획서.md").write_text(plan(c), encoding="utf-8")
        (d / "03_공사도급계약서.md").write_text(contract(c), encoding="utf-8")
        if c["appraisal"]:
            (d / "04_감정평가서.md").write_text(appraisal(c), encoding="utf-8")
        (d / "05_재무제표.json").write_text(json.dumps(financials(c), ensure_ascii=False, indent=1), encoding="utf-8")
        info = {"case_id": c["id"], "project": c["project"], "loan": c["loan"],
                "borrower": {"name": c["borrower"], "stock_code": c["code"], "industry": c["industry"]},
                "contractor": {"name": c["contractor"], "stock_code": c["ccode"]},
                "architect": {"name": c["architect"]}}
        (d / "case.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
        index.append(info)
        g = c["grade"]
        borrowers[c["borrower"]] = {
            "grade": {"grade": g[0], "css_score": g[1], "pd_1y_pct": g[2], "as_of": "2026-09-20"},
            "relationship": {"relationship_since": str(c["since"]), "existing_loans_krw_100m": c["loans"],
                             "deposits_krw_100m": c["deposits"], "delinquency_12m": 0}}
    (HERE / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    BANK.mkdir(exist_ok=True)
    (BANK / "borrowers.json").write_text(json.dumps({"_meta": {"title": "차주 DB (가상)", "synthetic": True}, "borrowers": borrowers},
                                                    ensure_ascii=False, indent=1), encoding="utf-8")
    (BANK / "contractors.json").write_text(json.dumps({"_meta": {"title": "시공사 책임준공 약정 관리현황 (가상)", "as_of": "2026-09-28", "synthetic": True},
                                                       "contractors": {k: {"commitment_limit_krw_100m": v["limit"], "commitment_used_krw_100m": v["used"],
                                                                           "sanction_history": v["sanctions"]} for k, v in CONTRACTORS.items()}},
                                                      ensure_ascii=False, indent=1), encoding="utf-8")
    print("사례 {}건 생성: {}".format(len(CASES), ", ".join(c["id"] + " " + c["borrower"] for c in CASES)))


if __name__ == "__main__":
    main()
