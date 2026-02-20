"""
Step 5: LangChain Text2SQL 파이프라인
자연어 질문을 Oracle SQL로 변환하고 실행하는 핵심 모듈
"""
import re
import logging
import threading
import pandas as pd
from sqlalchemy import text
from langchain_openai import ChatOpenAI
from langchain_community.utilities import SQLDatabase
from langchain_core.messages import HumanMessage, SystemMessage

from config import DB_CONFIG, TARGET_TABLES, DEFAULT_MODEL_KEY
from model_registry import get_model_config
from db_setup import get_engine

logger = logging.getLogger(__name__)


# ===== 1. 데이터베이스 연결 =====
engine = get_engine()

# SQLDatabase 인스턴스 (LangChain이 스키마 정보를 자동으로 가져옴)
db = SQLDatabase(
    engine=engine,
    schema=DB_CONFIG["user"],
    include_tables=TARGET_TABLES,
    sample_rows_in_table_info=3,
)

# 테이블 정보 캐싱
_table_info = db.get_table_info()

# ===== 2. LLM 인스턴스 캐시 (다중 모델 지원) =====
_llm_cache = {}
_report_llm_cache = {}
_cache_lock = threading.Lock()


def get_llm(model_key=None):
    """model_key에 따른 ChatOpenAI 인스턴스를 생성/캐싱하여 반환 (thread-safe)"""
    if model_key is None:
        model_key = DEFAULT_MODEL_KEY
    with _cache_lock:
        if model_key in _llm_cache:
            return _llm_cache[model_key]
        config = get_model_config(model_key)
        new_llm = ChatOpenAI(
            model=config["model_name"],
            base_url=config["base_url"],
            api_key="not-needed",
            temperature=0.0,
            max_tokens=config["max_tokens"],
            timeout=60,
        )
        _llm_cache[model_key] = new_llm
        return new_llm


def get_report_llm(model_key=None):
    """model_key에 따른 보고서용 ChatOpenAI 인스턴스를 생성/캐싱하여 반환 (thread-safe)"""
    if model_key is None:
        model_key = DEFAULT_MODEL_KEY
    with _cache_lock:
        if model_key in _report_llm_cache:
            return _report_llm_cache[model_key]
        config = get_model_config(model_key)
        # 보고서용은 1024가 기본이나, 모델 max_tokens가 더 작으면 그에 맞춤
        report_max_tokens = min(1024, config["max_tokens"])
        new_llm = ChatOpenAI(
            model=config["model_name"],
            base_url=config["base_url"],
            api_key="not-needed",
            temperature=0.0,
            max_tokens=report_max_tokens,
            timeout=30,
        )
        _report_llm_cache[model_key] = new_llm
        return new_llm

# ===== 3. 시스템 프롬프트 =====
SYSTEM_PROMPT = f"""당신은 Oracle SQL 전문가입니다.
사용자의 질문을 Oracle SQL SELECT 문으로 변환하세요.

## 테이블 스키마 정보
{_table_info}

## 테이블 설명
- move_item_master: 인사이동 대상 직원 마스터 (emp_nm=이름, pos_grd_nm=직급, org_nm=현재조직, lvl1~5_nm=조직계층, job_type1/2=직종, gender_nm=성별, year_desc=연령대, org_work_mon=조직근무개월, region_type=지역구분)
- move_case_item: 인사이동 배치안 상세 (new_lvl1~5_nm=새조직계층, must_stay_yn=잔류필수, must_move_yn=이동필수)
- move_case_cnst_master: 인사이동 제약조건 (cnst_nm=제약조건명, cnst_val=제약값, penalty_val=위반패널티)
- move_org_master: 조직 마스터 (org_nm=조직명, org_type=조직유형, tot_to=정원, region_type=지역구분, job_type1/2=직종)

## 규칙
1. Oracle SQL 문법만 사용
2. SELECT 문만 생성 (INSERT/UPDATE/DELETE/DROP 절대 금지)
3. SQL 끝에 세미콜론(;) 붙이지 않기
4. LIMIT 대신 ROWNUM 또는 FETCH FIRST N ROWS ONLY 사용
5. 스키마 접두사 HRAI_CON. 을 테이블명 앞에 붙이기
6. SQL만 출력하세요. 설명은 생략하세요.
7. 출력 컬럼에 한글 별칭(AS "한글명")을 붙이세요 (테이블 설명의 한글명 참조, SELECT *는 별칭 불필요). 예: COUNT(*) AS "인원수", org_nm AS "부서명"
8. 질문이 여러 테이블의 정보를 필요로 하면 적절한 JOIN을 사용하세요. 예: 직원+조직 → HRAI_CON.move_item_master m JOIN HRAI_CON.move_org_master o ON m.org_nm = o.org_nm
9. 단일 테이블로 충분하면 JOIN하지 마세요 (예: 직급별 인원수는 move_item_master만). 다른 테이블의 고유 컬럼이 필요할 때만 JOIN하세요."""


