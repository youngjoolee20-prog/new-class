"""지역 설정값 — 다른 지역으로 바꿀 때는 이 파일만 수정합니다."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DASHBOARD_DIR = ROOT / "dashboard"
DB_PATH = DATA_DIR / "asan_news.db"
SAMPLE_DB_PATH = DATA_DIR / "sample.db"
REPORT_JSON = DATA_DIR / "report.json"
BUDGET_CSV = DATA_DIR / "budget.csv"
DATA_JS = DASHBOARD_DIR / "data.js"


def load_env(path=ROOT / ".env"):
    """간단한 .env 로더(외부 라이브러리 없이). 이미 설정된 환경변수는 덮어쓰지 않음."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and v and k not in os.environ:
            os.environ[k] = v


load_env()

# ── 지역 ─────────────────────────────────────────────
REGION = "아산시"
REGION_SHORT = "아산"
UPPER_REGION = "충청남도"
START_DATE = "2026-01-01"
SYSTEM_NAME = f"{REGION} 홍보 사업 성과 분석 시스템"
OPERATOR = "사단법인 도시공동체본부"
MAKER = "YILOWOON"
BRAND_COLORS = {"blue": "#1d4f9c", "orange": "#e8891a", "green": "#2f8a3b"}
REPO = os.environ.get("GITHUB_REPO", "계정명/저장소명")
UPDATE_TIME_LABEL = "오전 8시"

# ── 수집 ─────────────────────────────────────────────
QUERIES = [
    "아산시", "아산시장", "아산시의회", "아산시청", "아산 온양온천",
    "아산 배방", "아산 탕정", "아산 이순신축제", "아산 곡교천", "아산 신정호",
]
LOCAL_WORDS = [
    "온양", "배방", "탕정", "음봉", "둔포", "곡교천", "신정호",
    "외암마을", "현충사", "이순신축제",
]
EXCLUDE_WORDS = ["서울아산병원", "현대아산", "아산나눔재단", "아산정책연구원"]

# ── 주제 분류 키워드 ──────────────────────────────────
TOPICS = {
    "행정·시정": ["시정", "행정", "시장", "공무원", "조직", "예산", "민원", "시청", "정책", "업무협약", "협약"],
    "경제·산업·일자리": ["경제", "산업", "기업", "일자리", "고용", "투자", "산단", "산업단지", "소상공인", "창업", "디스플레이", "반도체", "수출"],
    "관광·문화·축제": ["관광", "축제", "문화", "공연", "전시", "온천", "여행", "외암마을", "현충사", "이순신", "예술"],
    "복지·보건": ["복지", "보건", "건강", "의료", "돌봄", "어르신", "노인", "장애인", "취약계층", "기부", "나눔"],
    "교육·청년": ["교육", "학교", "학생", "청년", "대학", "장학", "아동", "청소년", "평생학습"],
    "도시·교통·개발": ["도시", "교통", "개발", "도로", "철도", "주택", "아파트", "재생", "버스", "택지", "도시계획"],
    "환경·안전": ["환경", "안전", "재난", "소방", "기후", "탄소", "미세먼지", "하천", "폭염", "방역", "사고"],
    "의회·정치": ["의회", "의원", "의장", "선거", "정당", "국회", "도의원", "시의원", "조례"],
    "체육": ["체육", "스포츠", "축구", "야구", "마라톤", "선수", "대회", "체전", "FC"],
}
OTHER_TOPIC = "기타"
TOPIC_ORDER = list(TOPICS) + [OTHER_TOPIC]

# ── 임계값 ───────────────────────────────────────────
CLUSTER_SIM = 0.45        # 자카드 유사도
CLUSTER_WINDOW_DAYS = 3   # 비교 범위
CLUSTER_MAX_SPAN = 7      # 이슈 최대 기간
BIG_ISSUE_PRESS = 5       # 대형 확산 이슈 기준(매체 수)
VIEWS_RECHECK_DAYS = 14
VIEWS_THREADS = 6
VIEWS_TIMEOUT = 12
# 조회수 표기를 검증한 도메인만 조회수로 인정
VIEWS_TRUSTED_DOMAINS = {
    "newsis.com", "news1.kr", "dt.co.kr", "joongdo.co.kr", "daejonilbo.com",
    "ccdailynews.com", "cctoday.co.kr", "ggilbo.com", "asan.go.kr",
}

# ── 매체 사전(도메인 → 매체명) ─────────────────────────
PRESS_BY_DOMAIN = {
    "yna.co.kr": "연합뉴스", "newsis.com": "뉴시스", "news1.kr": "뉴스1",
    "chosun.com": "조선일보", "joongang.co.kr": "중앙일보", "donga.com": "동아일보",
    "hani.co.kr": "한겨레", "khan.co.kr": "경향신문", "hankookilbo.com": "한국일보",
    "mk.co.kr": "매일경제", "hankyung.com": "한국경제", "sedaily.com": "서울경제",
    "edaily.co.kr": "이데일리", "mt.co.kr": "머니투데이", "fnnews.com": "파이낸셜뉴스",
    "asiae.co.kr": "아시아경제", "heraldcorp.com": "헤럴드경제", "dt.co.kr": "디지털타임스",
    "kbs.co.kr": "KBS", "imbc.com": "MBC", "sbs.co.kr": "SBS", "ytn.co.kr": "YTN",
    "nocutnews.co.kr": "노컷뉴스", "ohmynews.com": "오마이뉴스", "newspim.com": "뉴스핌",
    "joongdo.co.kr": "중도일보", "daejonilbo.com": "대전일보", "cctoday.co.kr": "충청투데이",
    "ccdailynews.com": "충청일보", "ggilbo.com": "금강일보", "tjb.co.kr": "TJB대전방송",
    "dynews.co.kr": "동양일보", "korea.kr": "정책브리핑",
}

# ── API ─────────────────────────────────────────────
NAVER_URL = "https://naverapihub.apigw.ntruss.com/search/v1/news"
NEWSTORE_URL = "https://tools.kinds.or.kr/search/news"
GEMINI_BASE_URL = os.environ.get("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com").rstrip("/")
GEMINI_TEXT_MODEL = os.environ.get("GEMINI_TEXT_MODEL", "gemini-2.5-flash")
