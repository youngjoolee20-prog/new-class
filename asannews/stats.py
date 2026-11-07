"""통계 분석 — 보고서의 모든 숫자는 여기서만 만든다(결정적 계산, scipy)."""
import csv
import math
from collections import Counter, defaultdict
from datetime import date, timedelta

import numpy as np
from scipy import stats as st

from . import config, db

WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]


def p3(p):
    """p값 유효숫자 3자리 보존(0으로 뭉개지지 않게)."""
    if p is None or (isinstance(p, float) and math.isnan(p)):
        return None
    return float(f"{p:.3g}")


def r3(x, nd=3):
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return None
    return round(float(x), nd)


def strength(r):
    a = abs(r or 0)
    if a >= 0.7:
        return "강함"
    if a >= 0.4:
        return "중간"
    if a >= 0.2:
        return "약함"
    return "거의 없음"


def holm(ps):
    """Holm-Bonferroni 보정."""
    idx = [i for i, p in enumerate(ps) if p is not None]
    order = sorted(idx, key=lambda i: ps[i])
    m = len(order)
    out = [None] * len(ps)
    running = 0.0
    for k, i in enumerate(order):
        adj = min(1.0, (m - k) * ps[i])
        running = max(running, adj)
        out[i] = running
    return out


def describe(values):
    a = np.asarray(values, dtype=float)
    if a.size == 0:
        return None
    mean = float(a.mean())
    sd = float(a.std(ddof=1)) if a.size > 1 else 0.0
    return {"n": int(a.size), "mean": r3(mean, 2), "sd": r3(sd, 2), "median": r3(float(np.median(a)), 2),
            "min": r3(float(a.min()), 2), "max": r3(float(a.max()), 2),
            "cv": r3(sd / mean, 3) if mean else None}


def fisher_ci(r, n):
    if n <= 3 or r is None or abs(r) >= 1:
        return [None, None]
    z = math.atanh(r)
    se = 1 / math.sqrt(n - 3)
    return [r3(math.tanh(z - 1.96 * se)), r3(math.tanh(z + 1.96 * se))]


def _load(con):
    arts = con.execute("SELECT id, pub_date, press, topic, cluster_id, views FROM articles").fetchall()
    clus = con.execute("SELECT id, first_date, article_cnt, press_cnt, topic FROM clusters").fetchall()
    return arts, clus


def week_start(d):
    return d - timedelta(days=d.weekday())


