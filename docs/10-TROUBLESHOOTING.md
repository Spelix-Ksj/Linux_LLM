# 10. 문제 해결 (트러블슈팅) 가이드

> **이 문서를 읽으면**: 시스템 운영 중 발생하는 주요 문제를 증상별로 진단하고 해결할 수 있습니다.
> **소요 시간**: 약 20분 (전체 읽기) / 해당 섹션만 참고 시 5분
> **선행 조건**: [09-OPERATIONS (서버 운영 가이드)](./09-OPERATIONS.md)

---

## 목차

1. [증상별 해결 플로우차트](#1-증상별-해결-플로우차트)
2. [웹 UI 접속 불가](#2-웹-ui-접속-불가)
3. [SQL 생성 안됨](#3-sql-생성-안됨)
4. [SQL 실행 오류](#4-sql-실행-오류)
5. [특정 모델 응답 없음](#5-특정-모델-응답-없음)
6. [서버 전체 느림](#6-서버-전체-느림)
7. [비밀번호/인증 문제](#7-비밀번호인증-문제)
8. [전체 시스템 재시작 순서](#8-전체-시스템-재시작-순서)
9. [빠른 참조 테이블](#9-빠른-참조-테이블)

---

## 1. 증상별 해결 플로우차트

문제가 발생했을 때 아래 차트를 보고 해당 섹션으로 이동합니다.

```
문제 발생
  |
  +-- 웹 UI(7860)에 접속이 안 되나요?
  |     +-- 예 --> 섹션 2. 웹 UI 접속 불가
  |
  +-- SQL이 생성되지 않나요? (웹 UI는 됨)
  |     +-- 예 --> 섹션 3. SQL 생성 안됨
  |
  +-- SQL은 생성되었으나 실행 시 오류가 나나요?
  |     +-- 예 --> 섹션 4. SQL 실행 오류
  |
  +-- 특정 모델(Qwen3-Coder)만 응답이 없나요?
  |     +-- 예 --> 섹션 5. 특정 모델 응답 없음
  |
  +-- 서버 전체가 느린가요?
  |     +-- 예 --> 섹션 6. 서버 전체 느림
  |
  +-- 비밀번호가 안 맞거나 로그인이 안 되나요?
  |     +-- 예 --> 섹션 7. 비밀번호/인증 문제
  |
  +-- 전체 시스템을 재시작해야 하나요?
        +-- 예 --> 섹션 8. 전체 시스템 재시작 순서
```

---

## 2. 웹 UI 접속 불가

**증상**: 브라우저에서 `http://192.168.10.40:7860`에 접속했을 때 페이지가 로드되지 않습니다.

### 2-1. 서비스 상태 확인

```bash
systemctl status text2sql-ui
```

| 상태 | 의미 | 다음 조치 |
|------|------|-----------|
| `active (running)` | 서비스는 실행 중 | 2-2단계로 이동 |
| `inactive (dead)` | 서비스가 중지됨 | `systemctl start text2sql-ui` 실행 |
| `failed` | 서비스가 오류로 중지됨 | 2-3단계로 이동 |

### 2-2. 방화벽 확인

서비스는 실행 중인데 접속이 안 되면 방화벽 문제일 수 있습니다.

```bash
firewall-cmd --list-ports
```

출력에 `7860/tcp`가 포함되어 있어야 합니다. 없으면 아래 명령으로 포트를 추가합니다.

```bash
firewall-cmd --permanent --add-port=7860/tcp
firewall-cmd --reload
```

### 2-3. 로그 확인

```bash
journalctl -u text2sql-ui -n 100 --no-pager
```

**자주 발생하는 오류 메시지 및 해결법**:

| 오류 메시지 | 원인 | 해결 방법 |
|-------------|------|-----------|
| `GRADIO_USER and GRADIO_PASSWORD environment variables must be set` | `.env` 파일에 계정 정보가 없음 | `.env` 파일에 `GRADIO_USER`와 `GRADIO_PASSWORD` 설정 |
| `Address already in use` | 포트 7860이 이미 사용 중 | `lsof -i :7860`으로 기존 프로세스 확인 후 종료 |
| `ModuleNotFoundError` | Python 패키지 누락 | `conda activate text2sql && pip install 패키지명` |
| `Connection refused` (vLLM 관련) | vLLM 서비스가 시작되지 않음 | 섹션 3으로 이동 |

### 2-4. .env 파일 확인

```bash
cat /root/text2sql/app/.env
```

아래 항목이 모두 설정되어 있는지 확인합니다.

```
GRADIO_USER=admin
GRADIO_PASSWORD=비밀번호
GRADIO_HOST=0.0.0.0
GRADIO_PORT=7860
```

설정 변경 후 반드시 서비스를 재시작합니다.

```bash
systemctl restart text2sql-ui
```

---

## 3. SQL 생성 안됨

**증상**: 웹 UI에서 질문을 입력하고 "SQL 생성 및 실행" 버튼을 눌렀으나, SQL이 생성되지 않거나 "LLM 서버 연결에 실패했습니다"라는 오류가 표시됩니다.

### 3-1. vLLM 서비스 상태 확인

```bash
systemctl status vllm
```

| 상태 | 의미 | 다음 조치 |
|------|------|-----------|
| `active (running)` | 서비스는 실행 중 | 3-2단계로 이동 |
| `inactive (dead)` | 서비스가 중지됨 | `systemctl start vllm` 실행 후 2~5분 대기 |
| `failed` | 서비스가 오류로 중지됨 | 3-4단계로 이동 |

### 3-2. 모델 로딩 여부 확인

```bash
curl http://localhost:8000/v1/models
```

| 응답 | 의미 | 다음 조치 |
|------|------|-----------|
| JSON 모델 목록 | 모델 로딩 완료 | 3-4단계(로그)로 이동하여 다른 원인 조사 |
| `Connection refused` | 서비스 미시작 또는 모델 로딩 중 | 2~5분 후 다시 시도 |
| 응답 지연(10초 이상) | 모델 로딩 중 | 5분 후 다시 시도 |

### 3-3. GPU 메모리 확인

```bash
nvidia-smi
```

**확인 사항**:
- GPU 0~3에 vLLM 프로세스가 표시되는지 확인합니다.
- GPU 메모리가 사용되고 있는지 확인합니다 (모델 로딩 후 상당량이 사용됨).
- GPU 메모리가 비어 있으면 모델이 로딩되지 않은 것입니다.

```
+----------------------------------+
| Processes:                       |
|  GPU  PID   Type  Process name   |
|   0   XXXX   C   ...vllm...     |  <-- 이런 프로세스가 보여야 정상
|   1   XXXX   C   ...vllm...     |
|   2   XXXX   C   ...vllm...     |
|   3   XXXX   C   ...vllm...     |
+----------------------------------+
```

### 3-4. vLLM 로그 확인

```bash
journalctl -u vllm -n 200 --no-pager
```

**자주 발생하는 오류 메시지 및 해결법**:

| 오류 메시지 | 원인 | 해결 방법 |
|-------------|------|-----------|
| `torch.cuda.OutOfMemoryError` | GPU 메모리 부족 | 다른 GPU 프로세스를 종료하고 vLLM을 재시작 |
| `FileNotFoundError: ...model...` | 모델 파일 경로가 잘못됨 | 서비스 파일에서 `--model` 경로 확인 |
| `NCCL error` | GPU 간 통신 오류 | `systemctl restart vllm`으로 재시작 |
| `Killed` | 시스템 메모리(RAM) 부족 | `free -h`로 메모리 확인 후 불필요한 프로세스 종료 |

### 3-5. vLLM 서비스 재시작 (최후의 수단)

```bash
systemctl restart vllm
```

> **주의**: 모델을 GPU에 다시 로딩하므로 약 2~5분이 소요됩니다. 이 시간 동안 SQL 생성 기능을 사용할 수 없습니다.

재시작 후 모델 로딩 완료를 확인합니다.

```bash
# 30초 간격으로 확인 (JSON 응답이 오면 로딩 완료)
curl http://localhost:8000/v1/models
```

---

## 4. SQL 실행 오류

**증상**: SQL은 생성되었으나, "SQL 실행 중 오류가 발생했습니다" 메시지가 표시됩니다.

### 4-1. Oracle DB 연결 확인

```bash
conda activate text2sql
cd /root/text2sql
python db_setup.py
```

| 결과 | 의미 | 다음 조치 |
|------|------|-----------|
| "연결 성공" | DB 연결 정상 | 4-2단계로 이동 |
| `ORA-12170: TNS:Connect timeout` | DB 서버에 연결할 수 없음 | 네트워크 또는 DB 서버 상태 확인 |
| `ORA-01017: invalid username/password` | 계정 정보 오류 | `.env`의 `ORACLE_USER`/`ORACLE_PASSWORD` 확인 |
| `ORA-12541: TNS:no listener` | DB 리스너 미실행 | DB 관리자에게 문의 |

### 4-2. 테이블/컬럼 존재 여부 확인

생성된 SQL에서 사용하는 테이블과 컬럼이 실제로 존재하는지 확인합니다.

```bash
conda activate text2sql
cd /root/text2sql
python -c "
from db_setup import get_engine
from sqlalchemy import inspect
engine = get_engine()
inspector = inspect(engine)
tables = inspector.get_table_names(schema='HRAI_CON')
print('사용 가능한 테이블:', tables)
"
```

이 시스템에서 사용하는 4개 테이블은 다음과 같습니다.

| 테이블명 | 설명 |
|----------|------|
| `move_item_master` | 인사이동 대상 직원 마스터 |
| `move_case_item` | 인사이동 배치안 상세 |
| `move_case_cnst_master` | 인사이동 제약조건 |
| `move_org_master` | 조직 마스터 |

### 4-3. SQL 문법 오류

LLM이 생성한 SQL에 문법 오류가 있을 수 있습니다. 주요 확인 사항은 다음과 같습니다.

| 문제 | 증상 | 원인 |
|------|------|------|
| `LIMIT` 사용 | `ORA-00933: SQL command not properly ended` | MySQL 문법 사용. Oracle에서는 `FETCH FIRST N ROWS ONLY` 또는 `ROWNUM`을 사용해야 함 |
| 스키마 누락 | `ORA-00942: table or view does not exist` | 테이블명 앞에 `HRAI_CON.` 접두사가 없음 |
| 잘못된 컬럼명 | `ORA-00904: invalid identifier` | 존재하지 않는 컬럼명 사용 |
| 쌍따옴표 문제 | `ORA-00972: identifier is too long` | 별칭에 큰따옴표 사용 규칙 위반 |

### 4-4. 타임아웃

시스템은 SQL 실행에 30초 타임아웃과 1,000행 제한을 적용합니다. 복잡한 쿼리가 이 제한을 초과할 수 있습니다.

- SQL 실행이 30초를 초과하면 타임아웃으로 오류가 발생합니다.
- 질문을 더 구체적으로 바꾸어 복잡도를 줄여 주세요.
- 예: "전체 직원을 보여줘" 대신 "IT 부서 직원 10명만 보여줘"

---

## 5. 특정 모델 응답 없음

**증상**: GPT-OSS-120B는 정상인데 Qwen3-Coder만 응답이 없거나, 반대의 경우입니다.

### 5-1. Qwen3-Coder 서비스 확인

```bash
systemctl status vllm-qwen3-coder
```

서비스가 중지 또는 실패 상태이면 재시작합니다.

```bash
systemctl restart vllm-qwen3-coder
```

### 5-2. Qwen3-Coder 모델 로딩 확인

```bash
curl http://localhost:8001/v1/models
```

JSON 응답이 오면 모델 로딩이 완료된 것입니다.

### 5-3. Qwen3-Coder 로그 확인

```bash
journalctl -u vllm-qwen3-coder -n 100 --no-pager
```

### 5-4. 컨텍스트 길이 초과 문제

Qwen3-Coder는 MoE 30B (활성 3B) 모델입니다. 입력 프롬프트가 너무 길면 응답이 실패할 수 있습니다.

**해결 방법**:
- 질문을 더 짧고 간결하게 작성합니다.
- 복잡한 질문은 GPT-OSS-120B 모델을 사용합니다.

### 5-5. GPU 4 상태 확인

Qwen3-Coder는 GPU 4에서 실행됩니다.

```bash
nvidia-smi
```

GPU 4에 vLLM 프로세스가 보이는지 확인합니다. 프로세스가 없으면 모델이 로딩되지 않은 것입니다.

---

## 6. 서버 전체 느림

**증상**: 모든 기능(웹 UI, SQL 생성, SQL 실행)이 평소보다 현저히 느립니다.

### 6-1. GPU 온도 확인

```bash
nvidia-smi
```

**확인 포인트**:
- GPU 온도가 **80도 이상**이면 성능 저하(thermal throttling)가 발생할 수 있습니다.
- 서버실 온도를 확인하고, 필요하면 냉각 조치를 취합니다.

| 온도 범위 | 상태 | 조치 |
|-----------|------|------|
| 40~60도 | 정상 | 조치 불필요 |
| 60~80도 | 주의 | 서버실 환경 확인 |
| 80도 이상 | 위험 | 서버실 냉각 조치 필요, 서비스 일시 중지 고려 |

### 6-2. 시스템 메모리(RAM) 확인

```bash
free -h
```

**확인 포인트**:
- `available` 값이 중요합니다. 이 값이 **2GB 미만**이면 메모리 부족입니다.
- vLLM은 GPU 메모리를 사용하지만, 모델 로딩 과정에서 시스템 RAM도 사용합니다.

```
              total    used    free    shared  buff/cache   available
Mem:          503Gi   480Gi   1.2Gi    12Mi      22Gi        20Gi
                                                              ^^^^
                                                        이 값이 2GB 이상이어야 함
```

### 6-3. 디스크 사용량 확인

```bash
df -h
```

**확인 포인트**:
- `Use%`가 **95% 이상**이면 디스크 부족입니다.
- 디스크가 가득 차면 로그 기록, 임시 파일 생성 등이 실패하여 전체 시스템이 느려질 수 있습니다.

**디스크 정리 방법** (필요 시):
```bash
# 시스템 저널 로그 정리 (1GB 이상 유지)
journalctl --vacuum-size=1G

# 오래된 pip 캐시 삭제
pip cache purge
```

### 6-4. CPU 사용률 확인

```bash
top
```

> `q` 키를 눌러 종료합니다.

CPU 사용률이 지속적으로 높다면 어떤 프로세스가 CPU를 점유하고 있는지 확인합니다.

---

## 7. 비밀번호/인증 문제

**증상**: 웹 UI 로그인 시 "Invalid username or password" 오류가 표시되거나, 비밀번호를 변경했는데 적용되지 않습니다.

### 7-1. 현재 설정 확인

```bash
cat /root/text2sql/app/.env
```

`GRADIO_USER`와 `GRADIO_PASSWORD` 값을 확인합니다.

### 7-2. 비밀번호 변경

```bash
nano /root/text2sql/app/.env
```

`GRADIO_PASSWORD=` 뒤의 값을 새 비밀번호로 변경합니다.

```
GRADIO_PASSWORD=새비밀번호
```

저장 방법: `Ctrl + O` -> `Enter` -> `Ctrl + X`

### 7-3. 서비스 재시작 (필수!)

`.env` 파일을 수정한 후 반드시 서비스를 재시작해야 변경 사항이 적용됩니다.

```bash
systemctl restart text2sql-ui
```

### 7-4. 변경 확인

```bash
systemctl status text2sql-ui
```

`Active: active (running)` 상태인지 확인한 후 브라우저에서 새 비밀번호로 로그인을 시도합니다.

> **주의**: 브라우저에 이전 비밀번호가 캐시되어 있을 수 있습니다. 브라우저의 캐시를 지우거나 시크릿/비공개 창으로 접속하세요.

---

## 8. 전체 시스템 재시작 순서

서비스 간에는 의존 관계가 있으므로 반드시 아래 순서를 지켜야 합니다.

### 의존 관계 다이어그램

```
+------------------+    +------------------------+
|  vllm            |    |  vllm-qwen3-coder      |
|  (GPU 0-3)       |    |  (GPU 4)               |
|  포트: 8000      |    |  포트: 8001             |
+--------+---------+    +-----------+------------+
         |                          |
         +-----------+--------------+
                     |
                     v
         +-----------------------+
         |  text2sql-ui          |
         |  (Gradio 웹 UI)      |
         |  포트: 7860           |
         +-----------------------+
                     |
                     v
         +-----------------------+
         |  Oracle DB            |
         |  (외부 서버)           |
         |  HQ.SPELIX.CO.KR:7744|
         +-----------------------+
```

**핵심**: vLLM 서비스들이 먼저 시작되어 모델 로딩이 완료된 후, text2sql-ui를 시작해야 합니다.

### 전체 중지 순서 (역순)

```bash
# 1단계: 웹 UI 중지 (가장 먼저)
systemctl stop text2sql-ui

# 2단계: vLLM 서비스 중지
systemctl stop vllm
systemctl stop vllm-qwen3-coder
```

### 전체 시작 순서

```bash
# =====================================================
#  1단계: vLLM 서비스 시작 (모델 서버 먼저!)
# =====================================================
systemctl start vllm
systemctl start vllm-qwen3-coder

# =====================================================
#  2단계: 모델 로딩 대기 (약 2~5분)
# =====================================================
# 30초~1분 간격으로 아래 명령을 실행하여 로딩 완료를 확인합니다.
curl http://localhost:8000/v1/models
curl http://localhost:8001/v1/models
# -> JSON 응답이 오면 로딩 완료

# =====================================================
#  3단계: 웹 UI 시작
# =====================================================
systemctl start text2sql-ui

# =====================================================
#  4단계: 전체 상태 확인
# =====================================================
systemctl status vllm vllm-qwen3-coder text2sql-ui
```

### 한눈에 보는 재시작 절차

```
[중지]  text2sql-ui  --> vllm, vllm-qwen3-coder
           (역순)

[시작]  vllm, vllm-qwen3-coder  --> (2~5분 대기)  --> text2sql-ui
           (정순)
```

---

## 9. 빠른 참조 테이블

가장 자주 발생하는 증상과 해결 방법을 한 테이블로 정리합니다.

| 증상 | 확인 명령어 | 해결 명령어 | 비고 |
|------|-----------|------------|------|
| 웹 UI 접속 불가 | `systemctl status text2sql-ui` | `systemctl restart text2sql-ui` | |
| 웹 UI 접속 불가 (방화벽) | `firewall-cmd --list-ports` | `firewall-cmd --permanent --add-port=7860/tcp && firewall-cmd --reload` | 7860/tcp 확인 |
| SQL 생성 안됨 | `systemctl status vllm` | `systemctl restart vllm` | 재로딩 2~5분 소요 |
| SQL 생성 안됨 | `curl http://localhost:8000/v1/models` | 모델 로딩 대기 후 재시도 | JSON 응답 확인 |
| SQL 실행 오류 | `python db_setup.py` | `.env` DB 정보 확인 후 재시작 | Oracle 연결 확인 |
| Qwen3 응답 없음 | `systemctl status vllm-qwen3-coder` | `systemctl restart vllm-qwen3-coder` | |
| GPU 메모리 부족 | `nvidia-smi` | 불필요한 프로세스 종료 후 vLLM 재시작 | |
| 서버 느림 (GPU 온도) | `nvidia-smi` | 서버실 냉각 확인 | 80도 이상 주의 |
| 서버 느림 (메모리) | `free -h` | 불필요한 프로세스 종료 | available 2GB 이상 |
| 서버 느림 (디스크) | `df -h` | `journalctl --vacuum-size=1G` | Use% 95% 미만 |
| 비밀번호 변경 안됨 | `cat /root/text2sql/app/.env` | `.env` 수정 후 `systemctl restart text2sql-ui` | 재시작 필수 |
| 전체 재시작 | `systemctl status vllm vllm-qwen3-coder text2sql-ui` | 섹션 8 순서 참고 | 순서 중요 |

---

## 문서 탐색
| 이전 | 목차 | 다음 |
|------|------|------|
| [09-OPERATIONS](./09-OPERATIONS.md) | [00-전체 안내](./00-INDEX.md) | [11-MODEL-MANAGEMENT](./11-MODEL-MANAGEMENT.md) |
