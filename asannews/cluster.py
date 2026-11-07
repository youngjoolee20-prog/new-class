"""유사 제목 기사 → 하나의 이슈로 통합."""
import re
from collections import defaultdict
from datetime import date

from . import config, db, text

_NONWORD = re.compile(r"[^0-9A-Za-z가-힣]+")
_BRACKETS = re.compile(r"\[[^\]]*\]|\([^)]*\)|【[^】]*】|<[^>]*>|“|”|‘|’")


def normalize(title):
    t = text.strip_prefix(title)
    t = _BRACKETS.sub(" ", t)
    return _NONWORD.sub(" ", t).strip()


def bigrams(s):
    s = s.replace(" ", "")
    return {s[i:i + 2] for i in range(len(s) - 1)} or {s}


def jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


class DSU:
    def __init__(self):
        self.p = {}
        self.lo = {}
        self.hi = {}

    def add(self, x, d):
        self.p[x] = x
        self.lo[x] = self.hi[x] = d

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b, max_span):
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        lo, hi = min(self.lo[ra], self.lo[rb]), max(self.hi[ra], self.hi[rb])
        if (hi - lo).days > max_span:   # 연쇄 병합 방지
            return
        self.p[rb] = ra
        self.lo[ra], self.hi[ra] = lo, hi


def run():
    con = db.connect()
    rows = con.execute("SELECT id, title, pub_date, press, views, topic FROM articles").fetchall()
    arts = []
    for r in rows:
        norm = normalize(r["title"])
        arts.append({
            "id": r["id"], "title": r["title"], "date": date.fromisoformat(r["pub_date"]),
            "press": r["press"], "views": r["views"], "topic": r["topic"],
            "bg": bigrams(norm), "words": {w for w in norm.split() if len(w) >= 2},
        })
    by_id = {a["id"]: a for a in arts}
    dsu = DSU()
    index = defaultdict(list)   # (날짜 서수, 단어) → id
    for a in arts:
        dsu.add(a["id"], a["date"])
        index_key = a["date"].toordinal()
        for w in a["words"]:
            index[(index_key, w)].append(a["id"])
    for a in arts:
        o = a["date"].toordinal()
        cands = set()
        for dd in range(0, config.CLUSTER_WINDOW_DAYS + 1):
            for w in a["words"]:
                cands.update(index.get((o + dd, w), ()))
        for cid in cands:
            if cid <= a["id"] and by_id[cid]["date"] == a["date"]:
                continue
            if cid == a["id"]:
                continue
            if jaccard(a["bg"], by_id[cid]["bg"]) >= config.CLUSTER_SIM:
                dsu.union(a["id"], cid, config.CLUSTER_MAX_SPAN)
    groups = defaultdict(list)
    for a in arts:
        groups[dsu.find(a["id"])].append(a)

    con.execute("DELETE FROM clusters")
    for members in groups.values():
        cid = min(m["id"] for m in members)
        if len(members) == 1:
            rep = members[0]
        else:
            rep = max(members, key=lambda m: sum(jaccard(m["bg"], o["bg"]) for o in members if o is not m))
        topics = defaultdict(int)
        for m in members:
            topics[m["topic"]] += 1
        views = [m["views"] for m in members if m["views"] is not None]
        con.execute(
            "INSERT INTO clusters VALUES (?,?,?,?,?,?,?,?)",
            (cid, text.strip_prefix(rep["title"]), min(m["date"] for m in members).isoformat(),
             max(m["date"] for m in members).isoformat(), len(members),
             len({m["press"] for m in members}), sum(views) if views else None,
             max(topics, key=topics.get)),
        )
        con.executemany("UPDATE articles SET cluster_id=? WHERE id=?", [(cid, m["id"]) for m in members])
    con.commit()
    db.log_run(con, "cluster", f"{len(arts)} articles → {len(groups)} issues")
    print(f"이슈 통합: 기사 {len(arts)}건 → 이슈 {len(groups)}개")
    con.close()
    return len(groups)
