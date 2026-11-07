"""DB → dashboard/data.js (window.ASAN_DATA, window.ASAN_REPORT)."""
import json
from datetime import datetime

from . import config, db


def export(report=None, sample=False):
    con = db.connect()
    rows = con.execute(
        "SELECT id, pub_date, cluster_id, press, title, url, views, topic FROM articles ORDER BY pub_date, id"
    ).fetchall()
    press_cnt = {}
    for r in rows:
        press_cnt[r["press"]] = press_cnt.get(r["press"], 0) + 1
    press = sorted(press_cnt, key=lambda p: -press_cnt[p])
    pidx = {p: i for i, p in enumerate(press)}
    topics = config.TOPIC_ORDER
    tidx = {t: i for i, t in enumerate(topics)}
    clusters = {str(c["id"]): c["title"] for c in con.execute("SELECT id, title FROM clusters")}
    articles = [[r["id"], r["pub_date"], r["cluster_id"], pidx[r["press"]], r["title"], r["url"],
                 r["views"], tidx.get(r["topic"], len(topics) - 1)] for r in rows]
    con.close()
    meta = {
        "region": config.REGION, "system": config.SYSTEM_NAME, "operator": config.OPERATOR,
        "maker": config.MAKER, "start": config.START_DATE,
        "first": rows[0]["pub_date"] if rows else None, "last": rows[-1]["pub_date"] if rows else None,
        "generated": datetime.now().isoformat(timespec="seconds"), "total": len(rows),
        "sample": sample, "bigIssuePress": config.BIG_ISSUE_PRESS, "updateTime": config.UPDATE_TIME_LABEL,
        "brand": config.BRAND_COLORS,
    }
    data = {"meta": meta, "press": press, "topics": topics, "clusters": clusters, "articles": articles}
    js = "/* 자동 생성 파일 — 직접 수정하지 마세요 */\n"
    js += "window.ASAN_DATA = " + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n"
    js += "window.ASAN_REPORT = " + json.dumps(report or {}, ensure_ascii=False, separators=(",", ":")) + ";\n"
    config.DATA_JS.parent.mkdir(parents=True, exist_ok=True)
    config.DATA_JS.write_text(js, encoding="utf-8")
    print(f"data.js 저장: 기사 {len(rows)}건 · 매체 {len(press)}곳 · 이슈 {len(clusters)}개")
