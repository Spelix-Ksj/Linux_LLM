# 11. 모델 추가, 교체, 비교 가이드

> **이 문서를 읽으면**: GPU 4에 새 LLM 모델을 추가하거나 기존 모델을 교체하고, 모델 간 성능을 비교할 수 있습니다.
> **소요 시간**: 약 25분
> **선행 조건**: [09-OPERATIONS (서버 운영 가이드)](./09-OPERATIONS.md)

---

## 목차

1. [현재 모델 구성](#1-현재-모델-구성)
2. [새 모델 추가하기 (GPU 4)](#2-새-모델-추가하기-gpu-4)
3. [MODEL_REGISTRY 설정 상세](#3-model_registry-설정-상세)
4. [모델 비교 테스트 방법](#4-모델-비교-테스트-방법)
5. [비활성화된 모델 목록](#5-비활성화된-모델-목록)
6. [Oracle SQL 전용 모델이 없는 이유](#6-oracle-sql-전용-모델이-없는-이유)

---

## 1. 현재 모델 구성

이 서버에는 두 개의 vLLM 인스턴스가 각각 다른 모델을 서빙하고 있습니다.

| 항목 | 메인 모델 | 테스트 모델 |
|------|-----------|------------|
| **모델키** | `gpt-oss-120b` | `qwen3-coder-30b` |
| **모델명** | gpt-oss-120b (117B MoE) | Qwen3-Coder-30B-A3B-Instruct |
| **파라미터** | 117B (MoE) | 30B (MoE, 활성 3B) |
| **GPU 할당** | GPU 0~3 (TP4) | GPU 4 |
| **포트** | 8000 | 8001 |
| **역할** | 메인 SQL 생성 | 테스트/비교용 |
| **상태** | active | active |
| **systemd 서비스** | `vllm.service` | `vllm-qwen3-coder.service` |
| **모델 파일 경로** | `/install_file_backup/tessinu/gpt-oss-120b` | (HuggingFace 또는 로컬) |
| **max_tokens** | 4096 | 4096 |

### 상태 확인 명령어

```bash
# 메인 모델 (GPT-OSS-120B)
systemctl status vllm
curl http://localhost:8000/v1/models

# 테스트 모델 (Qwen3-Coder)
systemctl status vllm-qwen3-coder
curl http://localhost:8001/v1/models
```

---

## 2. 새 모델 추가하기 (GPU 4)

GPU 4에서 실행 중인 테스트 모델을 교체하는 절차입니다. GPU 0~3은 메인 모델(GPT-OSS-120B)이 사용하므로 변경하지 않습니다.

### 전체 절차 요약

```
1. 기존 서비스 중지
2. 새 systemd 서비스 파일 생성
3. config.py의 MODEL_REGISTRY에 항목 추가
4. systemd 반영 및 서비스 시작
5. text2sql-ui 재시작
```

### 2-1. 기존 서비스 중지

현재 GPU 4에서 실행 중인 Qwen3-Coder 서비스를 중지합니다.

```bash
systemctl stop vllm-qwen3-coder
```

| 항목 | 설명 |
|------|------|
| **무엇을 하는 명령인지** | GPU 4에서 실행 중인 Qwen3-Coder vLLM 서비스를 중지합니다. |
| **기대 결과** | GPU 4의 메모리가 해제됩니다. `nvidia-smi`로 확인할 수 있습니다. |
| **주의사항** | 메인 모델(vllm 서비스, GPU 0~3)은 건드리지 않습니다. |

GPU 메모리가 해제되었는지 확인합니다.

```bash
nvidia-smi
```

GPU 4의 Memory-Usage가 거의 0이면 정상적으로 중지된 것입니다.

### 2-2. 새 서비스 파일 생성

새 모델을 위한 systemd 서비스 파일을 생성합니다. 아래 템플릿을 기반으로 수정합니다.

```bash
nano /etc/systemd/system/vllm-새모델명.service
```

**서비스 파일 템플릿**:

```ini
[Unit]
Description=vLLM 새모델명 Server
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root
Environment="PATH=/root/miniconda3/envs/py312_sr/bin:/usr/local/bin:/usr/bin"
Environment="HF_HOME=/root/.cache/huggingface"
Environment="CUDA_VISIBLE_DEVICES=4"
ExecStart=/root/miniconda3/envs/py312_sr/bin/python -m vllm.entrypoints.openai.api_server \
    --model /모델/파일/경로 \
    --gpu-memory-utilization 0.90 \
    --max-model-len 4096 \
    --host 0.0.0.0 \
    --port 8001
Restart=on-failure
RestartSec=10
TimeoutStartSec=600

[Install]
WantedBy=multi-user.target
```

**수정해야 하는 항목**:

| 항목 | 설명 | 예시 |
|------|------|------|
| `Description` | 서비스 설명 | `vLLM Qwen3-Coder Server` |
| `CUDA_VISIBLE_DEVICES` | 사용할 GPU 번호 | `4` (GPU 4만 사용) |
| `--model` | 모델 파일 경로 | `/install_file_backup/tessinu/모델명` 또는 HuggingFace ID |
| `--gpu-memory-utilization` | GPU 메모리 사용 비율 | `0.90` (90%) |
| `--max-model-len` | 최대 컨텍스트 길이 | `4096` (모델에 따라 조정) |
| `--port` | 서비스 포트 | `8001` |

> **참고**: 모델 크기에 따라 `--tensor-parallel-size` 옵션이 필요할 수 있습니다. GPU 4 하나만 사용한다면 이 옵션은 생략합니다(기본값 1). GPU 여러 장을 사용하는 경우에만 설정합니다.

### 2-3. config.py의 MODEL_REGISTRY에 항목 추가

```bash
nano /root/text2sql/app/config.py
```

`MODEL_REGISTRY` 딕셔너리에 새 모델 항목을 추가합니다.

```python
MODEL_REGISTRY = {
    # 기존 항목들...
    "gpt-oss-120b": { ... },
    "qwen3-coder-30b": { ... },  # 기존 모델은 주석 처리하거나 enabled=False로 변경

    # 새로 추가하는 모델
    "새모델키": {
        "display_name": "새 모델 표시 이름",
        "base_url": os.environ.get("VLLM_BASE_URL_1", "http://localhost:8001/v1"),
        "model_name": "vLLM에서 서빙하는 모델명",
        "gpu_info": "GPU 4",
        "description": "모델에 대한 간단한 설명",
        "max_tokens": 4096,
        "enabled": True,
    },
}
```

> **중요**: `model_name` 값은 vLLM 서비스 파일의 `--model` 옵션에 지정한 경로/이름과 정확히 일치해야 합니다. `curl http://localhost:8001/v1/models` 명령으로 반환되는 모델 ID와 동일한 값을 입력합니다.

### 2-4. systemd 반영 및 서비스 시작

```bash
# systemd 설정 새로 읽기 (새 서비스 파일 인식)
systemctl daemon-reload

# 새 서비스 시작
systemctl start vllm-새모델명

# 서비스 상태 확인
systemctl status vllm-새모델명
```

모델 로딩이 완료될 때까지 기다립니다 (약 1~5분).

```bash
# 모델 로딩 완료 확인
curl http://localhost:8001/v1/models
```

JSON 응답이 오면 로딩이 완료된 것입니다.

### 2-5. text2sql-ui 재시작

config.py를 수정했으므로 웹 UI를 재시작하여 새 모델이 드롭다운에 표시되도록 합니다.

```bash
systemctl restart text2sql-ui
```

### 2-6. 부팅 시 자동 시작 설정 (선택)

서버 재부팅 시 새 서비스가 자동으로 시작되도록 설정합니다.

```bash
systemctl enable vllm-새모델명
```

---

## 3. MODEL_REGISTRY 설정 상세

`config.py`의 `MODEL_REGISTRY`는 시스템에서 사용할 수 있는 모든 LLM 모델을 정의합니다.

### 필수 필드

| 필드명 | 타입 | 필수 | 설명 | 예시 |
|--------|------|------|------|------|
| `display_name` | str | 필수 | 웹 UI 드롭다운에 표시되는 이름 | `"GPT-OSS 120B (메인 추론 모델)"` |
| `base_url` | str | 필수 | vLLM 서버의 API 엔드포인트 URL | `"http://localhost:8000/v1"` |
| `model_name` | str | 필수 | vLLM에서 서빙하는 모델의 ID (경로 또는 이름) | `"/install_file_backup/tessinu/gpt-oss-120b"` |
| `gpu_info` | str | 필수 | 사용하는 GPU 정보 | `"GPU 0-3 (TP4)"` |
| `description` | str | 필수 | 모델에 대한 간단한 설명 | `"OpenAI 범용 추론 모델 (MoE 117B)"` |
| `max_tokens` | int | 필수 | LLM 응답의 최대 토큰 수 | `4096` |
| `enabled` | bool | 필수 | 모델 활성화 여부. `False`이면 웹 UI에 표시되지 않음 | `True` |

### model_name 확인 방법

`model_name` 값은 vLLM이 서빙하는 모델의 정확한 ID와 일치해야 합니다. 아래 명령으로 확인할 수 있습니다.

```bash
curl http://localhost:8001/v1/models
```

응답에서 `"id"` 값을 `model_name`으로 사용합니다.

```json
{
  "data": [
    {
      "id": "Qwen3-Coder-30B-A3B-Instruct",   <-- 이 값을 model_name으로 사용
      "object": "model"
    }
  ]
}
```

### 모델 비활성화 방법

모델을 제거하지 않고 비활성화하려면 두 가지 방법이 있습니다.

**방법 1**: `enabled: False`로 변경

```python
"qwen3-coder-30b": {
    ...
    "enabled": False,  # False로 변경하면 웹 UI에서 숨겨짐
},
```

**방법 2**: 항목 전체를 주석 처리

```python
# "qwen3-coder-30b": {
#     ...
# },
```

두 가지 모두 변경 후 `systemctl restart text2sql-ui`를 실행해야 적용됩니다.

---

## 4. 모델 비교 테스트 방법

### 비교 프로토콜

동일한 조건에서 두 모델의 SQL 생성 품질을 공정하게 비교하기 위한 절차입니다.

#### 사전 준비

1. 두 모델 모두 정상 서빙 상태인지 확인합니다.

```bash
curl http://localhost:8000/v1/models   # GPT-OSS-120B
curl http://localhost:8001/v1/models   # 비교 대상 모델
```

2. 테스트 질문 목록을 준비합니다 (5개 이상 권장).

#### 비교 테스트 진행

1. 웹 UI에서 모델 A를 선택합니다.
2. 준비한 질문을 하나씩 입력하고 결과를 기록합니다.
3. 모델 B로 전환합니다.
4. 같은 질문을 같은 순서로 다시 입력하고 결과를 기록합니다.

#### 평가 항목

각 질문에 대해 아래 5가지 항목을 평가합니다.

| 항목 | 평가 기준 | 점수 |
|------|-----------|------|
| **SQL 정확성** | 질문 의도를 정확히 반영했는지 | 0~2 |
| **Oracle 호환성** | Oracle 전용 문법을 올바르게 사용했는지 | 0~1 |
| **한글 별칭** | 출력 컬럼에 한글 AS 별칭을 붙였는지 | 0~1 |
| **실행 성공** | 오류 없이 SQL이 실행되었는지 | 0~1 |
| **보고서 품질** | 결과 보고서가 유용하고 정확한지 | 0~1 |

#### 결과 기록 템플릿

```
=== 모델 비교 테스트 결과 ===
테스트 일시: YYYY-MM-DD HH:MM
테스트 질문 수: N개

| 질문 | 모델 A 점수 | 모델 B 점수 | 비고 |
|------|------------|------------|------|
| Q1   |     /6     |     /6     |      |
| Q2   |     /6     |     /6     |      |
| ...  |     /6     |     /6     |      |
| 합계 |     /N*6   |     /N*6   |      |

결론: 모델 A / 모델 B가 더 적합
이유: ...
```

---

## 5. 비활성화된 모델 목록

아래 모델들은 테스트를 거친 후 현재 비활성화(주석 처리)되어 있습니다.

### Arctic-Text2SQL-R1-7B

| 항목 | 값 |
|------|-----|
| **모델명** | Snowflake Arctic-Text2SQL-R1-7B |
| **파라미터** | 7B |
| **비활성화 이유** | **SQLite 전용 모델**. BIRD 벤치마크에서 68.9% 정확도를 기록했으나, 학습 데이터가 SQLite 문법 기반입니다. Oracle SQL 문법(ROWNUM, FETCH FIRST, DUAL, 스키마 접두사 등)을 이해하지 못하여 생성된 SQL이 Oracle에서 실행 오류를 발생시킵니다. |
| **대안** | GPT-OSS-120B (범용 모델로 Oracle 문법 생성 가능) |

### EXAONE-Deep-32B

| 항목 | 값 |
|------|-----|
| **모델명** | LG AI Research EXAONE-Deep-32B |
| **파라미터** | 32B |
| **비활성화 이유** | **컨텍스트 길이 초과 문제**. 시스템 프롬프트에 테이블 스키마 정보(4개 테이블의 전체 컬럼 정보)를 포함하면 입력 토큰이 모델의 컨텍스트 제한을 초과합니다. `max_tokens`를 1024로 줄여도 긴 SQL 생성 시 잘림 현상이 발생합니다. |
| **대안** | Qwen3-Coder-30B (MoE 구조로 효율적 컨텍스트 처리) |

### Qwen3-30B-A3B (비코더 버전)

| 항목 | 값 |
|------|-----|
| **모델명** | Qwen3-30B-A3B-Thinking |
| **파라미터** | 30B (MoE, 활성 3B) |
| **비활성화 이유** | Qwen3-Coder 버전이 코딩/SQL 생성에 더 특화되어 있어, 동일 리소스(GPU 4) 사용 시 Coder 버전이 더 나은 성능을 보입니다. GPU 4 교체용으로 준비되어 있으나, 현재는 Qwen3-Coder가 활성화되어 있습니다. |
| **대안** | Qwen3-Coder-30B-A3B-Instruct (현재 활성화) |

---

## 6. Oracle SQL 전용 모델이 없는 이유

### Text2SQL 벤치마크의 한계

현재 주요 Text2SQL 벤치마크(BIRD, Spider)는 모두 **SQLite**를 기반으로 합니다.

| 벤치마크 | DB 엔진 | 평가 방식 |
|----------|---------|-----------|
| BIRD | SQLite | 실행 정확도 (EX) |
| Spider | SQLite | 정확 일치 (EM) + 실행 정확도 (EX) |

이로 인해 Text2SQL에 특화된 모델들(Arctic-Text2SQL, NSQL, SQLCoder 등)은 SQLite 문법에 최적화되어 있습니다.

### SQLite와 Oracle의 주요 차이점

| 기능 | SQLite | Oracle |
|------|--------|--------|
| 행 수 제한 | `LIMIT N` | `FETCH FIRST N ROWS ONLY` 또는 `ROWNUM` |
| 문자열 결합 | `||` | `||` 또는 `CONCAT()` |
| 자동 증가 | `AUTOINCREMENT` | `SEQUENCE` + `TRIGGER` |
| 날짜 함수 | `date()`, `strftime()` | `TO_DATE()`, `SYSDATE` |
| 스키마 접두사 | 불필요 | `스키마명.테이블명` 필수 |
| DUAL 테이블 | 없음 | `SELECT ... FROM DUAL` |
| NVL 함수 | `IFNULL()` 또는 `COALESCE()` | `NVL()` |

### 현재 시스템의 해결 방법

이 시스템은 Text2SQL 전용 모델 대신 **범용 대규모 모델**(GPT-OSS-120B)을 사용합니다. 범용 모델은 Oracle 문법을 포함한 다양한 SQL 방언을 학습하고 있어, 시스템 프롬프트에서 Oracle 규칙을 명시하면 올바른 Oracle SQL을 생성할 수 있습니다.

시스템 프롬프트(`text2sql_pipeline.py`)에 포함된 Oracle 전용 규칙:

```
1. Oracle SQL 문법만 사용
2. SELECT 문만 생성 (INSERT/UPDATE/DELETE/DROP 절대 금지)
3. SQL 끝에 세미콜론(;) 붙이지 않기
4. LIMIT 대신 ROWNUM 또는 FETCH FIRST N ROWS ONLY 사용
5. 스키마 접두사 HRAI_CON. 을 테이블명 앞에 붙이기
```

이 방식은 Text2SQL 전용 소형 모델보다 Oracle SQL 생성 정확도가 높은 것으로 확인되었습니다.

---

## 문서 탐색
| 이전 | 목차 | 다음 |
|------|------|------|
| [10-TROUBLESHOOTING](./10-TROUBLESHOOTING.md) | [00-전체 안내](./00-INDEX.md) | [99-REFERENCE](./99-REFERENCE.md) |
