"""뉴스토어(빅카인즈) 뉴스검색 API 기간 수집 — 선택 사항."""
import json
import os
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta

from . import collect as naver, config, db


def _post(payload):
    req = urllib.request.Request(
        config.NEWSTORE_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def collect_period(start=None, end=None):
    key = os.environ.get("NEWSTORE_API_KEY")
    if not key:
        print("NEWSTORE_API_KEY 가 없어 뉴스토어 수집을 건너뜁니다.")
        return 0
    start = start or config.START_DATE
    end = end or date.today().isoformat()
    con = db.connect()
    new = 0
    for q in config.QUERIES:
        page = 0
        while True:
            payload = {
                "access_key": key,
                "argument": {
                    "query": q,
                    "published_at": {"from": start, "until": end},
                    "sort": {"date": "desc"},
                    "return_from": page * 100,
                    "return_size": 100,
                    "fields": ["title", "content", "published_at", "provider", "provider_link_page"],
                },
            }
            try:
                res = _post(payload)
            except urllib.error.HTTPError as e:
                print(f"  뉴스토어 오류 {e.code}: {e.read().decode('utf-8', 'replace')[:300]}")
                break
            docs = (res.get("return_object") or {}).get("documents") or []
            for d in docs:
                url = d.get("provider_link_page")
                try:
                    dt = datetime.fromisoformat(d["published_at"][:19])
                except Exception:
                    continue
                if naver.save_article(con, url=url, title=d.get("title"), desc=(d.get("content") or "")[:300],
                                      pub_dt=dt, source="newstore", query=q, press=d.get("provider")):
                    new += 1
            con.commit()
            if len(docs) < 100:
                break
            page += 1
    db.log_run(con, "newstore", json.dumps({"new": new}))
    print(f"뉴스토어 수집 완료: 신규 {new}건")
    con.close()
    return new


def recent(days=3):
    return collect_period((date.today() - timedelta(days=days)).isoformat(), date.today().isoformat())