def _clean_sql(raw_sql: str) -> str:
    """LLM이 생성한 SQL에서 불필요한 텍스트를 정리"""
    sql = raw_sql.strip()

    # ```sql ... ``` 블록 추출
    match = re.search(r"```sql\s*(.*?)\s*```", sql, re.DOTALL | re.IGNORECASE)
    if match:
        sql = match.group(1).strip()

    # ``` ... ``` 블록 추출 (언어 지정 없는 경우)
    match = re.search(r"```\s*(.*?)\s*```", sql, re.DOTALL)
    if match and "SELECT" in match.group(1).upper():
        sql = match.group(1).strip()

    # 마지막 세미콜론 제거
    sql = sql.rstrip(";").strip()

    # SELECT/WITH로 시작하는 부분만 추출 (앞의 설명 텍스트 제거)
    select_match = re.search(r"((?:WITH|SELECT)\s.+)", sql, re.DOTALL | re.IGNORECASE)
    if select_match:
        sql = select_match.group(1).strip()

    # 후행 설명 텍스트 제거 (SQL 뒤에 붙은 텍스트)
    # SQL이 끝나는 지점 찾기: 마지막 괄호, 컬럼명, 숫자 뒤
    sql = sql.rstrip(";").strip()

    return sql


def _strip_sql_comments(sql: str) -> str:
    """SQL 주석을 제거하여 키워드 오탐 방지"""
    sql = re.sub(r'--[^\n]*', '', sql)
    sql = re.sub(r'/\*.*?\*/', '', sql, flags=re.DOTALL)
    return sql.strip()


def _is_safe_sql(sql: str) -> bool:
    """SQL이 안전한 SELECT 문인지 검증"""
    # 주석 제거 후 검사 (주석 내 키워드 오탐 방지)
    stripped = _strip_sql_comments(sql)
    upper = stripped.upper().strip()
    # Multi-statement 차단
    if ';' in stripped:
        return False
    # SQL 전체에서 위험한 키워드 검사 (서브쿼리 포함)
    dangerous = ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE", "MERGE", "EXEC", "EXECUTE", "GRANT", "REVOKE", "CALL", "COMMENT", "RENAME"]
    for keyword in dangerous:
        if re.search(rf'\b{keyword}\b', upper):
            return False
    return upper.startswith("SELECT") or upper.startswith("WITH")


REPORT_PROMPT = """당신은 데이터 분석 보고서 작성 전문가입니다.
주어진 SQL 쿼리와 실행 결과를 바탕으로, 비전문가도 이해할 수 있는 한국어 결과 보고서를 작성하세요.

보고서 형식:
1. **데이터 요약**: 조회된 데이터의 핵심 내용을 2-3문장으로 요약
2. **주요 수치**: 눈에 띄는 수치나 패턴 (최대값, 최소값, 평균 등)
3. **인사이트**: 데이터에서 읽을 수 있는 의미나 시사점

규칙:
- 한국어로 작성
- 간결하고 명확하게
- 숫자는 구체적으로 인용
- 마크다운 형식 사용"""


