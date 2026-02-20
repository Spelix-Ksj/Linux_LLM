# 01. 시스템 아키텍처

> **이 문서를 읽으면**: Text2SQL HR 시스템의 전체 구조, 데이터 흐름, 핵심 컴포넌트의 역할을 이해할 수 있습니다.
> **소요 시간**: 약 15분
> **선행 조건**: 없음

---

## 1. 전체 시스템 구성도

```
+=========================================================================+
|                        사용자 브라우저 (HTTP)                              |
+====================================+====================================+
                                     |
                                     | :7860
                                     v
+=========================================================================+
|                     Gradio 웹 UI  (app.py)                               |
|  +----------------+  +------------------+  +--------------------------+  |
|  | 질문 입력       |  | 모델 선택 Dropdown|  | 예시 질문 (5개)          |  |
|  | (Textbox)      |  | (gpt-oss/Qwen3) |  | (gr.Examples)           |  |
|  +----------------+  +------------------+  +--------------------------+  |
|  +----------------+  +------------------+  +--------------------------+  |
|  | 생성된 SQL      |  | 조회 결과 테이블  |  | 결과 보고서              |  |
|  | (Code)         |  | (Dataframe)      |  | (Accordion + Markdown)  |  |
|  +----------------+  +------------------+  +--------------------------+  |
|                            인증: GRADIO_USER / GRADIO_PASSWORD (.env)     |
+====================================+====================================+
                                     |
                                     v
+=========================================================================+
|              LangChain Text2SQL 파이프라인  (text2sql_pipeline.py)        |
|                                                                          |
|  +-----------------------+    +-----------------------------+            |
|  | SYSTEM_PROMPT         |    | ask_hr(question, model_key) |            |
|  | - Oracle SQL 규칙 9개 |    |   1. LLM 호출 (SQL 생성)    |            |
|  | - 테이블 스키마 정보   |--->|   2. _clean_sql() 정제      |            |
|  | - 한글 컬럼 설명       |    |   3. _is_safe_sql() 검증    |            |
|  +-----------------------+    |   4. Oracle 실행 (1000행)   |            |
|                               +-----------------------------+            |
|  +-----------------------------+    +------------------------------+     |
|  | get_llm(model_key)         |    | generate_report()            |     |
|  | - ChatOpenAI 인스턴스 캐시  |    | - SQL 분석 (테이블/컬럼/건수) |     |
|  | - thread-safe (Lock)       |    | - 2차 LLM 호출 (결과 요약)   |     |
|  +-----------------------------+    | - LLM 추론 과정 (접기 표시)  |     |
|                                     +------------------------------+     |
|  +-----------------------------+    +------------------------------+     |
|  | config.py                  |    | model_registry.py            |     |
|  | - MODEL_REGISTRY (다중 모델)|    | - 헬스체크 (/v1/models)      |     |
|  | - DB_CONFIG (Oracle 접속)  |    | - Dropdown choices 생성      |     |
|  | - .env 파서               |    | - 모델별 설정 조회            |     |
|  +-----------------------------+    +------------------------------+     |
|  +-----------------------------+                                         |
|  | db_setup.py                |                                         |
|  | - SQLAlchemy 엔진 생성     |                                         |
|  | - 커넥션 풀링 (5+10)      |                                         |
|  +-----------------------------+                                         |
+==================+=========================+============================+
                   |                         |
                   v                         v
+-------------------------------+  +-------------------------------+
|  vLLM 인스턴스 (GPU 서버)      |  |  Oracle Database              |
|                               |  |                               |
|  [GPU 0-3] :8000              |  |  호스트: HQ.SPELIX.CO.KR     |
|  gpt-oss-120b (메인)          |  |  포트:   7744                 |
|  - MoE 117B 파라미터          |  |  SID:    HISTPRD              |
|  - Tensor Parallel 4          |  |  스키마:  HRAI_CON            |
|  - OpenAI 호환 API            |  |                               |
|  - conda: py312_sr            |  |  4개 테이블:                  |
|                               |  |  - move_item_master           |
|  [GPU 4]   :8001              |  |  - move_case_item             |
|  Qwen3-Coder-30B (테스트)     |  |  - move_case_cnst_master      |
|  - MoE 30B (활성 3B)          |  |  - move_org_master            |
|  - max-model-len: 32768       |  |                               |
|  - conda: py312_sr            |  |                               |
+-------------------------------+  +-------------------------------+
```

