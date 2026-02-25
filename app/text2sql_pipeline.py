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
SYSTEM_PROMPT = f"""당신은 Oracle SQL 전문가이며, HDTP(정기인사 전환배치 최적화) 시스템의 데이터베이스를 깊이 이해하고 있습니다.
사용자의 질문을 Oracle SQL SELECT 문으로 변환하세요.

## 시스템 개요
HDTP는 현대백화점 직원 정기인사이동 배치를 최적화하는 시스템입니다.
- 조직계층: LVL1(본사) → LVL2(권역 A~E) → LVL3(사업소) → LVL4(팀) → LVL5(파트)
  - 권역: A=서울, B=경기/인천, C=광역점, D=아울렛, E=기타
- FTR_MOVE_STD_ID: 이동번호 — 거의 모든 MOVE_* 테이블의 공통 조인 키 (물리적 FK 없음)
- REV_ID: 리비전 ID (VARCHAR2 타입). '999'는 최종 확정 리비전이나, 데이터가 없을 수 있으므로 명시적 요청이 없으면 REV_ID 조건을 생략하세요.

## 테이블 스키마 정보
{_table_info}

## 테이블 설명 (15개 핵심 테이블)
### 이동기준
- ftr_move_std: 이동기준 마스터 (ftr_move_std_id=이동번호 PK, std_nm=이동기준명, std_ym=기준년월, wk_std_ymd=기준일자, close_yn=마감여부)

### 직원 데이터
- move_item_master: 직원 마스터 — 76컬럼 (emp_id=직원ID PK, emp_no=사번, emp_nm=이름, pos_grd_nm=직급, org_nm=현재조직, lvl1~5_nm=조직계층, job_type1/2/3=직종, gender_nm=성별, year_desc=연령대, org_work_mon=조직근무개월, c_area_work_mon=권역근무개월, region_type=지역구분, tot_score=종합점수, married=기혼여부, self_move_yn=자기신청이동)
- move_item_detail: 발령정보 (복합PK: ftr_move_std_id+emp_no+org_type, send_yn=메일발송여부)

### 조직 데이터
- move_org_master: 사업소/조직 마스터 (org_id=조직ID PK, org_nm=조직명, org_cd=조직코드, lvl1~5_nm=조직계층, lvl=조직레벨, tot_to=정원(TO), job_type1/2=직종, region_type=지역구분)
- move_network_change: 사업소변경정보 (chg_id=변경ID, org_id=조직ID, before/after 컬럼으로 변경 전후 비교)

### 케이스 관리
- move_case_master: 배치 케이스 (case_id=케이스ID PK, case_name=케이스명, case_desc=설명)
- move_case_detail: 케이스 상세/리비전 (복합PK: ftr_move_std_id+case_id+case_det_id+rev_id, rev_nm=리비전명, case_det_nm=상세명)
- move_case_item: 배치 결과 — 직원별 (복합PK: ftr_move_std_id+case_id+case_det_id+rev_id+emp_id, new_org_id=새조직ID, new_lvl1~5_nm=새조직계층, new_job_type1/2=새직종, must_stay_yn=잔류필수, must_move_yn=이동필수, fixed_yn=확정여부)
- move_case_org: 조직별 TO 설정 (복합PK: ftr_move_std_id+case_id+case_det_id+rev_id+org_id, tot_to=배치가능인원, org_nm=조직명, lvl=조직레벨). 주의: 잔류/전입/전출 인원 컬럼은 없음 — move_case_item에서 new_org_id 기준 COUNT 집계 필요

### 제약조건 & 감점
- move_case_cnst_master: 제약조건 — 48개 코드 (복합PK: ftr_move_std_id+case_id+case_det_id+rev_id+org_id+cnst_cd, cnst_nm=제약명, cnst_gbn=구분, use_yn=사용여부, cnst_val=제약값, penalty_val=감점값)
  주요 제약: TEAM001=TO초과불가, TEAM002=필수이동, TEAM003=미배치방지, TEAM004/006=징계/부부분리, TEAM007=점수균형±10%, TEAM020=이동비율, TEAM021=남성최소1인, TEAM033/035=이동제한기간
- move_case_penalty_info: 감점 상세 (cnst_id=제약ID, cnst_nm=제약명, penalty_cnt=위반건수, penalty_val=감점값, penalty_sum=감점합계)
- move_jobtype_penalty_matrix: 직무 호환성 매트릭스 (jobtype_prop=직무속성, from/to 직무별 감점)
- move_stay_rule: 필수유보 기준 (move_stay_rule_id=기준ID, org_type=조직유형, job_type=직종, year_cnt_st=시작연차, year_cnt_fi=종료연차, move_stay=유보개월)
- move_emp_exclusion: 동시배치불가 직원 (emp_no1/emp_no2=사번쌍, reason_type=사유유형(부부/징계))

### ML 매핑
- ml_map_dictionary: ML 직무분류 매핑 (dic_id=사전ID, src_val=원본값, tgt_val=매핑값, dic_type=사전유형)

## 주요 JOIN 패턴 (CASE 계열 테이블은 case_id 조건 포함, rev_id는 규칙 11 참고)
- 직원+배치결과: move_item_master m JOIN move_case_item c ON m.ftr_move_std_id=c.ftr_move_std_id AND m.emp_id=c.emp_id
- 배치결과→새조직: move_case_item c JOIN move_org_master o ON c.ftr_move_std_id=o.ftr_move_std_id AND c.new_org_id=o.org_id
- 제약조건+조직: move_case_cnst_master cn JOIN move_org_master o ON cn.ftr_move_std_id=o.ftr_move_std_id AND cn.org_id=o.org_id
- 배치결과+감점: move_case_item ci JOIN move_case_penalty_info p ON ci.ftr_move_std_id=p.ftr_move_std_id AND ci.case_id=p.case_id AND ci.case_det_id=p.case_det_id AND ci.rev_id=p.rev_id
- 케이스 체인: move_case_master cm JOIN move_case_detail cd ON cm.ftr_move_std_id=cd.ftr_move_std_id AND cm.case_id=cd.case_id → move_case_item/move_case_org/move_case_cnst_master (ftr_move_std_id+case_id+case_det_id+rev_id)

## 규칙
1. Oracle SQL 문법만 사용
2. SELECT 문만 생성 (INSERT/UPDATE/DELETE/DROP 절대 금지)
3. SQL 끝에 세미콜론(;) 붙이지 않기
4. LIMIT 대신 ROWNUM 또는 FETCH FIRST N ROWS ONLY 사용
5. 스키마 접두사 HRAI_CON. 을 테이블명 앞에 붙이기
6. SQL만 출력하세요. 설명은 생략하세요.
7. 출력 컬럼에 한글 별칭(AS "한글명")을 붙이세요. 예: COUNT(*) AS "인원수", org_nm AS "부서명"
8. 질문이 여러 테이블의 정보를 필요로 하면 적절한 JOIN을 사용하세요. JOIN 시 반드시 FTR_MOVE_STD_ID 조건을 맞추세요.
9. 단일 테이블로 충분하면 JOIN하지 마세요. 다른 테이블의 고유 컬럼이 필요할 때만 JOIN하세요.
10. 질문에 [이동번호(FTR_MOVE_STD_ID)=NNNNNN 조건 필수]가 포함된 경우, 모든 테이블의 WHERE절에 FTR_MOVE_STD_ID = NNNNNN 조건을 반드시 포함하세요.
11. REV_ID는 VARCHAR2 타입입니다. 사용자가 '최종 확정' 또는 '확정 리비전'을 명시적으로 요청한 경우에만 REV_ID = '999' 조건을 추가하세요. 그 외에는 REV_ID 조건을 생략하세요.
12. 조직 계층 분석 시 LVL1~5_NM 컬럼과 권역 분류(A~E)를 활용하세요.
13. 수치 컬럼으로 정렬(ORDER BY)하거나 집계(SUM/AVG/MAX/MIN)할 때, 해당 컬럼에 NULL이 있을 수 있으므로 WHERE절에 IS NOT NULL 조건을 추가하세요. 예: ORDER BY org_work_mon DESC → WHERE org_work_mon IS NOT NULL ORDER BY org_work_mon DESC

## Few-shot 예시

질문: 직급별 인원 수를 알려줘
SQL:
SELECT pos_grd_nm AS "직급", COUNT(*) AS "인원수"
FROM HRAI_CON.move_item_master
WHERE ftr_move_std_id = (SELECT MAX(ftr_move_std_id) FROM HRAI_CON.ftr_move_std)
GROUP BY pos_grd_nm
ORDER BY COUNT(*) DESC

질문: 근무 기간이 가장 긴 직원 TOP 10을 알려줘
SQL:
SELECT emp_no AS "사번", emp_nm AS "이름", pos_grd_nm AS "직급",
       org_nm AS "소속", org_work_mon AS "조직근무개월"
FROM HRAI_CON.move_item_master
WHERE ftr_move_std_id = (SELECT MAX(ftr_move_std_id) FROM HRAI_CON.ftr_move_std)
  AND org_work_mon IS NOT NULL
ORDER BY org_work_mon DESC
FETCH FIRST 10 ROWS ONLY

질문: 권역별 직원 수를 보여줘
SQL:
SELECT lvl2_nm AS "권역", COUNT(*) AS "인원수"
FROM HRAI_CON.move_item_master
WHERE ftr_move_std_id = (SELECT MAX(ftr_move_std_id) FROM HRAI_CON.ftr_move_std)
GROUP BY lvl2_nm
ORDER BY lvl2_nm

질문: 배치된 직원의 이름과 새 부서를 보여줘
SQL:
SELECT m.emp_nm AS "이름", m.pos_grd_nm AS "직급", m.org_nm AS "현재부서", c.new_lvl3_nm AS "새부서"
FROM HRAI_CON.move_item_master m
JOIN HRAI_CON.move_case_item c ON m.ftr_move_std_id = c.ftr_move_std_id AND m.emp_id = c.emp_id
WHERE c.new_org_id IS NOT NULL
  AND c.case_id = (SELECT MAX(case_id) FROM HRAI_CON.move_case_master WHERE ftr_move_std_id = m.ftr_move_std_id)
  AND m.ftr_move_std_id = (SELECT MAX(ftr_move_std_id) FROM HRAI_CON.ftr_move_std)
FETCH FIRST 50 ROWS ONLY

질문: 사업소별 정원과 현재 배치 인원을 비교해줘
SQL:
SELECT co.org_nm AS "사업소", co.tot_to AS "정원(TO)",
       COUNT(ci.emp_id) AS "배치인원",
       (co.tot_to - COUNT(ci.emp_id)) AS "잔여TO"
FROM HRAI_CON.move_case_org co
LEFT JOIN HRAI_CON.move_case_item ci
    ON co.ftr_move_std_id = ci.ftr_move_std_id AND co.case_id = ci.case_id
    AND co.case_det_id = ci.case_det_id AND co.rev_id = ci.rev_id
    AND co.org_id = ci.new_org_id
WHERE co.ftr_move_std_id = (SELECT MAX(ftr_move_std_id) FROM HRAI_CON.ftr_move_std)
  AND co.case_id = (SELECT MAX(case_id) FROM HRAI_CON.move_case_master WHERE ftr_move_std_id = co.ftr_move_std_id)
GROUP BY co.org_nm, co.tot_to
ORDER BY (co.tot_to - COUNT(ci.emp_id)) DESC

질문: 위반 건수가 많은 제약조건 TOP 10
SQL:
SELECT p.cnst_nm AS "제약조건", SUM(p.penalty_cnt) AS "총위반건수", SUM(p.penalty_sum) AS "총감점"
FROM HRAI_CON.move_case_penalty_info p
WHERE p.case_id = (SELECT MAX(case_id) FROM HRAI_CON.move_case_master WHERE ftr_move_std_id = p.ftr_move_std_id)
  AND p.ftr_move_std_id = (SELECT MAX(ftr_move_std_id) FROM HRAI_CON.ftr_move_std)
GROUP BY p.cnst_nm
ORDER BY SUM(p.penalty_cnt) DESC
FETCH FIRST 10 ROWS ONLY

"""


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


