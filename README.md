# 기업여신 심사 AI Agent (PoC)

> ⚠️ **모든 차주 제출서류·은행 내부자료·재무수치는 시연용 가상 데이터입니다.** 실제 기업의 계약·재무·신용상태와 무관하며, 기업명은 시나리오 구성을 위해서만 사용했습니다. 금리(한국은행 ECOS)와 뉴스(Google News)만 실제 데이터입니다.

**데모:** https://emily1818.github.io/credit-review-agent/

차주가 서류를 제출하면 AI Agent가 재무자료·기업정보·내부규정·외부뉴스를 모아 분석하고, 위험요인과 근거를 정리한 **심사보고서 초안**을 만듭니다. 확정할 수 없는 항목은 심사역에게 넘깁니다.

금융은 정확성과 신뢰가 중요한 산업이므로, 적용 범위를 넓히기보다 **출처 · 권한관리 · Fallback · Human-in-the-loop** 안전장치를 함께 갖추는 데 초점을 맞췄습니다.

```
[서류 업로드] → [Agent: 도구 호출] → [코드가 지표·규정 판정] → [LLM이 근거 붙여 서술] → [출처 검증] → [심사역 확인] → 보고서
```

## 데모 사례 6건

| 사례 | 차주 | 사업 | 시공사 | 결과 | 원인 |
|---|---|---|---|---|---|
| C1 | HDC랩스 | 분당 사옥 겸 R&D센터 | GS건설 | 조건부 승인 | 시공사 사고 이력, 약정 한도 97%, 공사비 불일치 |
| C2 | CJ대한통운 | 이천 물류센터 | DL이앤씨 | **승인** | 모든 기준 충족 |
| C3 | 호텔신라 | 제주 별관 증축 | 삼성물산 | 조건부 승인 | 공사비 28억 차이, 확약서 스캔본, DSCR 경계 |
| C4 | 오리온 | 진천 공장 | 대우건설 | **보류** | 자기자금 24.7%, LTV 77.8% |
| C5 | 카카오 | 안산 데이터센터 | 현대건설 | 조건부 승인 | 책임준공 배상한도 50%, 약정 한도 94% |
| C6 | 이마트 | 하남 복합몰 증축 | HDC현대산업개발 | **보류** | 감정평가서·책임준공확약서 미제출 |

사례마다 제출서류 5종이 `data/cases/C1/` 같은 폴더에 들어 있습니다: 여신거래신청서, 사업계획서, 공사도급계약서(책임준공 포함), 감정평가서, 재무제표(DART 연결 시 선택). 서류를 빼거나 수정해서 넣으면 결과가 달라집니다.

## 실행

**웹 데모(GitHub Pages):** 위 링크에서 브라우저 안(Pyodide)으로 규칙 기반 Agent가 돌아갑니다. 브라우저에서는 외부 API를 부를 수 없어서 배포 시점 캐시로 Fallback되고, 보고서에 그렇게 표시됩니다.

**로컬(Codex가 Agent 두뇌):**

```bash
git clone https://github.com/emily1818/credit-review-agent && cd credit-review-agent
python3 webapp.py                      # http://localhost:8780 → 사례 선택 → 서류 업로드 → 분석
python3 run.py --all                   # 6건 규칙 기반 일괄 실행
python3 run.py --case C1 --mode codex  # Codex CLI가 MCP로 도구 호출 (codex 로그인 필요)
python3 run.py --case C2 --role rm     # 영업점 RM 권한: 내부등급 마스킹
python3 run.py --case C1 --outage news,ecos   # API 장애 재현 → 캐시 Fallback
```

Python 3.9 이상, 표준 라이브러리만 사용합니다. OpenDART 재무제표를 쓰려면 `.env`에 `DART_API_KEY=...`를 넣으세요. 키에 사용 IP 제한이 있으면 OpenDART 마이페이지에서 현재 IP를 등록해야 합니다.

## 구조

```
webapp.py                     업로드 화면 → 분석 진행(실시간 로그) → 보고서
run.py                        CLI
src/credit_agent/
  tools.py                    Agent 도구 10개 (서류, 내부자료, 재무, 금리, 뉴스, 규정검색, 검증, HITL, 보고서 제출)
  guardrails.py               출처 등록·검증, 권한, Fallback, HITL 큐, 감사로그
  analysis.py                 DSCR·LTV·부채비율 계산, 규정 판정, 문서 간 대사 (결정론적)
  agent.py                    규칙 기반 실행 / Claude tool use
  mcp_server.py               도구를 MCP 서버로 노출 → Codex가 두뇌
  codex_runner.py             codex exec + MCP 설정
  docs.py                     사례 로딩, 은행 DB, 규정 조문 검색(RAG)
  report.py                   심사보고서 HTML
  connectors/                 ecos.py, dart.py, news.py
data/cases/                   데모 사례 6건 (generate.py로 재생성)
data/bank/                    가상 규정 3종, 차주·시공사 DB, 권한정책
scripts/build_pages.py        GitHub Pages 데모 빌드 → docs/
```

## 안전장치

| 원칙 | 구현 |
|---|---|
| 출처 | Agent가 본 모든 자료에 ID를 붙이고(`SUB-03`, `ECOS-CD91`, `REG-02-8`) 보고서 문장마다 인용을 강제합니다. 출처가 없거나 등록되지 않은 ID를 인용하면 `submit_report`에서 반려합니다. |
| 숫자 | DSCR, LTV, 부채비율은 `analysis.py`가 계산합니다. LLM은 계산 결과를 인용해 서술만 합니다. |
| 권고 상한 | 규정 판정상 보류인 건을 LLM이 승인으로 쓰면 반려합니다. 더 보수적인 권고는 허용합니다. |
| 권한관리 | 역할별 열람 범위를 적용합니다. RM은 내부등급(restricted)을 볼 수 없고, 거부 기록은 감사로그와 심사역 확인 목록에 남습니다. |
| Fallback | 실시간 API → 로컬 캐시 → 대체자료(DART → 차주 제출본) → 사람 확인 순서로 내려갑니다. LLM이 실패하면 규칙 기반 초안으로 대체합니다. 어느 단계를 썼는지 보고서에 표시합니다. |
| Human-in-the-loop | 서류 누락, 문서 불일치, 원본 미확인, 권한 밖 자료, Fallback 데이터, 전결권 초과는 사람에게 넘깁니다. 모두 확인해야 상신 버튼이 열립니다. |

Agent의 두뇌(LLM)는 바꿔 끼울 수 있습니다. 도구와 안전장치는 MCP 서버 쪽에 있으므로, Codex·Claude·사내 LLM 중 무엇을 붙여도 같은 규칙이 적용됩니다.

데이터 구분(가상/실제)과 실제 연동 가능한 API 목록은 [data/DATA_INVENTORY.md](data/DATA_INVENTORY.md)에 있습니다.
