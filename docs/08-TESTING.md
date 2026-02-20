# 08. 통합 테스트 및 검증

> **이 문서를 읽으면**: 시스템의 모든 구성 요소(GPU, vLLM, Oracle DB, 파이프라인, 웹 UI)가 정상 동작하는지 단계별로 확인할 수 있습니다.
> **소요 시간**: 약 30분
> **선행 조건**: [07-systemd 서비스 등록](./07-SERVICES.md)

---

## 목차

1. [단계별 검증 테이블](#1-단계별-검증-테이블)
2. [test_e2e.py 실행 방법](#2-test_e2epy-실행-방법)
3. [수동 테스트 시나리오](#3-수동-테스트-시나리오)
4. [모델 비교 테스트](#4-모델-비교-테스트-gpt-oss-vs-qwen3-coder)
5. [보안 테스트](#5-보안-테스트)
6. [전체 정상 판정 기준 체크리스트](#6-전체-정상-판정-기준-체크리스트)

---

## 1. 단계별 검증 테이블

시스템을 구성하는 모든 요소를 아래 순서대로 검증합니다. **위에서 아래로** 진행하며, 이전 단계가 통과해야 다음 단계를 진행할 수 있습니다.

| 단계 | 확인 사항 | 명령어 | 기대 결과 | 실패 시 참고 |
|------|-----------|--------|-----------|-------------|
| **1. GPU** | H100 5장 인식 | `nvidia-smi` | GPU 0~4까지 5장이 표시되고, 각각 약 95GB VRAM이 확인됨 | 서버 재부팅 또는 GPU 드라이버 확인 |
| **2. vLLM 메인** | GPT-OSS-120B 모델 서빙 | `curl http://localhost:8000/v1/models` | JSON 형태로 모델 목록이 반환됨 | [10-TROUBLESHOOTING](./10-TROUBLESHOOTING.md) 섹션 3 |
| **3. vLLM 보조** | Qwen3-Coder 모델 서빙 | `curl http://localhost:8001/v1/models` | JSON 형태로 모델 목록이 반환됨 | [10-TROUBLESHOOTING](./10-TROUBLESHOOTING.md) 섹션 5 |
| **4. Oracle** | DB 연결 | `conda activate text2sql && cd /root/text2sql && python db_setup.py` | "연결 성공" 메시지 출력 | [10-TROUBLESHOOTING](./10-TROUBLESHOOTING.md) 섹션 4 |
| **5. 파이프라인** | SQL 생성 및 실행 | `conda activate text2sql && cd /root/text2sql && python text2sql_pipeline.py` | SQL 쿼리가 생성되고, 조회 결과가 출력됨 | [10-TROUBLESHOOTING](./10-TROUBLESHOOTING.md) 섹션 3~4 |
| **6. 웹 UI** | 브라우저 접속 | 브라우저에서 `http://192.168.10.40:7860` 접속 | 로그인 페이지가 표시됨 | [10-TROUBLESHOOTING](./10-TROUBLESHOOTING.md) 섹션 2 |

### 검증 명령어 상세 설명

#### 1단계: GPU 확인

```bash
nvidia-smi
```

아래와 같은 출력이 나오면 정상입니다.

```
+-------------------------------------------+
| GPU  Name          ...  Memory-Usage      |
|   0  NVIDIA H100 NVL    xxxMiB / 95830MiB |  <-- GPU 0 (gpt-oss-120b)
|   1  NVIDIA H100 NVL    xxxMiB / 95830MiB |  <-- GPU 1 (gpt-oss-120b)
|   2  NVIDIA H100 NVL    xxxMiB / 95830MiB |  <-- GPU 2 (gpt-oss-120b)
|   3  NVIDIA H100 NVL    xxxMiB / 95830MiB |  <-- GPU 3 (gpt-oss-120b)
|   4  NVIDIA H100 NVL    xxxMiB / 95830MiB |  <-- GPU 4 (Qwen3-Coder)
+-------------------------------------------+
```

- GPU 0~4까지 총 5장이 표시되어야 합니다.
- 각 GPU의 Memory-Usage 항목에서 모델 로딩 후에는 메모리가 상당 부분 사용된 상태가 정상입니다.

#### 2단계: vLLM 메인 (GPT-OSS-120B) 확인

```bash
curl http://localhost:8000/v1/models
```

정상 응답 예시:

```json
{
  "data": [
    {
      "id": "/install_file_backup/tessinu/gpt-oss-120b",
      "object": "model",
      ...
    }
  ]
}
```

- `"data"` 배열 안에 모델 정보가 1개 이상 포함되어 있으면 정상입니다.
- `Connection refused` 오류가 나오면 아직 모델이 로딩 중이거나, vLLM 서비스가 시작되지 않은 것입니다. 2~5분 후 다시 시도합니다.

#### 3단계: vLLM 보조 (Qwen3-Coder) 확인

```bash
curl http://localhost:8001/v1/models
```

정상 응답 예시:

```json
{
  "data": [
    {
      "id": "Qwen3-Coder-30B-A3B-Instruct",
      "object": "model",
      ...
    }
  ]
}
```

#### 4단계: Oracle DB 연결 확인

```bash
conda activate text2sql
cd /root/text2sql
python db_setup.py
```

정상 출력 예시:

```
==================================================
 Oracle DB 연결 테스트
==================================================
  Host: HQ.SPELIX.CO.KR:7744
  SID:  HISTPRD
  User: HRAI_CON

  연결 성공: (1,)
  DB 버전: Oracle Database ...
```

- "연결 성공"이 출력되면 정상입니다.
- 이후 대상 테이블 스키마와 샘플 데이터도 함께 출력됩니다.

#### 5단계: 파이프라인 테스트

```bash
conda activate text2sql
cd /root/text2sql
python text2sql_pipeline.py
```

정상 출력 예시:

```
질문: move_item_master 테이블의 직급별(pos_grd_nm) 인원 수를 구해줘
SQL:
SELECT pos_grd_nm AS "직급", COUNT(*) AS "인원수"
FROM HRAI_CON.move_item_master
GROUP BY pos_grd_nm
ORDER BY COUNT(*) DESC
결과:
   직급  인원수
   ...
```

- SQL이 생성되고, 오류 없이 결과가 출력되면 정상입니다.

#### 6단계: 웹 UI 접속 확인

1. PC의 브라우저를 엽니다.
2. 주소창에 `http://192.168.10.40:7860`을 입력합니다.
3. 로그인 화면이 나타나면 `.env` 파일에 설정된 사용자명과 비밀번호를 입력합니다.
4. "인사정보 Text2SQL 시스템" 화면이 표시되면 정상입니다.

---

## 2. test_e2e.py 실행 방법

`test_e2e.py`는 DB 연결, vLLM 연결, SQL 생성, 다양한 질문 테스트를 자동으로 수행하는 통합 테스트 스크립트입니다.

### 실행 방법

```bash
conda activate text2sql
cd /root/text2sql
python test_e2e.py
```

### 기대 출력

```
==================================================
 Text2SQL 통합 테스트
==================================================

==================================================
[1/4] Oracle DB 연결 테스트
==================================================
  PASS: DB 연결 성공

==================================================
[2/4] vLLM 서버 연결 테스트
==================================================
  사용 가능 모델: ['/install_file_backup/tessinu/gpt-oss-120b']
  PASS: vLLM 서버 정상

==================================================
[3/4] SQL 생성 테스트
==================================================
  질문: 전체 테이블의 행 수를 각각 알려줘
  생성된 SQL:
    SELECT ...
  결과 행 수: N
  PASS: SQL 생성 및 실행 성공

==================================================
[4/4] 다양한 질문 테스트
==================================================
  질문: 직급별 인원 수를 구해줘
  SQL: SELECT pos_grd_nm AS "직급", COUNT(*) AS "인원수" ...
  결과: N건
  ...

  결과: 3 성공 / 0 실패

==================================================
 통합 테스트 완료
==================================================
```

### 테스트 항목별 설명

| 테스트 | 검증 내용 | PASS 조건 |
|--------|-----------|-----------|
| [1/4] DB 연결 | Oracle DB에 `SELECT 1 FROM dual` 실행 | 결과가 반환되면 성공 |
| [2/4] vLLM 연결 | `/v1/models` 엔드포인트 호출 | 모델 목록이 1개 이상이면 성공 |
| [3/4] SQL 생성 | 기본 질문으로 SQL 생성 및 실행 | 오류 없이 결과 행이 반환되면 성공 |
| [4/4] 다양한 질문 | 직급별 인원, 평균 나이, 조건 필터 등 3개 질문 | 각 질문에 대해 SQL 생성 및 실행 성공 |

### 실패 시 대처

- `[1/4]` 실패: Oracle DB 연결 문제입니다. `.env` 파일의 DB 접속 정보를 확인합니다.
- `[2/4]` 실패: vLLM 서비스가 실행 중이지 않거나 모델 로딩이 안 된 것입니다. `systemctl status vllm`을 확인합니다.
- `[3/4]` 실패: LLM이 올바른 SQL을 생성하지 못한 것입니다. vLLM 로그를 확인합니다.
- `[4/4]` 일부 실패: 특정 유형의 질문에서 SQL 생성이 잘 되지 않는 것입니다. 모델의 한계일 수 있으며, 프롬프트 조정을 검토합니다.

---

## 3. 수동 테스트 시나리오

웹 UI(`http://192.168.10.40:7860`)에 접속한 후, 아래 4가지 유형의 질문을 입력하여 정상 동작을 확인합니다.

### 시나리오 1: 기본 집계 (단일 테이블)

**질문**: "직급별 인원 수를 구해줘"

**예상 SQL**:
```sql
SELECT pos_grd_nm AS "직급", COUNT(*) AS "인원수"
FROM HRAI_CON.move_item_master
GROUP BY pos_grd_nm
ORDER BY COUNT(*) DESC
```

**확인 포인트**:
- `move_item_master` 테이블만 사용했는지 확인합니다.
- `GROUP BY`와 `COUNT(*)`가 포함되어 있는지 확인합니다.
- 결과 테이블에 직급명과 인원수가 표시되는지 확인합니다.
- 결과 보고서가 생성되는지 확인합니다.

### 시나리오 2: JOIN (다중 테이블)

**질문**: "부서별 정원과 현원을 비교해줘"

**예상 SQL**:
```sql
SELECT o.org_nm AS "부서명",
       o.tot_to AS "정원",
       COUNT(m.emp_nm) AS "현원"
FROM HRAI_CON.move_org_master o
LEFT JOIN HRAI_CON.move_item_master m ON o.org_nm = m.org_nm
GROUP BY o.org_nm, o.tot_to
ORDER BY o.org_nm
```

**확인 포인트**:
- `move_org_master`와 `move_item_master`를 JOIN했는지 확인합니다.
- 정원(`tot_to`)과 현원(`COUNT`)이 비교 가능한 형태로 출력되는지 확인합니다.
- JOIN 조건이 `org_nm` 기준인지 확인합니다.

### 시나리오 3: 집계 + 정렬 (서브쿼리 가능)

**질문**: "평균 나이가 가장 높은 부서는 어디야?"

**예상 SQL**:
```sql
SELECT org_nm AS "부서명", AVG(year_desc) AS "평균나이"
FROM HRAI_CON.move_item_master
GROUP BY org_nm
ORDER BY AVG(year_desc) DESC
FETCH FIRST 1 ROWS ONLY
```

**확인 포인트**:
- `AVG()` 집계 함수가 사용되었는지 확인합니다.
- `ORDER BY ... DESC`로 내림차순 정렬이 되었는지 확인합니다.
- Oracle 문법(`FETCH FIRST N ROWS ONLY` 또는 `ROWNUM`)이 사용되었는지 확인합니다.
- `LIMIT`(MySQL 문법)이 사용되지 않았는지 확인합니다.

### 시나리오 4: 조건 필터 (WHERE)

**질문**: "IT 부서에서 대리급 이상 직원들만 보여줘"

**예상 SQL**:
```sql
SELECT emp_nm AS "이름", pos_grd_nm AS "직급", org_nm AS "부서"
FROM HRAI_CON.move_item_master
WHERE org_nm LIKE '%IT%'
  AND pos_grd_nm IN ('대리', '과장', '차장', '부장', '이사', '상무', '전무', '부사장', '사장')
```

**확인 포인트**:
- `WHERE` 절에 부서 조건(`org_nm`)과 직급 조건(`pos_grd_nm`)이 모두 포함되었는지 확인합니다.
- "대리급 이상"을 적절히 해석하여 필터링했는지 확인합니다.
- 결과에 IT 부서 소속 직원만 나오는지 확인합니다.

### 테스트 결과 기록

아래 표를 복사하여 테스트 결과를 기록합니다.

| 시나리오 | 질문 유형 | SQL 생성 | SQL 실행 | 결과 보고서 | 판정 |
|----------|-----------|----------|----------|------------|------|
| 1 | 기본 집계 | O / X | O / X | O / X | PASS / FAIL |
| 2 | JOIN | O / X | O / X | O / X | PASS / FAIL |
| 3 | 집계+정렬 | O / X | O / X | O / X | PASS / FAIL |
| 4 | 조건 필터 | O / X | O / X | O / X | PASS / FAIL |

---

## 4. 모델 비교 테스트 (GPT-OSS vs Qwen3-Coder)

### 테스트 목적

같은 질문을 두 모델에 각각 보내어 SQL 생성 품질을 비교합니다.

### 비교 방법

1. 웹 UI(`http://192.168.10.40:7860`)에 접속합니다.
2. **모델 선택** 드롭다운에서 `GPT-OSS 120B (메인 추론 모델)`을 선택합니다.
3. 아래 테스트 질문을 입력하고 결과를 기록합니다.
4. **모델 선택** 드롭다운에서 `Qwen3-Coder 30B (테스트)`로 변경합니다.
5. 같은 질문을 다시 입력하고 결과를 기록합니다.

### 비교 테스트 질문 (5개)

| 번호 | 질문 | 난이도 |
|------|------|--------|
| Q1 | "직급별 인원 수를 구해줘" | 쉬움 |
| Q2 | "부서별 정원과 현원을 비교해줘" | 보통 (JOIN) |
| Q3 | "평균 나이가 가장 높은 부서는 어디야?" | 보통 (집계) |
| Q4 | "IT 부서에서 대리급 이상 직원들만 보여줘" | 보통 (조건) |
| Q5 | "각 지역별로 남녀 성비를 구해줘" | 어려움 (복합 집계) |

### 비교 기록표

| 질문 | 모델 | SQL 정확성 | Oracle 문법 | 한글 별칭 | 실행 결과 | 점수 (1~5) |
|------|------|-----------|------------|-----------|-----------|-----------|
| Q1 | GPT-OSS | O / X | O / X | O / X | O / X | |
| Q1 | Qwen3-Coder | O / X | O / X | O / X | O / X | |
| Q2 | GPT-OSS | O / X | O / X | O / X | O / X | |
| Q2 | Qwen3-Coder | O / X | O / X | O / X | O / X | |
| ... | ... | ... | ... | ... | ... | |

### 평가 기준

| 항목 | 설명 | 배점 |
|------|------|------|
| **SQL 정확성** | 질문의 의도를 정확히 반영한 SQL인지 | 2점 |
| **Oracle 문법** | Oracle 전용 문법(ROWNUM, FETCH FIRST, DUAL 등)을 올바르게 사용했는지 | 1점 |
| **한글 별칭** | 출력 컬럼에 한글 별칭(AS "한글명")을 붙였는지 | 1점 |
| **실행 결과** | SQL이 오류 없이 실행되어 결과를 반환했는지 | 1점 |

- **5점**: 완벽한 SQL 생성 및 실행
- **4점**: 사소한 문제가 있으나 결과는 정확
- **3점**: SQL은 실행되나 의도와 다소 다른 결과
- **2점**: SQL 문법 오류 또는 실행 실패
- **1점**: SQL 생성 자체가 안 됨

### curl을 사용한 모델별 직접 테스트

웹 UI 대신 커맨드라인에서 직접 각 모델에 요청을 보내 비교할 수도 있습니다.

**GPT-OSS-120B (포트 8000)**:
```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "/install_file_backup/tessinu/gpt-oss-120b",
    "messages": [
      {"role": "system", "content": "당신은 Oracle SQL 전문가입니다. SELECT 문만 생성하세요."},
      {"role": "user", "content": "직급별 인원 수를 구해줘"}
    ],
    "max_tokens": 512,
    "temperature": 0.0
  }'
```

**Qwen3-Coder (포트 8001)**:
```bash
curl http://localhost:8001/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen3-Coder-30B-A3B-Instruct",
    "messages": [
      {"role": "system", "content": "당신은 Oracle SQL 전문가입니다. SELECT 문만 생성하세요."},
      {"role": "user", "content": "직급별 인원 수를 구해줘"}
    ],
    "max_tokens": 512,
    "temperature": 0.0
  }'
```

---

## 5. 보안 테스트

시스템이 위험한 SQL(INSERT, UPDATE, DELETE, DROP 등)을 차단하는지 확인합니다.

### 테스트 방법

웹 UI에서 아래 질문을 입력합니다.

### 테스트 케이스

| 번호 | 입력 질문 | 기대 결과 |
|------|-----------|-----------|
| S1 | "모든 직원 데이터를 삭제해줘" | **차단**: "안전하지 않은 SQL이 감지되었습니다. SELECT 문만 허용됩니다." |
| S2 | "move_item_master 테이블을 DROP해줘" | **차단**: 동일한 안전성 오류 메시지 |
| S3 | "직원 이름을 홍길동으로 변경해줘" | **차단**: UPDATE 문이 감지되어 차단 |
| S4 | "새 직원을 추가해줘" | **차단**: INSERT 문이 감지되어 차단 |

### 확인 사항

- 위 4가지 질문 모두에서 **"안전하지 않은 SQL이 감지되었습니다"** 메시지가 표시되어야 합니다.
- 실제 SQL이 실행되지 않아야 합니다(데이터가 변경되지 않아야 합니다).
- 차단 후에도 시스템이 정상적으로 다음 질문을 처리할 수 있어야 합니다.

### 보안 검증 원리

시스템은 `text2sql_pipeline.py`의 `_is_safe_sql()` 함수에서 다음 키워드를 검사하여 위험한 SQL을 차단합니다.

```
차단 키워드: INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, TRUNCATE,
            MERGE, EXEC, EXECUTE, GRANT, REVOKE, CALL, COMMENT, RENAME
```

추가로 다음 조건도 검사합니다:
- SQL이 `SELECT` 또는 `WITH`으로 시작하는지 확인합니다.
- 세미콜론(`;`)이 포함된 다중 쿼리를 차단합니다.
- SQL 주석 내의 키워드는 오탐 방지를 위해 제거한 후 검사합니다.

---

## 6. 전체 정상 판정 기준 체크리스트

아래 모든 항목이 통과되면 시스템이 정상적으로 동작하는 것입니다.

### 필수 항목 (모두 통과해야 함)

| 번호 | 검증 항목 | 확인 방법 | 통과 여부 |
|------|-----------|-----------|-----------|
| 1 | GPU 5장 인식 | `nvidia-smi`에서 GPU 0~4 표시 | [ ] |
| 2 | vLLM 메인 서비스 정상 | `curl localhost:8000/v1/models` JSON 응답 | [ ] |
| 3 | vLLM 보조 서비스 정상 | `curl localhost:8001/v1/models` JSON 응답 | [ ] |
| 4 | Oracle DB 연결 성공 | `python db_setup.py` 연결 성공 메시지 | [ ] |
| 5 | test_e2e.py 전체 통과 | `python test_e2e.py` 4/4 테스트 통과 | [ ] |
| 6 | 웹 UI 접속 가능 | `http://192.168.10.40:7860` 로그인 화면 표시 | [ ] |
| 7 | 웹 UI 로그인 성공 | .env의 계정으로 로그인 | [ ] |
| 8 | 기본 질문 SQL 생성 | "직급별 인원 수를 구해줘" 입력 시 SQL 생성 | [ ] |
| 9 | SQL 실행 결과 표시 | 생성된 SQL로 조회 결과 테이블 표시 | [ ] |
| 10 | 결과 보고서 생성 | 조회 결과에 대한 분석 보고서 표시 | [ ] |
| 11 | 보안 차단 동작 | "데이터를 삭제해줘" 입력 시 차단 메시지 | [ ] |
| 12 | 모델 전환 동작 | 드롭다운에서 Qwen3-Coder 선택 후 질문 처리 | [ ] |

### 선택 항목 (권장)

| 번호 | 검증 항목 | 확인 방법 | 통과 여부 |
|------|-----------|-----------|-----------|
| 13 | JOIN 질문 정상 | 시나리오 2 테스트 통과 | [ ] |
| 14 | 집계 질문 정상 | 시나리오 3 테스트 통과 | [ ] |
| 15 | 조건 질문 정상 | 시나리오 4 테스트 통과 | [ ] |
| 16 | 모델 비교 5개 질문 완료 | 비교 기록표 작성 완료 | [ ] |

### 판정 기준

- **필수 12개 항목 모두 통과**: 시스템 정상 -- 운영 가능
- **필수 항목 1개라도 실패**: 해당 항목의 문제를 해결한 후 재검증 필요
- **선택 항목 일부 실패**: 운영은 가능하나, 해당 유형의 질문에서 제한이 있을 수 있음

---

## 문서 탐색
| 이전 | 목차 | 다음 |
|------|------|------|
| [07-SERVICES](./07-SERVICES.md) | [00-전체 안내](./00-INDEX.md) | [09-OPERATIONS](./09-OPERATIONS.md) |
