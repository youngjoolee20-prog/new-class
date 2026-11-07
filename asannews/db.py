"""SQLite 스키마와 연결."""
import sqlite3
from datetime import datetime

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  url TEXT UNIQUE NOT NULL,
  naver_link TEXT,
  title TEXT NOT NULL,
  description TEXT,
  pub_date TEXT NOT NULL,          -- YYYY-MM-DD
  pub_datetime TEXT,
  press TEXT,
  domain TEXT,
  source TEXT NOT NULL,            -- naver|newstore|bigkinds|sample
  query TEXT,
  topic TEXT,
  cluster_id INTEGER,
  views INTEGER,
  views_checked TEXT,
  views_status TEXT,
  collected_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_articles_date ON articles(pub_date);
CREATE INDEX IF NOT EXISTS idx_articles_cluster ON articles(cluster_id);
CREATE INDEX IF NOT EXISTS idx_articles_press ON articles(press);
CREATE TABLE IF NOT EXISTS clusters (
  id INTEGER PRIMARY KEY,
  title TEXT,
  first_date TEXT,
  last_date TEXT,
  article_cnt INTEGER,
  press_cnt INTEGER,
  views_sum INTEGER,
  topic TEXT
);
CREATE INDEX IF NOT EXISTS idx_clusters_first ON clusters(first_date);
CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  step TEXT,
  started TEXT,
  detail TEXT
);
"""

_db_path = config.DB_PATH


def use(path):
    """사용할 DB 파일 지정(샘플 모드 등)."""
    global _db_path
    _db_path = path


def current_path():
    return _db_path


def connect(path=None):
    p = path or _db_path
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(p)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def log_run(con, step, detail):
    con.execute(
        "INSERT INTO runs(step, started, detail) VALUES (?,?,?)",
        (step, datetime.now().isoformat(timespec="seconds"), str(detail)),
    )
    con.commit()