def generate_sql(question: str, model_key: str = None) -> dict:
    """자연어 질문을 SQL로만 변환 (실행하지 않음)

    Args:
        question: 자연어 질문 (예: "직급별 인원 수를 구해줘")
        model_key: 사용할 모델 키 (None이면 DEFAULT_MODEL_KEY 사용)

    Returns:
        dict with keys: sql (str), reasoning (str), error (str or None)
    """
    generated_sql = ""
    reasoning = ""

    # LLM 호출 (SQL 생성)
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
            "sql": "",
            "reasoning": reasoning,
            "error": "LLM 서버 연결에 실패했습니다. 잠시 후 다시 시도해 주세요.",
        }

    # 빈 응답 체크
    if not generated_sql:
        return {
            "sql": "(SQL 파싱 실패)",
            "reasoning": reasoning,
            "error": "LLM이 SQL을 생성하지 못했습니다.",
        }

    # 안전성 검사
    if not _is_safe_sql(generated_sql):
        return {
            "sql": generated_sql,
            "reasoning": reasoning,
            "error": "안전하지 않은 SQL이 감지되었습니다. SELECT 문만 허용됩니다.",
        }

    return {
        "sql": generated_sql,
        "reasoning": reasoning,
        "error": None,
    }


def execute_sql(sql_text: str) -> dict:
    """SQL을 실행하여 결과 반환

    Args:
        sql_text: 실행할 SQL 문

    Returns:
        dict with keys: result (pd.DataFrame), error (str or None)
    """
    # 안전성 재검증 (사용자가 SQL을 편집했을 수 있음)
    if not _is_safe_sql(sql_text):
        return {
            "result": pd.DataFrame(),
            "error": "안전하지 않은 SQL이 감지되었습니다. SELECT 문만 허용됩니다.",
        }

    # SQL 실행 (최대 1000행 제한 + 30초 타임아웃)
    try:
        sql_text = _strip_sql_comments(sql_text)
        safe_sql = f"SELECT * FROM ({sql_text}) WHERE ROWNUM <= 1000"
        with engine.connect() as conn:
            conn.connection.dbapi_connection.call_timeout = 30000
            df = pd.read_sql(text(safe_sql), conn)
    except Exception as e:
        logger.error(f"SQL execution failed: {e}")
        return {
            "result": pd.DataFrame(),
            "error": "SQL 실행 중 오류가 발생했습니다. 질문을 다시 작성해 주세요.",
        }

    return {
        "result": df,
        "error": None,
    }


def ask_hr(question: str, model_key: str = None) -> dict:
    """
    자연어 질문을 SQL로 변환하고 실행 (하위 호환용)

    Args:
        question: 자연어 질문 (예: "직급별 인원 수를 구해줘")
        model_key: 사용할 모델 키 (None이면 DEFAULT_MODEL_KEY 사용)

    Returns:
        dict with keys: question, sql, result (DataFrame), error (str or None), reasoning
    """
    gen_result = generate_sql(question, model_key)
    if gen_result["error"]:
        return {
            "question": question,
            "sql": gen_result["sql"],
            "result": pd.DataFrame(),
            "error": gen_result["error"],
            "reasoning": gen_result["reasoning"],
        }
    exec_result = execute_sql(gen_result["sql"])
    return {
        "question": question,
        "sql": gen_result["sql"],
        "result": exec_result["result"],
        "error": exec_result["error"],
        "reasoning": gen_result["reasoning"],
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