---

## 2. 데이터 흐름

사용자가 질문을 입력하면 아래 8단계를 거쳐 결과가 반환됩니다.

```
[1] 질문 입력 --> [2] Gradio 수신 --> [3] LangChain 파이프라인
        --> [4] 프롬프트 구성 --> [5] vLLM 전송 --> [6] SQL 정제+검증
        --> [7] Oracle 실행 --> [8] 보고서 생성 + UI 표시
```

### 단계별 상세 설명

| 단계 | 위치 | 처리 내용 |
|------|------|-----------|
| **1. 사용자 질문 입력** | 브라우저 | 사용자가 한국어 자연어 질문을 입력합니다. (예: "직급별 인원 수를 구해줘") |
| **2. Gradio 수신** | `app.py` | `process_question()` 함수가 호출됩니다. 빈 입력은 거부하고, `model_key`의 유효성을 검증합니다. |
| **3. LangChain 파이프라인 진입** | `text2sql_pipeline.py` | `ask_hr(question, model_key)` 함수가 호출됩니다. |
| **4. 시스템 프롬프트 + 스키마 구성** | `text2sql_pipeline.py` | `SYSTEM_PROMPT`에 Oracle SQL 규칙 9개, 4개 테이블의 스키마 정보, 한글 컬럼 설명이 포함됩니다. `SystemMessage` + `HumanMessage`로 메시지를 구성합니다. |
| **5. vLLM으로 전송 및 SQL 생성** | vLLM 서버 | `ChatOpenAI` (OpenAI 호환 API)를 통해 선택된 모델의 vLLM 인스턴스에 요청합니다. LLM이 Oracle SELECT 문을 생성합니다. reasoning 모델의 경우 추론 과정(`reasoning_content`)도 캡처합니다. |
| **6. SQL 정제 + 안전성 검증** | `text2sql_pipeline.py` | `_clean_sql()`: 마크다운 코드블록, 설명 텍스트, 세미콜론을 제거합니다. `_is_safe_sql()`: SELECT/WITH만 허용하고, INSERT/UPDATE/DELETE/DROP 등 15개 위험 키워드를 차단합니다. 주석 내 키워드 오탐을 방지하기 위해 `_strip_sql_comments()`로 주석을 먼저 제거합니다. |
| **7. Oracle DB 실행** | Oracle DB | 생성된 SQL을 `SELECT * FROM (생성된SQL) WHERE ROWNUM <= 1000`으로 감싸 최대 1,000행으로 제한합니다. `call_timeout=30000ms`로 30초 타임아웃을 설정합니다. 결과는 pandas DataFrame으로 변환됩니다. |
| **8. 보고서 생성 + UI 표시** | `text2sql_pipeline.py`, `app.py` | `generate_report()`: SQL에서 사용된 테이블명을 추출하고, 결과 상위 20행을 2차 LLM에 전달하여 자연어 분석 보고서를 생성합니다. 최종적으로 생성된 SQL, DataFrame 테이블, 상태 메시지, 분석 보고서가 Gradio UI에 표시됩니다. |

---

## 3. 핵심 컴포넌트

### 3.1 vLLM -- GPU 가속 LLM 서빙 엔진

vLLM은 대규모 언어 모델을 GPU에서 고속으로 서빙하는 추론 엔진입니다. OpenAI 호환 API(`/v1/chat/completions`)를 제공하므로, `langchain_openai.ChatOpenAI`로 직접 연결할 수 있습니다.

