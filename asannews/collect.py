"""NAVER API HUB 뉴스 검색 수집."""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from email.utils import parsedate_to_datetime

from . import config, db, text


def _keys():
    cid = os.environ.get("NAVER_CLIENT_ID")
    sec = os.environ.get("NAVER_CLIENT_SECRET")
    if not cid or not sec:
        sys.exit(".env 파일에 NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 을 입력하세요.")
    return cid, sec


def _request(params, cid, sec, retries=5):
    url = config.NAVER_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "X-NCP-APIGW-API-KEY-ID": cid,
        "X-NCP-APIGW-API-KEY": sec,
        "User-Agent": "asan-news-dashboard/1.0",
    })
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            if e.code == 429 and attempt < retries - 1:
                wait = 2 ** attempt
                print(f"  429 요청 한도 — {wait}초 대기 후 재시도")
                time.sleep(wait)
                continue
            sys.exit(f"네이버 API 오류 {e.code}: {body}")
    sys.exit("네이버 API 재시도 한도 초과")


def save_article(con, *, url, title, desc, pub_dt, source, query, naver_link=None, press=None):
    """관련 기사만 URL 기준 중복 없이 저장. 저장되면 True."""
    title, desc = text.clean(title), text.clean(desc)
    if not url or not title or not text.is_relevant(title, desc):
        return False
    dom = text.domain_of(url)
    cur = con.execute(
        """INSERT OR IGNORE INTO articles
           (url, naver_link, title, description, pub_date, pub_datetime, press, domain,
            source, query, topic, collected_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (url, naver_link, title, desc, pub_dt.strftime("%Y-%m-%d"),
         pub_dt.isoformat(timespec="seconds"), press or text.press_from_domain(dom), dom,
         source, query, text.classify_topic(title, desc),
         datetime.now().isoformat(timespec="seconds")),
    )
    return cur.rowcount > 0


def collect():
    cid, sec = _keys()
    con = db.connect()
    start = datetime.strptime(config.START_DATE, "%Y-%m-%d").date()
    total = {"fetched": 0, "relevant_new": 0, "irrelevant": 0}
    for q in config.QUERIES:
        new = fetched = 0
        for st in range(1, 1000, 100):
            data = _request({"query": q, "display": 100, "start": st, "sort": "date"}, cid, sec)
            items = data.get("items", [])
            if not items:
                break
            stop = False
            for it in items:
                fetched += 1
                try:
                    dt = parsedate_to_datetime(it["pubDate"]).replace(tzinfo=None)
                except Exception:
                    continue
                if dt.date() < start:
                    stop = True
                    continue
                url = it.get("originallink") or it.get("link")
                if save_article(con, url=url, title=it.get("title"), desc=it.get("description"),
                                pub_dt=dt, source="naver", query=q, naver_link=it.get("link")):
                    new += 1
                else:
                    total["irrelevant"] += 0  # 중복·무관 구분 없이 버림
            con.commit()
            if stop or len(items) < 100:
                break
            time.sleep(0.15)
        total["fetched"] += fetched
        total["relevant_new"] += new
        print(f"  [{q}] 조회 {fetched}건 · 신규 {new}건")
    db.log_run(con, "collect", json.dumps(total, ensure_ascii=False))
    print(f"수집 완료: 신규 {total['relevant_new']}건")
    con.close()
    return total
