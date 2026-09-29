import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# .env (KEY=VALUE) 로딩. 이미 설정된 환경변수가 우선한다.
_env = ROOT / ".env"
if _env.exists():
    for _line in _env.read_text(encoding="utf-8").splitlines():
        if "=" in _line and not _line.lstrip().startswith("#"):
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))
DATA = ROOT / "data"
CASES = DATA / "cases"
BANK = DATA / "bank"
CACHE = DATA / "cache"
OUT = ROOT / "out"
RUNS = OUT / "runs"

DART_API_KEY = os.environ.get("DART_API_KEY", "")
# ECOS는 'sample' 키로도 10건까지 조회된다. 운영에서는 발급받은 키를 쓴다.
ECOS_API_KEY = os.environ.get("ECOS_API_KEY") or "sample"
HTTP_TIMEOUT = float(os.environ.get("HTTP_TIMEOUT", "8"))

CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-5-5")
CURRENT_YEAR = 2026