| 항목 | 메인 인스턴스 | 테스트 인스턴스 |
|------|--------------|----------------|
| **모델** | gpt-oss-120b (MoE 117B) | Qwen3-Coder-30B-A3B (MoE 30B, 활성 3B) |
| **GPU** | GPU 0-3 (Tensor Parallel 4) | GPU 4 (단일) |
| **포트** | 8000 | 8001 |
| **VRAM 사용** | ~90 GB x 4장 | ~87 GB x 1장 |
| **max_tokens** | 4096 | 4096 |
| **Conda 환경** | py312_sr | py312_sr |
| **systemd 서비스** | vllm | vllm-qwen3-coder |
| **성능 (Text2SQL)** | 4/4 성공 (100%) | 3/4 성공 (75%) |

### 3.2 LangChain -- LLM-DB 연결 미들웨어

LangChain은 LLM과 외부 데이터 소스를 연결하는 프레임워크입니다. 이 프로젝트에서는 다음 컴포넌트를 사용합니다.

| 컴포넌트 | 패키지 | 역할 |
|----------|--------|------|
| `ChatOpenAI` | `langchain_openai` | vLLM의 OpenAI 호환 API에 연결하여 LLM을 호출합니다. |
| `SQLDatabase` | `langchain_community` | Oracle DB에 연결하여 테이블 스키마 정보를 자동으로 추출합니다. |
| `SystemMessage` / `HumanMessage` | `langchain_core` | LLM에 전달할 시스템 프롬프트와 사용자 질문을 구조화합니다. |

LangChain의 `SQLDatabase`는 시작 시 4개 대상 테이블의 스키마 정보와 샘플 데이터(3행)를 자동으로 가져와서 `SYSTEM_PROMPT`에 주입합니다. 이를 통해 LLM이 테이블 구조를 정확히 파악할 수 있습니다.

### 3.3 Oracle Database -- HR 인사정보 DB

Oracle DB에는 인사이동 관련 4개 테이블이 있으며, 스키마는 `HRAI_CON`입니다.

**ERD (Entity-Relationship Diagram)**

```
+---------------------------+         +---------------------------+
| move_item_master          |         | move_org_master           |
|---------------------------|         |---------------------------|
| emp_nm      (이름)        |         | org_nm      (조직명)      |
| pos_grd_nm  (직급)        |    +----| org_type    (조직유형)    |
| org_nm      (현재조직) --------+    | tot_to      (정원)        |
| lvl1~5_nm   (조직계층)    |         | region_type (지역구분)    |
| job_type1/2 (직종)        |         | job_type1/2 (직종)        |
| gender_nm   (성별)        |         +---------------------------+
| year_desc   (연령대)      |
| org_work_mon(조직근무개월) |
| region_type (지역구분)    |
+------------+--------------+
             |
             | (1:N 관계)
             v
+---------------------------+         +---------------------------+
| move_case_item            |         | move_case_cnst_master     |
|---------------------------|         |---------------------------|
| new_lvl1~5_nm (새조직계층)|         | cnst_nm     (제약조건명)  |
| must_stay_yn  (잔류필수)  |         | cnst_val    (제약값)      |
| must_move_yn  (이동필수)  |         | penalty_val (위반패널티)  |
+---------------------------+         +---------------------------+
```

- **move_item_master**: 인사이동 대상 직원 마스터 (개인정보 + 현재 소속)
- **move_case_item**: 인사이동 배치안 상세 (새 조직 배치 결과)
- **move_case_cnst_master**: 인사이동 제약조건 정의 (제약명, 값, 패널티)
- **move_org_master**: 조직 마스터 (조직명, 유형, 정원, 지역)

### 3.4 Gradio -- Python 웹 UI 프레임워크

Gradio는 Python 함수를 웹 인터페이스로 변환하는 프레임워크입니다. `gr.Blocks` API를 사용하여 커스텀 레이아웃을 구성합니다.

**UI 구성 요소**

