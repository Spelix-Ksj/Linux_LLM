"""
Step 7: 통합 테스트 스크립트
DB 연결, SQL 생성, 실행을 단계별로 검증
실행: python test_e2e.py
"""
import sys


def test_db_connection():
    """1단계: DB 연결 테스트"""
    print("=" * 50)
    print("[1/4] Oracle DB 연결 테스트")
    print("=" * 50)
    from db_setup import get_engine
    from sqlalchemy import text

    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1 FROM dual"))
        assert result.fetchone() is not None
    print("  PASS: DB 연결 성공\n")
    return engine


def test_vllm_connection():
    """2단계: vLLM 서버 연결 테스트"""
    print("=" * 50)
    print("[2/4] vLLM 서버 연결 테스트")
    print("=" * 50)
    import urllib.request
    import json
    from config import VLLM_BASE_URL

    url = VLLM_BASE_URL.rstrip("/") + "/models"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            models = [m["id"] for m in data.get("data", [])]
            print(f"  사용 가능 모델: {models}")
            assert len(models) > 0
        print("  PASS: vLLM 서버 정상\n")
    except Exception as e:
        print(f"  FAIL: vLLM 서버 연결 실패 - {e}\n")
        sys.exit(1)


def test_sql_generation():
    """3단계: SQL 생성 테스트"""
    print("=" * 50)
    print("[3/4] SQL 생성 테스트")
    print("=" * 50)
    from text2sql_pipeline import ask_hr

    question = "전체 테이블의 행 수를 각각 알려줘"
    result = ask_hr(question)

    print(f"  질문: {result['question']}")
    print(f"  생성된 SQL:\n    {result['sql']}")

    if result["error"]:
        print(f"  오류: {result['error']}")
        print("  FAIL: SQL 생성/실행 실패\n")
        return False

    print(f"  결과 행 수: {len(result['result'])}")
    print(f"  PASS: SQL 생성 및 실행 성공\n")
    return True


def test_multiple_questions():
    """4단계: 다양한 질문 테스트"""
    print("=" * 50)
    print("[4/4] 다양한 질문 테스트")
    print("=" * 50)
    from text2sql_pipeline import ask_hr

    questions = [
        "직급별 인원 수를 구해줘",
        "평균 나이가 가장 높은 부서는 어디야?",
        "IT 부서에서 대리급 이상의 직원들만 보여줘",
    ]

    passed = 0
    failed = 0

    for q in questions:
        print(f"\n  질문: {q}")
        result = ask_hr(q)
        print(f"  SQL: {result['sql'][:100]}...")

        if result["error"]:
            print(f"  오류: {result['error']}")
            failed += 1
        else:
            print(f"  결과: {len(result['result'])}건")
            print(result["result"].head(3).to_string(index=False))
            passed += 1

    print(f"\n  결과: {passed} 성공 / {failed} 실패\n")


if __name__ == "__main__":
    print("\n" + "=" * 50)
    print(" Text2SQL 통합 테스트")
    print("=" * 50 + "\n")

    test_db_connection()
    test_vllm_connection()
    if test_sql_generation():
        test_multiple_questions()

    print("=" * 50)
    print(" 통합 테스트 완료")
    print("=" * 50)
