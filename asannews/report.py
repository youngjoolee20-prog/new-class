"""통계 + AI 해석 묶기. AI 실패·키 없음이면 직전 해석을 재사용한다."""
import json
import re
from datetime import datetime

from . import config, llm, stats


def _previous_ai():
    if config.REPORT_JSON.exists():
        try:
            return json.loads(config.REPORT_JSON.read_text(encoding="utf-8")).get("ai")
        except Exception:
            pass
    if config.DATA_JS.exists():
        m = re.search(r"window\.ASAN_REPORT\s*=\s*(\{.*?\});\s*$", config.DATA_JS.read_text(encoding="utf-8"), re.S | re.M)
        if m:
            try:
                return json.loads(m.group(1)).get("ai")
            except Exception:
                pass
    return None


def build(con=None, use_ai=False):
    result = stats.analyze(con)
    ai, ai_status = None, "none"
    if use_ai:
        ai = llm.interpret(result)
        ai_status = "fresh" if ai else "none"
    if ai is None:
        prev = _previous_ai()
        if prev:
            ai, ai_status = prev, ai_status if ai_status == "fresh" else "reused"
    rep = {"generated": datetime.now().isoformat(timespec="seconds"), "stats": result,
           "ai": ai, "ai_status": ai_status, "model": config.GEMINI_TEXT_MODEL if ai else None}
    try:
        config.REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
        config.REPORT_JSON.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass
    label = {"fresh": "AI 해석 포함", "reused": "직전 AI 해석 재사용", "none": "AI 해석 없음(통계만)"}[ai_status]
    print(f"보고서 생성: {label}")
    return rep
