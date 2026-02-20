# 04. vLLM 설치 및 LLM 모델 배포

> **이 문서를 읽으면**: vLLM 엔진을 설치하고, 메인 모델(gpt-oss-120b)과 보조 모델(Qwen3-Coder-30B)을 GPU에 배포하여 OpenAI 호환 API 서버를 운영할 수 있습니다.
> **소요 시간**: 약 40분
> **선행 조건**: [03-Miniconda 설치 및 Python 환경 구성](./03-PYTHON-ENV.md)
> **관련 스크립트**: deploy/04_vllm_deploy.sh

---

## 목차

1. [vLLM이란?](#1-vllm이란)
2. [vLLM 설치](#2-vllm-설치)
3. [메인 모델 배포 (gpt-oss-120b)](#3-메인-모델-배포-gpt-oss-120b)
4. [보조 모델 배포 (Qwen3-Coder-30B) — 선택사항](#4-보조-모델-배포-qwen3-coder-30b--선택사항)
5. [모델 선택 히스토리](#5-모델-선택-히스토리)
6. [확인 체크리스트](#6-확인-체크리스트)

---

## 1. vLLM이란?

### 1-1. 개념 설명

vLLM은 대규모 언어 모델(LLM)을 **빠르고 효율적으로 서빙**하기 위한 오픈소스 추론 엔진입니다.

이름을 분해하면 다음과 같습니다.

| 구성 요소 | 의미 |
|-----------|------|
| **v** | Virtualized 또는 Very fast를 의미합니다 |
| **LLM** | Large Language Model (대규모 언어 모델)입니다 |

### 1-2. vLLM의 핵심 특징

| 특징 | 설명 |
|------|------|
| **OpenAI 호환 API** | ChatGPT API와 동일한 형식의 API를 제공합니다. 기존에 OpenAI API를 사용하던 코드를 URL만 변경하면 그대로 사용할 수 있습니다 |
| **PagedAttention** | GPU 메모리를 효율적으로 관리하는 기술입니다. 같은 GPU로 더 많은 요청을 동시에 처리할 수 있습니다 |
| **Tensor Parallelism** | 하나의 큰 모델을 여러 GPU에 나누어 실행합니다. 120B 파라미터 모델은 한 장의 GPU에 올라가지 않으므로, 4장의 GPU로 분산합니다 |
| **H100 최적화** | NVIDIA H100 GPU의 FP8 연산, NVLink 고속 통신 등을 활용하여 최적의 성능을 발휘합니다 |
| **연속 배치(Continuous Batching)** | 여러 사용자의 요청을 실시간으로 묶어 처리하여 응답 속도를 높입니다 |

### 1-3. 전체 구조에서의 위치

```
사용자 → Gradio 웹 UI (포트 7860) → vLLM API 서버 (포트 8000) → GPU에서 모델 추론
                                         ↑
                                    OpenAI 호환 API
                                    (POST /v1/chat/completions)
```

Gradio 앱이 사용자의 자연어 질문을 받아 프롬프트로 변환한 뒤, vLLM API에 요청을 보내면 vLLM이 GPU 위의 LLM 모델로 SQL을 생성하여 반환합니다.

---

## 2. vLLM 설치

vLLM은 `py312_sr` 가상환경에 설치합니다.

### 2-1. 환경 활성화 및 설치

```bash
conda activate py312_sr
pip install vllm
```

| 항목 | 설명 |
|------|------|
| **무엇을 하는 명령인가** | `py312_sr` 가상환경을 활성화한 후, pip으로 vLLM 패키지를 설치합니다. PyTorch, CUDA 관련 패키지 등 의존성도 함께 자동으로 설치됩니다 |
| **기대 결과** | 상당히 많은 패키지가 다운로드됩니다 (총 5~10GB 이상). 마지막에 `Successfully installed vllm-X.X.X ...` 메시지가 표시됩니다 |
| **실패 시 대처** | 메모리 부족 오류 — `pip install vllm --no-cache-dir`로 캐시 없이 설치합니다. CUDA 관련 오류 — `nvidia-smi`로 CUDA 버전을 확인하고, 호환되는 vLLM 버전을 지정하여 설치합니다 (예: `pip install vllm==0.6.6`) |

> **설치 시간 안내**: 네트워크 속도에 따라 10~30분 정도 소요될 수 있습니다. PyTorch와 CUDA 관련 패키지가 대용량이기 때문입니다.

### 2-2. 설치 확인

```bash
python -c "import vllm; print(vllm.__version__)"
```

| 항목 | 설명 |
|------|------|
| **무엇을 하는 명령인가** | Python에서 vLLM 모듈을 불러와 버전을 출력합니다 |
| **기대 결과** | `0.6.6` 등의 버전 번호가 출력됩니다 |
| **실패 시 대처** | `ModuleNotFoundError` — vLLM이 설치되지 않았거나 다른 가상환경에 있습니다. `which python`으로 현재 환경을 확인합니다 |

---

## 3. 메인 모델 배포 (gpt-oss-120b)

### 3-1. 모델 정보

| 항목 | 값 |
|------|-----|
| **모델 이름** | gpt-oss-120b |
| **모델 유형** | MoE (Mixture of Experts) |
| **파라미터 수** | 117B (1,170억 개) |
| **사용 GPU** | GPU 0, 1, 2, 3 (총 4장) |
| **병렬화 방식** | Tensor Parallelism 4 (TP=4) |
| **서비스 포트** | 8000 |
| **모델 저장 경로** | /install_file_backup/tessinu/gpt-oss-120b |
| **역할** | Oracle DB용 SQL 생성 (Text2SQL 메인 엔진) |

> **MoE(Mixture of Experts)란?**: 전체 117B 파라미터 중 실제로 동시에 활성화되는 파라미터는 일부입니다. "전문가(Expert)" 네트워크 여러 개 중 입력에 맞는 일부만 선택적으로 사용하므로, 파라미터 수 대비 연산량이 적고 속도가 빠릅니다.

### 3-2. 수동 시작 명령어

```bash
conda activate py312_sr

CUDA_VISIBLE_DEVICES=0,1,2,3 python -m vllm.entrypoints.openai.api_server \
    --model /install_file_backup/tessinu/gpt-oss-120b \
    --served-model-name gpt-oss-120b \
    --tensor-parallel-size 4 \
    --gpu-memory-utilization 0.92 \
    --max-model-len 16384 \
    --port 8000 \
    --trust-remote-code
```

| 항목 | 설명 |
|------|------|
| **무엇을 하는 명령인가** | vLLM의 OpenAI 호환 API 서버를 시작하여 gpt-oss-120b 모델을 서빙합니다 |
| **기대 결과** | 모델 로딩 로그가 출력된 후 `Uvicorn running on http://0.0.0.0:8000` 메시지가 표시됩니다. 모델 로딩에 2~5분 정도 소요됩니다 |
| **실패 시 대처** | `CUDA out of memory` — `--gpu-memory-utilization` 값을 낮춥니다 (예: 0.85). 모델 경로 오류 — `ls /install_file_backup/tessinu/gpt-oss-120b`로 모델 파일이 존재하는지 확인합니다. 포트 충돌 — `lsof -i :8000`으로 해당 포트를 사용 중인 프로세스를 확인하고 종료합니다 |

각 옵션의 의미는 다음과 같습니다.

| 옵션 | 값 | 설명 |
|------|-----|------|
| `CUDA_VISIBLE_DEVICES` | `0,1,2,3` | 사용할 GPU 번호를 지정합니다. GPU 0~3번을 사용합니다 |
| `--model` | 경로 | 로컬에 저장된 모델의 디렉토리 경로입니다 |
| `--served-model-name` | `gpt-oss-120b` | API에서 사용할 모델 이름입니다. 클라이언트가 이 이름으로 모델을 지정합니다 |
| `--tensor-parallel-size` | `4` | 모델을 4개의 GPU에 분산합니다. NVLink로 연결된 GPU 0~3을 사용하므로 최적의 성능을 발휘합니다 |
| `--gpu-memory-utilization` | `0.92` | GPU 메모리의 92%까지 사용합니다. 나머지 8%는 시스템 예비용입니다 |
| `--max-model-len` | `16384` | 한 번에 처리할 수 있는 최대 토큰 수입니다 (입력 + 출력 합산). 약 1만 6천 토큰입니다 |
| `--port` | `8000` | API 서버의 포트 번호입니다 |
| `--trust-remote-code` | - | 모델에 포함된 커스텀 코드의 실행을 허용합니다. 일부 모델은 이 옵션이 없으면 로딩에 실패합니다 |

> **주의**: 이 명령어를 실행하면 현재 터미널이 vLLM 서버 로그로 점유됩니다. 다른 작업을 하려면 새 SSH 세션을 열거나, `screen` 또는 `tmux`를 사용합니다. 운영 환경에서는 `systemd` 서비스로 등록하여 백그라운드에서 자동 실행되도록 설정합니다 (별도 문서 참조).

### 3-3. 동작 확인

새 터미널(SSH 세션)을 열고 다음 명령어를 실행합니다.

**모델 목록 확인:**

```bash
curl http://localhost:8000/v1/models
```

| 항목 | 설명 |
|------|------|
| **무엇을 하는 명령인가** | vLLM API 서버에 등록된 모델 목록을 조회합니다. OpenAI API의 `/v1/models` 엔드포인트와 동일합니다 |
| **기대 결과** | JSON 응답이 출력되며, `"id": "gpt-oss-120b"` 항목이 포함되어 있습니다 |
| **실패 시 대처** | `Connection refused` — vLLM 서버가 아직 시작되지 않았습니다. 서버 터미널에서 `Uvicorn running` 메시지가 나올 때까지 기다립니다. `curl: command not found` — `dnf install -y curl`로 curl을 설치합니다 |

기대 출력 예시:

```json
{
  "object": "list",
  "data": [
    {
      "id": "gpt-oss-120b",
      "object": "model",
      "created": 1700000000,
      "owned_by": "vllm"
    }
  ]
}
```

**실제 추론 테스트:**

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-oss-120b",
    "messages": [
      {"role": "user", "content": "SELECT 1 FROM DUAL을 설명해주세요"}
    ],
    "max_tokens": 200
  }'
```

| 항목 | 설명 |
|------|------|
| **무엇을 하는 명령인가** | vLLM API에 실제 추론 요청을 보내 모델이 정상적으로 응답하는지 확인합니다 |
| **기대 결과** | JSON 형식의 응답이 출력되며, `"choices"` 배열 안에 모델의 답변이 포함됩니다 |
| **실패 시 대처** | 응답이 매우 느리면(2분 이상) GPU 메모리나 서버 상태를 점검합니다. 오류 응답이 오면 서버 터미널의 로그를 확인합니다 |

---

## 4. 보조 모델 배포 (Qwen3-Coder-30B) — 선택사항

보조 모델은 메인 모델의 백업 또는 코드 생성 보조 용도로 사용합니다. **필수가 아닌 선택사항**이므로 필요한 경우에만 배포합니다.

### 4-1. 모델 정보

| 항목 | 값 |
|------|-----|
| **모델 이름** | Qwen3-Coder-30B-AWQ |
| **파라미터 수** | 30B (300억 개) |
| **양자화** | AWQ (4-bit) |
| **사용 GPU** | GPU 4 (1장) |
| **서비스 포트** | 8001 |
| **최대 컨텍스트 길이** | 32768 토큰 |
| **역할** | 코드 생성 보조, 메인 모델 대안 |

### 4-2. 수동 시작 명령어

```bash
conda activate py312_sr

CUDA_VISIBLE_DEVICES=4 python -m vllm.entrypoints.openai.api_server \
    --model /install_file_backup/tessinu/Qwen3-Coder-30B-AWQ \
    --served-model-name Qwen3-Coder-30B \
    --tensor-parallel-size 1 \
    --gpu-memory-utilization 0.92 \
    --max-model-len 32768 \
    --port 8001 \
    --trust-remote-code
```

| 항목 | 설명 |
|------|------|
| **무엇을 하는 명령인가** | GPU 4번에 Qwen3-Coder-30B 모델을 로딩하여 포트 8001에서 서빙합니다 |
| **기대 결과** | `Uvicorn running on http://0.0.0.0:8001` 메시지가 표시됩니다. 로딩에 1~3분 소요됩니다 |
| **실패 시 대처** | 메인 모델과 동일한 방법으로 대처합니다. GPU 번호(`CUDA_VISIBLE_DEVICES=4`)와 포트(`--port 8001`)가 메인 모델과 겹치지 않는지 확인합니다 |

메인 모델과의 주요 차이점:

| 옵션 | 메인 모델 | 보조 모델 | 이유 |
|------|-----------|-----------|------|
| `CUDA_VISIBLE_DEVICES` | 0,1,2,3 | 4 | GPU 4는 NVLink 미연결이므로 단독 사용합니다 |
| `--tensor-parallel-size` | 4 | 1 | GPU 1장으로 충분한 크기(30B, 4-bit 양자화)입니다 |
| `--max-model-len` | 16384 | 32768 | 보조 모델은 메모리 여유가 있어 더 긴 컨텍스트를 처리할 수 있습니다 |
| `--port` | 8000 | 8001 | 두 모델이 동시에 서빙되므로 포트를 분리합니다 |

### 4-3. 동작 확인

```bash
curl http://localhost:8001/v1/models
```

| 항목 | 설명 |
|------|------|
| **무엇을 하는 명령인가** | 보조 모델 API 서버의 모델 목록을 조회합니다 |
| **기대 결과** | `"id": "Qwen3-Coder-30B"` 항목이 포함된 JSON 응답이 출력됩니다 |
| **실패 시 대처** | 메인 모델의 동작 확인과 동일한 방법으로 대처합니다. 포트를 8001로 입력했는지 확인합니다 |

---

## 5. 모델 선택 히스토리

현재 사용 중인 gpt-oss-120b 모델에 도달하기까지 여러 모델을 테스트했습니다. 아래는 각 후보 모델의 평가 결과와 탈락 사유입니다.

### 5-1. 후보 모델 평가 요약

| 모델 | 장점 | 탈락 사유 | Oracle 호환성 |
|------|------|-----------|---------------|
| **SQLCoder** (Defog) | Text2SQL 전용 모델, 가벼움 | 2023년 출시된 구세대 모델입니다. 최신 SQL 문법과 복잡한 조인을 잘 처리하지 못합니다 | 낮음 |
| **Arctic-Text2SQL** (Snowflake) | BIRD 벤치마크 1위, 높은 정확도 | **SQLite 전용**으로 학습되어 Oracle 문법(ROWNUM, NVL, DECODE, 시퀀스 등)을 지원하지 않습니다 | 매우 낮음 |
| **EXAONE-Deep-32B** (LG AI Research) | 한국어 이해도 우수, Oracle 일부 지원 | 대형 스키마(테이블 50개 이상)를 프롬프트에 포함하면 **컨텍스트 길이 초과** 문제가 발생합니다 | 중간 |
| **gpt-oss-120b** | MoE 구조로 빠름, 범용 코드 생성 능력 우수 | (현재 사용 중) | **높음** |

### 5-2. 상세 평가

**SQLCoder (Defog)**

SQLCoder는 2023년에 출시된 Text2SQL 전용 모델입니다. 출시 당시에는 좋은 성능을 보였으나, 이후 범용 LLM들의 코드 생성 능력이 크게 향상되면서 상대적 우위를 잃었습니다. 특히 복잡한 서브쿼리나 윈도우 함수를 포함한 SQL 생성에서 오류율이 높았습니다.

**Arctic-Text2SQL (Snowflake)**

BIRD 벤치마크에서 1위를 달성한 고성능 모델입니다. 그러나 BIRD 벤치마크는 **SQLite** 데이터베이스를 기준으로 평가합니다. 이 모델은 SQLite 문법에 최적화되어 있어, Oracle 전용 문법을 사용하면 문법 오류가 빈번하게 발생했습니다.

Oracle과 SQLite의 주요 문법 차이:

| 기능 | Oracle | SQLite |
|------|--------|--------|
| 행 수 제한 | `ROWNUM <= 10` 또는 `FETCH FIRST 10 ROWS ONLY` | `LIMIT 10` |
| NULL 대체 | `NVL(컬럼, 기본값)` | `IFNULL(컬럼, 기본값)` |
| 조건 분기 | `DECODE(...)` 또는 `CASE WHEN` | `CASE WHEN` |
| 문자열 결합 | `||` 또는 `CONCAT()` | `||` |
| 날짜 함수 | `SYSDATE`, `TO_DATE(...)` | `date('now')` |

이러한 차이 때문에 Arctic-Text2SQL이 생성한 SQL은 Oracle에서 직접 실행할 수 없었습니다.

**EXAONE-Deep-32B (LG AI Research)**

한국어 이해도가 우수하고 Oracle 문법도 어느 정도 지원했습니다. 그러나 이 프로젝트의 Oracle 스키마는 테이블이 50개 이상이고, 각 테이블의 컬럼 설명까지 포함하면 프롬프트 길이가 매우 깁니다. EXAONE-Deep-32B의 컨텍스트 윈도우(약 8K~16K 토큰)로는 전체 스키마를 포함하는 프롬프트를 처리하지 못하여 **컨텍스트 길이 초과 오류**가 발생했습니다.

**gpt-oss-120b (최종 선택)**

4개 테스트 케이스(단순 조회, 조인, 서브쿼리, 집계 함수) 모두에서 Oracle 문법에 맞는 정확한 SQL을 생성했습니다 (**4/4 성공**). MoE 구조 덕분에 117B 파라미터 모델임에도 추론 속도가 빠르고, 충분한 컨텍스트 길이를 지원하여 대형 스키마도 처리할 수 있습니다.

### 5-3. 결론

```
Oracle 환경에서의 Text2SQL 정확도 비교

SQLCoder           ██░░░░░░░░  1/4 성공
Arctic-Text2SQL    █░░░░░░░░░  0/4 성공 (문법 비호환)
EXAONE-Deep-32B    ███░░░░░░░  2/4 성공 (컨텍스트 초과 실패 포함)
gpt-oss-120b       ██████████  4/4 성공 ★ 현재 사용 중
```

gpt-oss-120b는 Oracle 전용 SQL 생성에서 가장 안정적인 결과를 보여주었으며, 이 프로젝트의 메인 모델로 선정되었습니다.

---

## 6. 확인 체크리스트

다음 단계로 넘어가기 전에 모든 항목을 확인합니다.

| 순번 | 확인 항목 | 확인 명령어 | 기대 결과 |
|------|-----------|-------------|-----------|
| 1 | vLLM 설치 확인 | `conda activate py312_sr && python -c "import vllm; print(vllm.__version__)"` | 버전 번호 출력 |
| 2 | 메인 모델 파일 존재 | `ls /install_file_backup/tessinu/gpt-oss-120b` | 모델 파일 목록 출력 |
| 3 | 메인 모델 API 응답 | `curl http://localhost:8000/v1/models` | `gpt-oss-120b` 포함 JSON |
| 4 | 메인 모델 추론 테스트 | `curl -X POST http://localhost:8000/v1/chat/completions ...` | 모델 응답 JSON |
| 5 | (선택) 보조 모델 API 응답 | `curl http://localhost:8001/v1/models` | `Qwen3-Coder-30B` 포함 JSON |
| 6 | GPU 사용 상태 | `nvidia-smi` | GPU 0~3에 vllm 프로세스 표시 |

> **운영 참고**: 수동 시작 명령어는 테스트 및 디버깅 용도입니다. 서버 재부팅 시 자동으로 모델이 시작되도록 하려면 systemd 서비스로 등록해야 합니다. 이 내용은 별도 문서에서 다룹니다.

모든 항목이 확인되면 다음 문서로 진행합니다.

---
## 문서 탐색
| 이전 | 목차 | 다음 |
|------|------|------|
| [이전](./03-PYTHON-ENV.md) | [00-전체 안내](./00-INDEX.md) | [다음](./05-ORACLE-DB.md) |