| 컴포넌트 | Gradio 위젯 | 설명 |
|----------|-------------|------|
| 모델 선택 | `gr.Dropdown` | gpt-oss-120b / Qwen3-Coder 중 선택, 헬스체크 상태 표시 |
| 모델 새로고침 | `gr.Button` | 모델 목록 및 상태를 실시간 갱신 |
| 모델 상태 | `gr.Markdown` | 현재 선택된 모델의 이름, 상태, GPU 정보 표시 |
| 질문 입력 | `gr.Textbox` | 한국어 자연어 질문 입력 (2줄) |
| 실행 버튼 | `gr.Button` | "SQL 생성 및 실행" (primary variant) |
| 상태 표시 | `gr.Textbox` | "조회 완료: N건" 또는 오류 메시지 |
| 생성된 SQL | `gr.Code` | SQL 구문 강조 표시 (language="sql") |
| 조회 결과 | `gr.Dataframe` | pandas DataFrame을 테이블로 표시 |
| 결과 보고서 | `gr.Accordion` + `gr.Markdown` | SQL 분석 + LLM 추론 과정 + 자연어 결과 요약 |
| 예시 질문 | `gr.Examples` | 5개 예시 질문 (클릭하면 자동 입력) |

---

## 4. 기술 스택

| 분류 | 패키지 | 용도 |
|------|--------|------|
| **LLM 서빙** | vLLM | H100 GPU 최적화 LLM 추론 엔진, OpenAI 호환 API 제공 |
| **LLM 프레임워크** | LangChain (`langchain_openai`, `langchain_community`, `langchain_core`) | LLM-DB 연결 미들웨어, 프롬프트 관리, 스키마 자동 추출 |
| **DB 드라이버** | oracledb | Oracle Database Python 드라이버 (Thin 모드) |
| **DB ORM** | SQLAlchemy | 커넥션 풀링, 스키마 조회, SQL 실행 |
| **웹 UI** | Gradio | Python 함수를 웹 인터페이스로 변환, 인증 지원 |
| **데이터 처리** | pandas | SQL 실행 결과를 DataFrame으로 변환 및 표시 |
| **환경 관리** | Miniconda | Python 가상 환경 (text2sql, py312_sr) |
| **프로세스 관리** | systemd | vLLM 및 Gradio 서비스의 자동 시작/재시작 관리 |
| **메인 LLM** | gpt-oss-120b | OpenAI 범용 오픈소스 추론 모델 (MoE 117B, Apache 2.0) |
| **테스트 LLM** | Qwen3-Coder-30B-A3B-Instruct | Alibaba 코딩 특화 MoE 모델 (30B 파라미터, 활성 3B) |

---

## 5. 모델 선택 히스토리

이 프로젝트에서는 최적의 Text2SQL 모델을 찾기 위해 여러 모델을 테스트했습니다. 아래는 그 과정을 시간 순서대로 정리한 것입니다.

```
SQLCoder-34b (2023년, 구세대)
    |
    |  "더 좋은 모델이 있을까?"
    v
Arctic-Text2SQL-R1-7B (BIRD 벤치마크 1위, 68.9%)
    |
    |  문제: SQLite 전용 학습 -> Oracle 비호환
    |        LIMIT, strftime() 등 SQLite 문법 생성
    |        시스템 프롬프트로 교정 불가 (파인튜닝 override)
    v
EXAONE-Deep-32B (LG AI, 한국어 특화)
    |
    |  문제: 시스템 프롬프트(~7,289 토큰) + max_tokens(4,096)
    |        = 11,385 > max_model_len(8,192)
    |        -> 컨텍스트 초과 400 에러
    v
gpt-oss-120b (메인 -- 100% 성공률)       <-- 현재 메인 모델
    |
    |  "보조 모델도 확보하자"
    v
Qwen3-Coder-30B-A3B (테스트 -- 75% 성공률)  <-- 현재 테스트 모델
```

### 최종 결론

