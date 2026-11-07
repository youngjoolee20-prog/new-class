"""빅카인즈 웹에서 내려받은 엑셀(.xlsx) 가져오기."""
import json
from datetime import datetime
from pathlib import Path

from . import collect as naver, db


def import_xlsx(path):
    from openpyxl import load_workbook

    path = Path(path)
    if not path.exists():
        raise SystemExit(f"파일이 없습니다: {path}")
    ws = load_workbook(path, read_only=True).active
    rows = ws.iter_rows(values_only=True)
    header = [str(h or "").strip() for h in next(rows)]

    def col(*names):
        for n in names:
            if n in header:
                return header.index(n)
        return None

    i_date, i_press = col("일자"), col("언론사")
    i_title, i_body, i_url = col("제목"), col("본문"), col("URL", "url")
    if None in (i_date, i_title):
        raise SystemExit("빅카인즈 엑셀 형식이 아닙니다(일자·제목 열 필요).")
    con = db.connect()
    new = 0
    for r in rows:
        try:
            dt = datetime.strptime(str(r[i_date])[:8], "%Y%m%d")
        except Exception:
            continue
        url = (r[i_url] if i_url is not None else None) or f"bigkinds://{r[i_date]}/{r[i_title]}"
        if naver.save_article(con, url=url, title=r[i_title], desc=(r[i_body] or "")[:300] if i_body is not None else "",
                              pub_dt=dt, source="bigkinds", query="bigkinds",
                              press=r[i_press] if i_press is not None else None):
            new += 1
    con.commit()
    db.log_run(con, "bigkinds", json.dumps({"file": path.name, "new": new}, ensure_ascii=False))
    print(f"빅카인즈 가져오기 완료: 신규 {new}건")
    con.close()
    return new
