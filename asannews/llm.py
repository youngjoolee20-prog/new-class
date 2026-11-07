"""Gemini 해석 — 숫자를 만들지 않고, stats.py가 계산한 JSON만 해석한다."""
import copy
import json
import os
import urllib.error
import urllib.request

from . import config

PROMPT = """너는 지방자치단체 홍보 성과를 분석하는 통계 담당 공무원이다.
아래 JSON은 {region} 관련 온라인 뉴스의 통계 분석 결과다. 다음 규칙을 반드시 지켜 해석하라.

[규칙]
1. JSON에 있는 수치만 사용하고, 새로운 수치를 만들거나 계산하지 말 것.
2. 상관의 유의성은 p_holm(Holm 보정 p) 기준 0.05로 판단할 것.
3. 인과관계를 단정하지 말 것("~때문" 금지, "~와 함께 나타남" 등으로 표현).
4. 추세 문장에는 수집 편향(포털 검색 기반) 가능성을 명시할 것.
5. 표본이 작거나(n<12) 유의하지 않으면 결론을 유보할 것.
6. 공무원 보고서 개조식 문체("~함", "~임", "~필요")로 작성할 것.
7. 'note'가 붙은 상관은 구조적 관계임을 언급할 것.

[출력 JSON 형식]
{{"headline": "한 문장 요약",
 "key_findings": ["핵심 발견 3~5개"],
 "sections": {{"trend": "...", "correlation": "...", "weekday": "...", "topic_spread": "...",
              "topic_month": "...", "budget": "..."}},
 "recommendations": ["제언 3개"],
 "caveats": ["유의사항 2~4개"]}}

[통계 결과]
{data}
"""


def _strip(stats):
    """차트용 원자료(points, series 등)는 빼고 보낸다."""
    s = copy.deepcopy(stats)

    def walk(o):
        if isinstance(o, dict):
            for k in list(o):
                if k in ("points", "series", "counts", "rows", "matrix"):
                    o.pop(k)
                else:
                    walk(o[k])
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(s)
    return s


def interpret(stats):
    key = os.environ.get("GEMINI_API_KEY")
    if not key or not stats.get("available"):
        return None
    url = f"{config.GEMINI_BASE_URL}/v1beta/models/{config.GEMINI_TEXT_MODEL}:generateContent"
    body = {
        "contents": [{"role": "user", "parts": [{"text": PROMPT.format(
            region=config.REGION, data=json.dumps(_strip(stats), ensure_ascii=False))}]}],
        "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
    }
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json", "x-goog-api-key": key})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            res = json.loads(r.read().decode("utf-8"))
        txt = res["candidates"][0]["content"]["parts"][0]["text"]
        out = json.loads(txt)
        if not isinstance(out, dict) or "headline" not in out:
            return None
        return out
    except urllib.error.HTTPError as e:
        print(f"Gemini 오류 {e.code}: {e.read().decode('utf-8', 'replace')[:300]}")
    except Exception as e:
        print(f"Gemini 해석 실패: {e}")
    return None
