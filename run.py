"""아산시 홍보 사업 성과 분석 시스템 — 명령어

사용법:
  python run.py daily              매일 실행: 수집 → (뉴스토어) → 원문 확인 → 이슈 통합 → 보고서(AI) → data.js
  python run.py collect            네이버 API HUB 뉴스 수집
  python run.py newstore [시작 끝]  뉴스토어(빅카인즈) API 기간 수집 (예: 2026-01-01 2026-03-31)
  python run.py bigkinds 파일.xlsx  빅카인즈 엑셀 가져오기
  python run.py cluster            유사 제목 → 이슈 통합
  python run.py views              원문 페이지에서 매체명·조회수 확인
  python run.py build              통계(직전 AI 해석 재사용) + data.js 생성
  python run.py report             통계 + AI 해석(Gemini) + data.js 생성
  python run.py sample [일수]       키 없이 화면 확인용 샘플 데이터 생성 → data.js
"""
import sys

from asannews import config, db


def main(argv):
    if len(argv) < 2 or argv[1] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    cmd, args = argv[1], argv[2:]

    if cmd == "sample":
        from asannews import cluster, export, report, sample
        sample.build(days=int(args[0]) if args else None)
        db.use(config.SAMPLE_DB_PATH)
        cluster.run()
        rep = report.build(use_ai=False)
        export.export(rep, sample=True)
        print("샘플 화면: python -m http.server 8765 --directory dashboard → http://localhost:8765")
    elif cmd == "collect":
        from asannews import collect
        collect.collect()
    elif cmd == "newstore":
        from asannews import newstore
        newstore.collect_period(*args[:2])
    elif cmd == "bigkinds":
        if not args:
            print("사용법: python run.py bigkinds 파일.xlsx")
            return 1
        from asannews import bigkinds
        bigkinds.import_xlsx(args[0])
    elif cmd == "cluster":
        from asannews import cluster
        cluster.run()
    elif cmd == "views":
        from asannews import views
        views.run()
    elif cmd in ("build", "report"):
        from asannews import export, report
        rep = report.build(use_ai=(cmd == "report"))
        export.export(rep)
    elif cmd == "daily":
        from asannews import cluster, collect, export, newstore, report, views
        collect.collect()
        steps = [("뉴스토어", newstore.recent), ("원문 확인", views.run)]
        for name, fn in steps:          # 선택 단계는 실패해도 계속
            try:
                fn()
            except Exception as e:
                print(f"{name} 단계 실패(계속 진행): {e}")
        cluster.run()
        rep = report.build(use_ai=True)
        export.export(rep)
    else:
        print(f"알 수 없는 명령: {cmd}\n{__doc__}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