def analyze(con=None):
    own = con is None
    con = con or db.connect()
    arts, clus = _load(con)
    if own:
        con.close()
    if not arts:
        return {"available": False, "reason": "데이터 없음"}

    today = date.today()
    cur_week = week_start(today)
    dates = [date.fromisoformat(a["pub_date"]) for a in arts]
    first, last = min(dates), max(dates)

    # ── 주간 집계(진행 중인 주 제외) ──
    wk = defaultdict(lambda: {"articles": 0, "issues": set(), "press": set(), "views": 0, "views_n": 0})
    daily = Counter()
    for a, d in zip(arts, dates):
        daily[d] += 1
        w = week_start(d)
        if w >= cur_week:
            continue
        g = wk[w]
        g["articles"] += 1
        g["issues"].add(a["cluster_id"])
        g["press"].add(a["press"])
        if a["views"] is not None:
            g["views"] += a["views"]
            g["views_n"] += 1
    big_by_week = Counter()
    for c in clus:
        w = week_start(date.fromisoformat(c["first_date"]))
        if c["press_cnt"] >= config.BIG_ISSUE_PRESS and w < cur_week:
            big_by_week[w] += 1
    weeks = []
    w = week_start(first)
    while w < cur_week:
        g = wk.get(w)
        n_art = g["articles"] if g else 0
        n_iss = len(g["issues"]) if g else 0
        weeks.append({
            "week": w.isoformat(), "articles": n_art, "issues": n_iss,
            "press": len(g["press"]) if g else 0, "big": big_by_week.get(w, 0),
            "per_issue": round(n_art / n_iss, 3) if n_iss else 0.0,
            "views": g["views"] if g and g["views_n"] else None,
        })
        w += timedelta(days=7)

    # 일간 시계열(오늘 제외)
    days = []
    d = first
    while d < today and d <= last:
        days.append({"date": d.isoformat(), "count": daily.get(d, 0), "weekday": d.weekday()})
        d += timedelta(days=1)

    out = {"available": True, "period": {"first": first.isoformat(), "last": last.isoformat(),
                                          "weeks": len(weeks), "days": len(days),
                                          "excluded_current_week": cur_week.isoformat()}}
    y = np.array([x["articles"] for x in weeks], dtype=float)

    # ── 기술통계 ──
    out["descriptive"] = {
        "weekly": describe(y) if len(y) else None,
        "daily": describe([x["count"] for x in days]) if days else None,
        "total_articles": len(arts), "total_issues": len(clus),
        "total_press": len({a["press"] for a in arts}),
    }

    # ── 추세 ──
    if len(weeks) >= 4:
        x = np.arange(len(weeks), dtype=float)
        lr = st.linregress(x, y)
        sp = st.spearmanr(x, y)
        out["trend"] = {
            "n": len(weeks), "slope": r3(lr.slope, 3), "intercept": r3(lr.intercept, 3),
            "r2": r3(lr.rvalue ** 2, 3), "p": p3(lr.pvalue),
            "spearman_rho": r3(sp.statistic), "spearman_p": p3(sp.pvalue),
            "direction": "증가" if lr.slope > 0 else "감소",
            "significant": bool(lr.pvalue < 0.05),
            "points": [{"week": wd["week"], "articles": wd["articles"]} for wd in weeks],
        }
    else:
        out["trend"] = {"n": len(weeks), "available": False}

    # ── 상관(주간 지표 ↔ 보도 건수) ──
    metrics = [("issues", "이슈 수"), ("press", "보도 매체 수"), ("big", "대형 확산 이슈 수"),
               ("per_issue", "이슈당 보도 건수")]
    views_weeks = [wd for wd in weeks if wd["views"] is not None]
    if len(views_weeks) >= 5:
        metrics.append(("views", "확인 조회수"))
    corr = []
    for key, label in metrics:
        sub = [wd for wd in weeks if wd[key] is not None]
        xs = np.array([wd[key] for wd in sub], dtype=float)
        ys = np.array([wd["articles"] for wd in sub], dtype=float)
        if len(sub) < 5 or xs.std() == 0 or ys.std() == 0:
            continue
        pr = st.pearsonr(xs, ys)
        sp = st.spearmanr(xs, ys)
        item = {"key": key, "label": label, "n": len(sub), "r": r3(pr.statistic), "p": p3(pr.pvalue),
                "ci95": fisher_ci(float(pr.statistic), len(sub)), "rho": r3(sp.statistic), "rho_p": p3(sp.pvalue),
                "strength": strength(pr.statistic),
                "points": [[wd[key], wd["articles"]] for wd in sub]}
        if key == "issues":
            item["note"] = "보도 건수 = 이슈 수 × 이슈당 보도이므로 구조적 상관이 포함됨"
        if key == "press":
            item["note"] = "매체 수와 보도 건수는 함께 늘어나는 구조적 관계가 있음"
        corr.append(item)
    adj = holm([c["p"] for c in corr])
    for c, a in zip(corr, adj):
        c["p_holm"] = p3(a)
        c["significant"] = bool(a is not None and a < 0.05)
    out["correlation"] = corr

    # 상관행렬
    keys = [("articles", "보도 건수"), ("issues", "이슈 수"), ("press", "매체 수"), ("big", "대형 확산"),
            ("per_issue", "이슈당 보도")]
    if len(weeks) >= 5:
        M = np.array([[wd[k] for k, _ in keys] for wd in weeks], dtype=float)
        with np.errstate(invalid="ignore", divide="ignore"):
            cm = np.corrcoef(M, rowvar=False)
        out["corr_matrix"] = {"labels": [l for _, l in keys],
                              "matrix": [[r3(v) for v in row] for row in cm]}
    else:
        out["corr_matrix"] = None

    # ── 요일 효과 ──
    if len(days) >= 14:
        wkd = [x["count"] for x in days if x["weekday"] < 5]
        wke = [x["count"] for x in days if x["weekday"] >= 5]
        mw = st.mannwhitneyu(wkd, wke, alternative="two-sided")
        n1, n2 = len(wkd), len(wke)
        mu = n1 * n2 / 2
        sigma = math.sqrt(n1 * n2 * (n1 + n2 + 1) / 12)
        z = (mw.statistic - mu) / sigma if sigma else 0
        groups = [[x["count"] for x in days if x["weekday"] == k] for k in range(7)]
        kw = st.kruskal(*groups)
        out["weekday"] = {
            "weekday_mean": r3(np.mean(wkd), 2), "weekend_mean": r3(np.mean(wke), 2),
            "U": r3(mw.statistic, 1), "p": p3(mw.pvalue), "effect_r": r3(abs(z) / math.sqrt(n1 + n2)),
            "kw_H": r3(kw.statistic, 2), "kw_p": p3(kw.pvalue),
            "by_day": [{"day": WEEKDAYS[k], "mean": r3(np.mean(g), 2) if g else 0, "n": len(g)}
                       for k, g in enumerate(groups)],
        }
    else:
        out["weekday"] = None

    # ── 주제별 확산력(이슈당 매체 수) ──
    by_topic = defaultdict(list)
    for c in clus:
        by_topic[c["topic"]].append(c["press_cnt"])
    eligible = {t: v for t, v in by_topic.items() if len(v) >= 20}
    spread = {"topics": [{"topic": t, "issues": len(v), "mean_press": r3(np.mean(v), 2),
                          "median_press": r3(np.median(v), 2),
                          "big_share": r3(sum(1 for x in v if x >= config.BIG_ISSUE_PRESS) / len(v))}
                         for t, v in sorted(by_topic.items(), key=lambda kv: -np.mean(kv[1]))]}
    if len(eligible) >= 2:
        kw = st.kruskal(*eligible.values())
        n = sum(len(v) for v in eligible.values())
        spread.update({"kw_H": r3(kw.statistic, 2), "p": p3(kw.pvalue),
                       "epsilon2": r3(kw.statistic / (n - 1)), "n_topics": len(eligible), "n": n})
    out["topic_spread"] = spread

    # ── 주제 구성 변화(주제×월) ──
    months = sorted({d.strftime("%Y-%m") for d in dates})
    topics = config.TOPIC_ORDER
    table = np.zeros((len(topics), len(months)))
    for a, d in zip(arts, dates):
        ti = topics.index(a["topic"]) if a["topic"] in topics else len(topics) - 1
        table[ti, months.index(d.strftime("%Y-%m"))] += 1
    tm = {"months": months, "topics": topics, "counts": table.astype(int).tolist()}
    keep_r = table.sum(1) > 0
    keep_c = table.sum(0) > 0
    t2 = table[keep_r][:, keep_c]
    if t2.shape[0] >= 2 and t2.shape[1] >= 2:
        chi = st.chi2_contingency(t2)
        n = t2.sum()
        v = math.sqrt(chi.statistic / (n * (min(t2.shape) - 1)))
        tm.update({"chi2": r3(chi.statistic, 2), "dof": int(chi.dof), "p": p3(chi.pvalue), "cramers_v": r3(v)})
    out["topic_month"] = tm

    # ── 홍보비 연계 ──
    out["budget"] = budget_analysis(arts, dates)

    # ── 데이터 한계 ──
    lim = ["수집은 포털 검색 API 결과에 의존하므로, 검색어에 걸리지 않는 기사와 지면 기사는 누락될 수 있음(수집 편향)."]
    if len(weeks) >= 5:
        y1 = y[:-1] - y.mean()
        y2 = y[1:] - y.mean()
        ac = float((y1 * y2).sum() / ((y - y.mean()) ** 2).sum()) if y.std() else 0
        out["descriptive"]["autocorr_lag1"] = r3(ac)
        if abs(ac) >= 0.3:
            lim.append(f"주간 보도량에 자기상관(lag1 = {ac:.2f})이 있어 p값이 과소 추정될 수 있음.")
    lim.append("상관관계는 인과관계를 의미하지 않음. 보도량 변화는 홍보 외 사건·계절 요인의 영향을 받음.")
    views_known = sum(1 for a in arts if a["views"] is not None)
    rate = views_known / len(arts)
    out["descriptive"]["views_rate"] = r3(rate)
    if rate < 0.5:
        lim.append(f"조회수는 공개 매체 기사 {rate * 100:.1f}%에서만 확인되어 전체 도달 규모를 대표하지 못함.")
    if len(weeks) < 12:
        lim.append(f"분석 기간이 {len(weeks)}주로 짧아 통계 결과의 안정성이 낮음.")
    out["limitations"] = lim
    return out


def budget_analysis(arts, dates):
    if not config.BUDGET_CSV.exists():
        return {"available": False}
    budget = {}
    with open(config.BUDGET_CSV, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            try:
                budget[row["month"].strip()[:7]] = float(row["amount"])
            except Exception:
                continue
    monthly = Counter(d.strftime("%Y-%m") for d in dates)
    months = sorted(m for m in budget if m in monthly)
    res = {"available": True, "months": len(months),
           "rows": [{"month": m, "amount": budget[m], "articles": monthly[m],
                     "cost_per_article": round(budget[m] / monthly[m]) if monthly[m] else None} for m in months]}
    if len(months) >= 4:
        xs = [budget[m] for m in months]
        ys = [monthly[m] for m in months]
        if np.std(xs) and np.std(ys):
            pr = st.pearsonr(xs, ys)
            sp = st.spearmanr(xs, ys)
            res.update({"r": r3(pr.statistic), "p": p3(pr.pvalue), "rho": r3(sp.statistic),
                        "ci95": fisher_ci(float(pr.statistic), len(months))})
    if len(months) < 12:
        res["caution"] = f"표본이 {len(months)}개월로 적어 결론을 유보함."
    return res