def generate_report(question: str, sql: str, df: pd.DataFrame, reasoning: str = "", model_key: str = None) -> str:
    """SQL 실행 결과를 분석하여 자연어 보고서를 생성"""
    if df.empty:
        return ""

    # 1. SQL에서 테이블명 추출
    tables_used = list(dict.fromkeys(re.findall(r'HRAI_CON\.(\w+)', sql, re.IGNORECASE)))

    # 2. 결과 요약 정보 (LLM 컨텍스트 초과 방지를 위해 크기 제한)
    result_preview = df.head(20).to_string(index=False)
    if len(result_preview) > 3000:
        result_preview = df.head(5).to_string(index=False)
    if len(result_preview) > 3000:
        result_preview = result_preview[:3000]
    columns_str = ", ".join(df.columns.tolist())

    # 3. 2차 LLM 호출로 결과 요약 생성 (프롬프트 인젝션 방지: 입력 길이 제한 + 구분자)
    safe_question = question[:500]
    user_prompt = f"""## 원래 질문
<user_input>{safe_question}</user_input>

## 실행된 SQL
{sql}

## 조회 결과 ({len(df)}건, 컬럼: {columns_str})
{result_preview}

위 내용을 바탕으로 결과 보고서를 작성하세요."""

    try:
        messages = [
            SystemMessage(content=REPORT_PROMPT),
            HumanMessage(content=user_prompt),
        ]
        active_report_llm = get_report_llm(model_key)
        resp = active_report_llm.invoke(messages)
        llm_summary = resp.content.strip()
    except Exception as e:
        logger.error(f"Report generation failed: {e}")
        llm_summary = "(보고서 생성 중 오류가 발생했습니다)"

    # 4. 최종 보고서 조립
    report_parts = []
    report_parts.append("## SQL 분석\n")
    report_parts.append(f"- **사용된 테이블**: {', '.join(tables_used) if tables_used else '(파싱 불가)'}")
    report_parts.append(f"- **조회 건수**: {len(df)}건")
    report_parts.append(f"- **결과 컬럼**: {columns_str}\n")

    if reasoning:
        display_reasoning = reasoning[:1000] + "..." if len(reasoning) > 1000 else reasoning
        report_parts.append(f"<details><summary>LLM 추론 과정 (펼치기)</summary>\n\n{display_reasoning}\n\n</details>\n")

    report_parts.append("## 결과 요약\n")
    report_parts.append(llm_summary)

    return "\n".join(report_parts)


def ask_hr(question: str, model_key: str = None) -> dict:
    """
    자연어 질문을 SQL로 변환하고 실행

    Args:
        question: 자연어 질문 (예: "직급별 인원 수를 구해줘")
        model_key: 사용할 모델 키 (None이면 DEFAULT_MODEL_KEY 사용)

    Returns:
        dict with keys: question, sql, result (DataFrame), error (str or None)
    """
    error = None
    generated_sql = ""
    reasoning = ""
    df = pd.DataFrame()

    # 1단계: LLM 호출 (SQL 생성)
    try:
        active_llm = get_llm(model_key)
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=question),
        ]
        response = active_llm.invoke(messages)

        # reasoning model의 사고과정 캡처
        if hasattr(response, "additional_kwargs"):
            reasoning = response.additional_kwargs.get("reasoning_content", "")
        if not reasoning and hasattr(response, "response_metadata"):
            reasoning = response.response_metadata.get("reasoning_content", "")

        raw_sql = response.content
        generated_sql = _clean_sql(raw_sql)
    except Exception as e:
        logger.error(f"LLM invocation failed: {e}")
        return {
            "question": question,
            "sql": "",
            "result": pd.DataFrame(),
            "error": "LLM 서버 연결에 실패했습니다. 잠시 후 다시 시도해 주세요.",
            "reasoning": reasoning,
        }

    # 빈 응답 체크
    if not generated_sql:
        return {
            "question": question,
            "sql": f"(raw response: {raw_sql[:500]})",
            "result": pd.DataFrame(),
            "error": "LLM이 SQL을 생성하지 못했습니다.",
            "reasoning": reasoning,
        }

    # 안전성 검사
    if not _is_safe_sql(generated_sql):
        return {
            "question": question,
            "sql": generated_sql,
            "result": pd.DataFrame(),
            "error": "안전하지 않은 SQL이 감지되었습니다. SELECT 문만 허용됩니다.",
            "reasoning": reasoning,
        }

    # 2단계: SQL 실행 (최대 1000행 제한 + 30초 타임아웃)
    try:
        safe_sql = f"SELECT * FROM ({generated_sql}) WHERE ROWNUM <= 1000"
        with engine.connect() as conn:
            conn.connection.dbapi_connection.call_timeout = 30000
            df = pd.read_sql(text(safe_sql), conn)
    except Exception as e:
        logger.error(f"SQL execution failed: {e}")
        error = "SQL 실행 중 오류가 발생했습니다. 질문을 다시 작성해 주세요."

    return {
        "question": question,
        "sql": generated_sql,
        "result": df,
        "error": error,
        "reasoning": reasoning,
    }


if __name__ == "__main__":
    # 간단한 테스트
    test_q = "move_item_master 테이블의 직급별(pos_grd_nm) 인원 수를 구해줘"
    print(f"질문: {test_q}")
    result = ask_hr(test_q)
    print(f"SQL:\n{result['sql']}")
    if result["error"]:
        print(f"오류: {result['error']}")
    else:
        print(f"결과:\n{result['result']}")
