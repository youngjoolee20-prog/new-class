"""원문 페이지 확인 — 매체명(og:site_name) 보정과 조회수 수집."""
import re
import urllib.request
import urllib.robotparser
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from urllib.parse import urlparse

from . import config, db

UA = "Mozilla/5.0 (compatible; AsanNewsDashboard/1.0)"
_robots = {}
_OG_SITE = re.compile(r'<meta[^>]+property=["\']og:site_name["\'][^>]+content=["\']([^"\']{1,40})["\']', re.I)
_OG_SITE2 = re.compile(r'<meta[^>]+content=["\']([^"\']{1,40})["\'][^>]+property=["\']og:site_name["\']', re.I)
_VIEWS = re.compile(r"조회(?:수)?\s*[:：]?\s*(?:</?[^>]{0,40}>\s*)*([0-9][0-9,]{0,9})(?!\s*[.\-/년월일:])")
_CHARSET = re.compile(rb'charset=["\']?([A-Za-z0-9_\-]+)', re.I)


def _allowed(url):
    p = urlparse(url)
    base = f"{p.scheme}://{p.netloc}"
    if base not in _robots:
        rp = urllib.robotparser.RobotFileParser(base + "/robots.txt")
        try:
            rp.read()
        except Exception:
            rp = None
        _robots[base] = rp
    rp = _robots[base]
    return True if rp is None else rp.can_fetch(UA, url)


def _decode(raw, ctype):
    enc = None
    m = re.search(r"charset=([\w\-]+)", ctype or "", re.I)
    if m:
        enc = m.group(1)
    else:
        m2 = _CHARSET.search(raw[:4000])
        if m2:
            enc = m2.group(1).decode()
    for e in (enc, "utf-8", "euc-kr", "cp949"):
        if not e:
            continue
        try:
            return raw.decode(e)
        except Exception:
            continue
    return raw.decode("utf-8", "replace")


def fetch(row):
    url, dom = row["url"], row["domain"] or ""
    if not url.startswith("http"):
        return row["id"], None, None, "skip"
    try:
        if not _allowed(url):
            return row["id"], None, None, "robots"
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=config.VIEWS_TIMEOUT) as r:
            html = _decode(r.read(800_000), r.headers.get("Content-Type"))
    except Exception:
        return row["id"], None, None, "error"
    m = _OG_SITE.search(html) or _OG_SITE2.search(html)
    site = m.group(1).strip() if m else None
    views = None
    if any(dom == d or dom.endswith("." + d) for d in config.VIEWS_TRUSTED_DOMAINS):
        vm = _VIEWS.search(html)
        if vm:
            v = int(vm.group(1).replace(",", ""))
            if 0 <= v < 50_000_000:
                views = v
    return row["id"], site, views, "ok" if views is not None else "none"


def run(limit=3000):
    con = db.connect()
    since = (date.today() - timedelta(days=config.VIEWS_RECHECK_DAYS)).isoformat()
    rows = con.execute(
        """SELECT id, url, domain FROM articles
           WHERE source != 'sample' AND (views_checked IS NULL OR pub_date >= ?)
           ORDER BY pub_date DESC LIMIT ?""", (since, limit)).fetchall()
    if not rows:
        print("확인할 원문이 없습니다.")
        return 0
    now = datetime.now().isoformat(timespec="seconds")
    ok = 0
    with ThreadPoolExecutor(config.VIEWS_THREADS) as ex:
        for aid, site, views, status in ex.map(fetch, rows):
            if site:
                con.execute("UPDATE articles SET press=? WHERE id=? AND (press=domain OR press IS NULL)", (site, aid))
            con.execute("UPDATE articles SET views=COALESCE(?, views), views_checked=?, views_status=? WHERE id=?",
                        (views, now, status, aid))
            ok += views is not None
    con.commit()
    db.log_run(con, "views", f"checked {len(rows)}, views {ok}")
    print(f"원문 확인 {len(rows)}건 · 조회수 확인 {ok}건")
    con.close()
    return ok
