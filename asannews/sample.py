"""키 없이 화면을 확인하기 위한 샘플 데이터(data/sample.db). 매체명은 '샘플매체 NN' 형식."""
import random
from datetime import date, datetime, timedelta

from . import config, db

SUBJECTS = {
    "행정·시정": ["아산시, 하반기 시정 주요 업무 보고회 개최", "아산시장, 읍면동 순방 시민과 대화", "아산시 민원 처리 기간 단축 성과",
                "아산시, 조직 개편안 확정", "아산시 2027년 예산안 편성 착수"],
    "경제·산업·일자리": ["아산시, 탕정 디스플레이 기업 투자 협약 체결", "아산시 청년 일자리 박람회 성료", "아산 소상공인 경영 안정 자금 지원",
                     "아산시, 배방 산업단지 입주 기업 모집", "아산시 고용률 충남 상위권 기록"],
    "관광·문화·축제": ["아산 성웅 이순신축제 개막 관람객 몰려", "온양온천 야간 관광 프로그램 운영", "외암마을 전통 체험 행사 인기",
                   "곡교천 은행나무길 가을 축제 준비", "신정호 음악회 시민 호응"],
    "복지·보건": ["아산시, 어르신 돌봄 서비스 확대", "아산시 보건소 무료 건강검진 운영", "아산 취약계층 겨울나기 나눔 행사",
               "아산시 장애인 일자리 지원 강화"],
    "교육·청년": ["아산시 청년 정책 협의체 출범", "아산시 장학금 지원 대상 확대", "아산 학교 밖 청소년 지원 사업 추진"],
    "도시·교통·개발": ["아산 탕정 도시개발 사업 본격화", "아산시 시내버스 노선 개편 시행", "온양 원도심 도시재생 사업 선정",
                   "아산 둔포 도로 확장 공사 착공"],
    "환경·안전": ["아산시 폭염 대비 안전 대책 가동", "곡교천 하천 정비 사업 완료", "아산시 탄소중립 실천 캠페인"],
    "의회·정치": ["아산시의회 임시회 조례안 처리", "아산시의회 행정사무감사 돌입", "아산시의원 지역 현안 간담회"],
    "체육": ["충남아산FC 홈경기 승리", "아산 이순신 마라톤 대회 성료", "아산시 생활체육 대회 개최"],
}
VARIANTS = ["", " …시민 기대", " 눈길", " 추진", " 박차", " 본격화", " 성황", " 화제"]
PREFIXES = ["", "", "", "[포토] ", "(아산=샘플뉴스) ", "[아산] "]


def build(days=None, seed=42):
    rnd = random.Random(seed)
    path = config.SAMPLE_DB_PATH
    if path.exists():
        path.unlink()
    db.use(path)
    con = db.connect()
    start = datetime.strptime(config.START_DATE, "%Y-%m-%d").date()
    end = date.today() - timedelta(days=1)
    if days:
        start = max(start, end - timedelta(days=days))
    presses = [f"샘플매체 {i:02d}" for i in range(1, 41)]
    weights = [1 / (i ** 0.7) for i in range(1, 41)]
    topics = list(SUBJECTS)
    topic_w = [9, 7, 8, 5, 3, 5, 3, 4, 3]
    n = 0
    d = start
    while d <= end:
        weekday = d.weekday()
        trend = 1 + 0.25 * ((d - start).days / max(1, (end - start).days))
        n_issues = rnd.randint(2, 6) if weekday < 5 else rnd.randint(0, 2)
        n_issues = int(round(n_issues * trend))
        for _ in range(n_issues):
            topic = rnd.choices(topics, topic_w)[0]
            base = rnd.choice(SUBJECTS[topic])
            size = max(1, int(rnd.paretovariate(1.3)))
            size = min(size, 18)
            chosen = rnd.sample(presses, k=min(size, len(presses))) if size > 1 else rnd.choices(presses, weights)
            for p in chosen:
                pub = d + timedelta(days=rnd.choice([0, 0, 0, 0, 1, 1, 2]))
                if pub > end:
                    pub = end
                title = rnd.choice(PREFIXES) + base + rnd.choice(VARIANTS)
                n += 1
                url = f"https://sample.example/{d:%Y%m%d}/{n}"
                views = None
                status = "skip"
                if rnd.random() < 0.35:
                    views = int(rnd.lognormvariate(6.2, 1.0))
                    status = "ok"
                dt = datetime(pub.year, pub.month, pub.day, rnd.randint(6, 21), rnd.randint(0, 59))
                con.execute(
                    """INSERT INTO articles (url, naver_link, title, description, pub_date, pub_datetime,
                       press, domain, source, query, topic, views, views_checked, views_status, collected_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (url, url, title, f"{base} 관련 샘플 기사 본문입니다.", pub.isoformat(),
                     dt.isoformat(timespec="seconds"), p, "sample.example", "sample", "sample",
                     topic, views, datetime.now().isoformat(timespec="seconds"), status,
                     datetime.now().isoformat(timespec="seconds")),
                )
        d += timedelta(days=1)
    con.commit()
    db.log_run(con, "sample", f"{n} articles")
    con.close()
    print(f"샘플 데이터 {n}건 생성: {path}")
    return n