| 모델 | 역할 | GPU | 성공률 | 비고 |
|------|------|-----|--------|------|
| **gpt-oss-120b** | 메인 | 0-3 (TP4) | 100% | 범용 추론 모델, Oracle SQL 안정적 생성 |
| **Qwen3-Coder-30B** | 테스트 | 4 | 75% | 코딩 특화 MoE, 한글 별칭 자동 사용 우수하나 불필요 JOIN 오류 |

### 핵심 교훈

- **Text2SQL 벤치마크 점수가 실전 성능을 보장하지 않습니다.** BIRD/Spider 벤치마크는 100% SQLite 기반이므로, Oracle 환경에서는 벤치마크 1위 모델(Arctic)보다 범용 모델(gpt-oss)이 우수했습니다.
- **Oracle SQL 전용 Text2SQL 오픈소스 모델은 현재 존재하지 않습니다.** 장기적으로 SQLGlot(SQLite -> Oracle 자동 변환)이나 Oracle SQL 파인튜닝을 검토할 수 있습니다.

---

## 6. 보안 설계

이 시스템은 다음 4개 계층에서 보안을 적용합니다.

### 6.1 환경변수 분리 (.env)

모든 민감 정보(DB 비밀번호, Gradio 인증 정보)는 `.env` 파일에 저장하며, Git에서 추적하지 않습니다.

```
# .env 파일 (Git 미추적)
ORACLE_PASSWORD=****
GRADIO_USER=admin
GRADIO_PASSWORD=****
```

`config.py`의 `_load_env()` 함수가 `.env` 파일을 파싱하여 `os.environ`에 주입합니다. 이미 환경변수에 설정된 값이 있으면 해당 값을 우선합니다.

### 6.2 SQL 안전성 검사

`_is_safe_sql()` 함수가 LLM이 생성한 SQL의 안전성을 검증합니다.

- **허용**: `SELECT`, `WITH` 로 시작하는 문만 실행합니다.
- **차단**: 15개 위험 키워드를 정규식으로 검사합니다.
  ```
  INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, TRUNCATE,
  MERGE, EXEC, EXECUTE, GRANT, REVOKE, CALL, COMMENT, RENAME
  ```
- **다중 문 차단**: 세미콜론(`;`)이 포함된 SQL을 거부합니다.
- **주석 오탐 방지**: `_strip_sql_comments()`로 `--` 및 `/* */` 주석을 제거한 후 키워드를 검사합니다.

### 6.3 Gradio 인증

웹 UI 접속 시 ID/비밀번호 인증을 요구합니다. 인증 정보는 `.env` 파일에서 읽으며, 환경변수가 설정되지 않으면 `RuntimeError`가 발생하여 서버가 시작되지 않습니다.

```python
gradio_user = os.environ.get("GRADIO_USER")
gradio_password = os.environ.get("GRADIO_PASSWORD")
if not gradio_user or not gradio_password:
    raise RuntimeError("GRADIO_USER and GRADIO_PASSWORD environment variables must be set")
```

### 6.4 결과 행 수 제한

Oracle DB 실행 시 모든 쿼리를 아래와 같이 감싸서 최대 1,000행만 반환합니다.

```sql
SELECT * FROM (사용자SQL) WHERE ROWNUM <= 1000
```

추가로, `call_timeout=30000ms` (30초) 타임아웃을 설정하여 장시간 실행되는 쿼리를 자동 종료합니다.

### 6.5 프롬프트 인젝션 방지

보고서 생성 시 사용자 질문의 길이를 500자로 제한하고, `<user_input>` 구분자로 감싸서 프롬프트 인젝션을 방지합니다.

```python
safe_question = question[:500]
user_prompt = f"""## 원래 질문
<user_input>{safe_question}</user_input>
...
"""
```

---

## 문서 탐색

| 이전 | 목차 | 다음 |
|------|------|------|
| - | [00-전체 안내](./00-INDEX.md) | [02-서버 환경 설정](./02-SERVER-SETUP.md) |
