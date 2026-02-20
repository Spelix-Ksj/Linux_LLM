"""
Step 4: Oracle DB 연결 테스트 및 스키마 확인 스크립트
실행: python db_setup.py
"""
import oracledb
from sqlalchemy import create_engine, inspect, text
from config import DB_CONFIG, TARGET_TABLES


def get_engine():
    """SQLAlchemy 엔진 생성"""
    return create_engine(
        "oracle+oracledb://",
        connect_args=DB_CONFIG,
        pool_size=5,
        max_overflow=10,
        pool_recycle=3600,
        pool_pre_ping=True,
        pool_timeout=30,
    )


def test_connection(engine):
    """DB 연결 테스트"""
    print("=" * 50)
    print(" Oracle DB 연결 테스트")
    print("=" * 50)
    print(f"  Host: {DB_CONFIG['host']}:{DB_CONFIG['port']}")
    print(f"  SID:  {DB_CONFIG['sid']}")
    print(f"  User: {DB_CONFIG['user']}")
    print()

    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1 FROM dual"))
        print(f"  연결 성공: {result.fetchone()}")

        # DB 버전 확인
        ver = conn.execute(text("SELECT banner FROM v$version WHERE ROWNUM = 1"))
        row = ver.fetchone()
        if row:
            print(f"  DB 버전: {row[0]}")
    print()


def show_schema(engine):
    """대상 테이블 스키마 조회"""
    print("=" * 50)
    print(" 대상 테이블 스키마")
    print("=" * 50)

    inspector = inspect(engine)
    schema = DB_CONFIG["user"]

    # 사용 가능한 테이블 목록 확인
    available_tables = inspector.get_table_names(schema=schema)
    print(f"\n  스키마 '{schema}'의 전체 테이블 수: {len(available_tables)}")

    for table_name in TARGET_TABLES:
        print(f"\n  === {table_name} ===")
        try:
            columns = inspector.get_columns(table_name, schema=schema)
            if not columns:
                print(f"    (테이블을 찾을 수 없음)")
                continue
            for col in columns:
                nullable = "NULL" if col.get("nullable", True) else "NOT NULL"
                print(f"    {col['name']:30s} {str(col['type']):20s} {nullable}")
        except Exception as e:
            print(f"    오류: {e}")

    print()

    # 대상 테이블 외 다른 테이블도 표시 (참고용)
    other_tables = [t for t in available_tables if t.lower() not in [x.lower() for x in TARGET_TABLES]]
    if other_tables:
        print(f"  기타 테이블 ({len(other_tables)}개):")
        for t in sorted(other_tables)[:20]:
            print(f"    - {t}")
        if len(other_tables) > 20:
            print(f"    ... 외 {len(other_tables) - 20}개")
    print()


def show_sample_data(engine):
    """각 테이블의 샘플 데이터 조회"""
    print("=" * 50)
    print(" 샘플 데이터 (각 테이블 상위 3행)")
    print("=" * 50)

    schema = DB_CONFIG["user"]

    with engine.connect() as conn:
        for table_name in TARGET_TABLES:
            print(f"\n  === {table_name} ===")
            try:
                result = conn.execute(
                    text(f'SELECT * FROM "{schema}"."{table_name}" WHERE ROWNUM <= 3')
                )
                rows = result.fetchall()
                cols = result.keys()
                print(f"    컬럼: {', '.join(cols)}")
                for i, row in enumerate(rows, 1):
                    print(f"    [{i}] {dict(zip(cols, row))}")
                if not rows:
                    print("    (데이터 없음)")
            except Exception as e:
                # 대소문자 이슈 - 소문자로도 시도
                try:
                    result = conn.execute(
                        text(f"SELECT * FROM {schema}.{table_name} WHERE ROWNUM <= 3")
                    )
                    rows = result.fetchall()
                    cols = result.keys()
                    print(f"    컬럼: {', '.join(cols)}")
                    for i, row in enumerate(rows, 1):
                        print(f"    [{i}] {dict(zip(cols, row))}")
                    if not rows:
                        print("    (데이터 없음)")
                except Exception as e2:
                    print(f"    오류: {e2}")
    print()


if __name__ == "__main__":
    engine = get_engine()
    test_connection(engine)
    show_schema(engine)
    show_sample_data(engine)
