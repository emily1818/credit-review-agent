"""여신심사 AI Agent PoC 실행 (CLI).

  python3 run.py --case C1                 # 심사역 권한, 규칙 기반(LLM 없이)
  python3 run.py --case C2 --role rm       # 영업점 RM 권한 (내부등급 마스킹)
  python3 run.py --case C1 --outage news,ecos   # 외부 API 장애 재현 → Fallback
  python3 run.py --case C6 --mode codex    # Codex CLI가 MCP로 도구를 호출 (codex 로그인 필요)
  python3 run.py --all                     # 6건 모두 규칙 기반으로 실행
  python3 webapp.py                        # 업로드 화면 (http://localhost:8780)
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))
from credit_agent import agent, codex_runner, config, report  # noqa: E402
from credit_agent.docs import Case  # noqa: E402
from credit_agent.tools import Context  # noqa: E402


def run_one(case_dir, role, mode, outage="", out=None, log=None):
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    config.OUT.mkdir(exist_ok=True)
    case = Case(case_dir)
    out = Path(out) if out else config.OUT / "report_{}_{}_{}.html".format(case.id, role, stamp)
    log = Path(log) if log else out.with_suffix(".audit.jsonl")
    outages = [x for x in outage.split(",") if x]
    if mode == "codex":
        last = out.with_suffix(".codex.txt")
        rc = codex_runner.run(case_dir, role, out, log, last, outage)
        if last.exists():
            print("\n[Codex 최종 답변]\n" + last.read_text(encoding="utf-8").strip())
        if not out.exists():  # Codex·MCP 서버가 비정상 종료한 경우
            print("Codex가 보고서를 남기지 못함 (종료코드 {}) → 규칙 기반 초안으로 대체".format(rc))
            ctx = Context(role, case, outages, log)
            ctx.note_fallback("LLM 서술(Codex)", "규칙 기반 템플릿")
            agent.run(ctx, "offline")
            out.write_text(report.render(ctx, "offline"), encoding="utf-8")
        return out
    ctx = Context(role, case, outages, log)
    agent.run(ctx, mode)
    out.write_text(report.render(ctx, mode), encoding="utf-8")
    print("\n[{}] 권고: {} | 출처 {}개 | Fallback {}건 | 사람 확인 {}건".format(
        case.id, ctx.report["recommendation"], len(ctx.sources.sources), len(ctx.fallbacks), len(ctx.hitl.items)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="C1", help="data/cases 아래 사례 ID (C1~C6)")
    ap.add_argument("--case-dir", default=None, help="사례 폴더 직접 지정")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--role", default="reviewer", choices=["reviewer", "rm", "compliance"])
    ap.add_argument("--mode", default="offline", choices=["offline", "claude", "codex"])
    ap.add_argument("--outage", default="", help="장애 재현: news,ecos,dart")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    dirs = sorted(p for p in config.CASES.iterdir() if (p / "case.json").exists()) if a.all else \
        [Path(a.case_dir) if a.case_dir else config.CASES / a.case]
    for d in dirs:
        print("보고서:", run_one(d, a.role, a.mode, a.outage, None if a.all else a.out))


if __name__ == "__main__":
    main()
