# 07. systemd 서비스 등록 및 자동화

> **이 문서를 읽으면**: vLLM과 Text2SQL 웹 UI를 systemd 서비스로 등록하여, 서버 재부팅 시 자동으로 시작되도록 설정할 수 있습니다.
> **소요 시간**: 약 25분
> **선행 조건**: [06-APP-DEPLOY.md](./06-APP-DEPLOY.md)
> **관련 스크립트**: deploy/07_services.sh

---

## 1. systemd란?

**systemd**는 Linux에서 백그라운드 프로세스(서비스)를 관리하는 시스템입니다.

Windows에 익숙하다면 아래 비교를 참고합니다.

| 개념 | Windows | Linux (systemd) |
|------|---------|-----------------|
| 서비스 관리 도구 | 서비스(services.msc) | `systemctl` 명령어 |
| 서비스 설정 파일 | 레지스트리 | `/etc/systemd/system/` 폴더의 `.service` 파일 |
| 서비스 시작 | "시작" 버튼 클릭 | `systemctl start 서비스명` |
| 서비스 중지 | "중지" 버튼 클릭 | `systemctl stop 서비스명` |
| 자동 시작 설정 | "자동" 시작 유형 선택 | `systemctl enable 서비스명` |

> **왜 서비스로 등록합니까?**
> 수동 실행(`python app.py`)은 터미널을 닫으면 프로그램도 종료됩니다.
> 서비스로 등록하면 다음 세 가지가 보장됩니다:
> 1. 서버가 재부팅되어도 **자동으로 시작**됩니다.
> 2. 프로그램이 비정상 종료되면 **자동으로 재시작**됩니다.
> 3. 터미널을 닫아도 **백그라운드에서 계속 실행**됩니다.

---

## 2. 서비스 파일 구조 이해

systemd 서비스 파일은 세 개의 섹션으로 구성됩니다. 각 섹션의 역할을 알아봅니다.

```ini
[Unit]
# 서비스에 대한 설명과 의존 관계를 정의합니다
Description=서비스 설명
After=network.target    # 네트워크가 준비된 후에 시작합니다

[Service]
# 서비스가 실행할 명령과 동작 방식을 정의합니다
ExecStart=/usr/bin/python app.py    # 실행할 명령어
WorkingDirectory=/root/text2sql/app # 작업 디렉토리
Environment="KEY=VALUE"             # 환경변수 설정
Restart=on-failure                  # 오류 시 자동 재시작
RestartSec=10                       # 재시작 전 대기 시간(초)

[Install]
# 서비스 활성화(enable) 시 적용되는 설정입니다
WantedBy=multi-user.target    # 서버 부팅 시 자동 시작
```

### 주요 옵션 상세 설명

| 옵션 | 위치 | 설명 |
|------|------|------|
| `Description` | [Unit] | 사람이 읽기 위한 서비스 설명입니다. `systemctl status`에서 표시됩니다 |
| `After` | [Unit] | 이 서비스보다 **먼저** 시작되어야 하는 서비스를 지정합니다 |
| `ExecStart` | [Service] | 서비스가 시작될 때 실행할 명령어입니다. **반드시 절대 경로**로 작성합니다 |
| `WorkingDirectory` | [Service] | 명령어가 실행될 디렉토리입니다. `cd` 후 실행하는 것과 같습니다 |
| `Environment` | [Service] | 서비스 실행 시 적용할 환경변수입니다 |
| `Restart` | [Service] | `on-failure`이면 오류로 종료될 때만, `always`이면 항상 재시작합니다 |
| `RestartSec` | [Service] | 재시작 전 대기 시간(초)입니다. 너무 빠른 재시작 반복을 방지합니다 |
| `WantedBy` | [Install] | `multi-user.target`은 "일반적인 서버 부팅 상태"를 의미합니다 |

---

## 3. vLLM 메인 서비스 (vllm.service)

vLLM 메인 서비스는 Text2SQL의 핵심 LLM 모델을 제공합니다. 포트 `8000`에서 동작합니다.

### 3.1 서비스 파일 전문

```ini
[Unit]
Description=vLLM Main Inference Server (GPU 0-3, Port 8000)
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/text2sql
Environment="PATH=/root/miniconda3/envs/text2sql/bin:/usr/local/bin:/usr/bin:/bin"
Environment="CUDA_VISIBLE_DEVICES=0,1,2,3"
ExecStart=/root/miniconda3/envs/text2sql/bin/python -m vllm.entrypoints.openai.api_server \
    --model /root/models/main-model \
    --host 0.0.0.0 \
    --port 8000 \
    --tensor-parallel-size 4 \
    --gpu-memory-utilization 0.90 \
    --max-model-len 16384
Restart=on-failure
RestartSec=30
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
```

### 3.2 각 라인 설명

| 라인 | 설명 |
|------|------|
| `Description=vLLM Main...` | 이 서비스가 vLLM 메인 서버임을 나타냅니다. GPU 0-3번, 포트 8000을 사용합니다 |
| `After=network.target` | 네트워크가 준비된 후에 시작합니다. DB나 외부 API 접속이 필요하기 때문입니다 |
| `Type=simple` | 명령어를 실행하면 바로 서비스가 시작된 것으로 간주합니다 |
| `Environment="PATH=..."` | conda 가상환경의 Python을 사용하기 위해 PATH를 직접 지정합니다 |
| `Environment="CUDA_VISIBLE_DEVICES=0,1,2,3"` | GPU 4개(0, 1, 2, 3번)를 사용하도록 설정합니다 |
| `--model /root/models/main-model` | 로드할 모델의 경로입니다 |
| `--host 0.0.0.0` | 모든 네트워크 인터페이스에서 접속을 허용합니다 |
| `--port 8000` | API 서버 포트를 8000으로 설정합니다 |
| `--tensor-parallel-size 4` | 모델을 GPU 4개에 분산하여 로드합니다 |
| `--gpu-memory-utilization 0.90` | GPU 메모리의 90%까지 사용합니다 |
| `--max-model-len 16384` | 최대 입출력 토큰 길이를 16,384로 제한합니다 |
| `Restart=on-failure` | 오류로 종료되면 자동 재시작합니다 |
| `RestartSec=30` | 재시작 전 30초 대기합니다 (모델 언로드 시간 확보) |
| `LimitNOFILE=65536` | 열 수 있는 최대 파일 수를 65,536으로 늘립니다 |

### 3.3 서비스 설치 및 시작

```bash
# 1. 서비스 파일을 systemd 디렉토리에 복사
cp /root/text2sql/services/vllm.service /etc/systemd/system/

# 2. systemd에 새 서비스 파일을 인식시킴
systemctl daemon-reload

# 3. 부팅 시 자동 시작 설정
systemctl enable vllm

# 4. 서비스 시작
systemctl start vllm
```

| 명령어 | 설명 |
|--------|------|
| `cp ... /etc/systemd/system/` | 서비스 파일을 systemd가 읽는 폴더에 복사합니다 |
| `systemctl daemon-reload` | 변경된 서비스 파일을 systemd가 다시 읽습니다. **파일 수정 후 반드시 실행**합니다 |
| `systemctl enable vllm` | 서버 재부팅 시 자동 시작을 활성화합니다 |
| `systemctl start vllm` | 서비스를 지금 바로 시작합니다 |

> **중요: 모델 로딩에 2~5분이 소요됩니다**
> `systemctl start vllm`을 실행한 직후에는 서비스가 "active"로 표시되지만,
> 모델이 GPU에 완전히 로드되기까지 **2~5분**이 걸립니다.
> 이 시간 동안 API 요청을 보내면 오류가 발생합니다.

---

## 4. vLLM 보조 서비스 (vllm-qwen3-coder.service)

보조 모델(Qwen3 Coder)을 별도의 vLLM 인스턴스로 실행합니다.

### 4.1 서비스 파일 전문

```ini
[Unit]
Description=vLLM Qwen3-Coder Service (GPU 4, Port 8001)
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/text2sql
Environment="PATH=/root/miniconda3/envs/text2sql/bin:/usr/local/bin:/usr/bin:/bin"
Environment="CUDA_VISIBLE_DEVICES=4"
ExecStart=/root/miniconda3/envs/text2sql/bin/python -m vllm.entrypoints.openai.api_server \
    --model /root/models/qwen3-coder \
    --host 0.0.0.0 \
    --port 8001 \
    --gpu-memory-utilization 0.90 \
    --max-model-len 32768
Restart=on-failure
RestartSec=30
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
```

### 4.2 메인 서비스와의 차이점

| 항목 | 메인 (vllm) | 보조 (vllm-qwen3-coder) |
|------|------------|------------------------|
| GPU | 0, 1, 2, 3 (4개) | 4 (1개) |
| 포트 | 8000 | 8001 |
| tensor-parallel-size | 4 | 미지정 (기본값 1) |
| max-model-len | 16384 | **32768** (코드 생성용으로 더 긴 컨텍스트) |

### 4.3 서비스 설치 및 시작

```bash
cp /root/text2sql/services/vllm-qwen3-coder.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable vllm-qwen3-coder
systemctl start vllm-qwen3-coder
```

---

## 5. Gradio 웹 UI 서비스 (text2sql-ui.service)

Text2SQL 웹 UI를 서비스로 등록합니다.

### 5.1 서비스 파일 전문

```ini
[Unit]
Description=Text2SQL Gradio Web UI (Port 7860)
After=network.target vllm.service

[Service]
Type=simple
User=root
WorkingDirectory=/root/text2sql/app
Environment="PATH=/root/miniconda3/envs/text2sql/bin:/usr/local/bin:/usr/bin:/bin"
EnvironmentFile=/root/text2sql/app/.env
ExecStart=/root/miniconda3/envs/text2sql/bin/python app.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### 5.2 핵심 포인트: vllm.service 의존성

```ini
After=network.target vllm.service
```

이 줄은 `text2sql-ui` 서비스가 `vllm` 서비스 **이후에** 시작되도록 지정합니다. Text2SQL 웹 UI는 vLLM 서버가 동작 중이어야 정상 작동하므로, 이 의존성이 중요합니다.

> **주의: `After`는 "시작 순서"만 지정합니다**
> `After=vllm.service`는 vllm이 "시작 명령을 받은 후"에 text2sql-ui를 시작한다는 의미입니다.
> vllm의 모델 로딩이 **완료될 때까지 기다리지는 않습니다**.
> 따라서 모델 로딩 완료 후에 text2sql-ui를 시작하려면 수동으로 순서를 관리해야 합니다.
> (6절의 서비스 시작 순서를 참고합니다.)

### 5.3 서비스 설치 및 시작

```bash
cp /root/text2sql/services/text2sql-ui.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable text2sql-ui
systemctl start text2sql-ui
```

---

## 6. 서비스 시작 순서

세 개의 서비스를 올바른 순서로 시작하는 전체 절차입니다.

```
 ┌──────────────────────────────────────────────────────────┐
 │  [1단계] vLLM 서비스 시작 (두 서비스 동시에 시작)          │
 │                                                          │
 │    systemctl start vllm                                  │
 │    systemctl start vllm-qwen3-coder                      │
 └────────────────────┬─────────────────────────────────────┘
                      │
                      │  2~5분 대기 (모델이 GPU에 로드되는 시간)
                      │
 ┌────────────────────▼─────────────────────────────────────┐
 │  [2단계] 모델 로딩 완료 확인                               │
 │                                                          │
 │    curl http://localhost:8000/v1/models                   │
 │                                                          │
 │    → 정상: {"data": [{"id": "모델명", ...}]}              │
 │    → 미완료: 연결 실패 또는 빈 목록                         │
 └────────────────────┬─────────────────────────────────────┘
                      │
                      │  모델 목록이 정상 출력되면 다음 단계로
                      │
 ┌────────────────────▼─────────────────────────────────────┐
 │  [3단계] Text2SQL 웹 UI 시작                              │
 │                                                          │
 │    systemctl start text2sql-ui                            │
 └────────────────────┬─────────────────────────────────────┘
                      │
 ┌────────────────────▼─────────────────────────────────────┐
 │  [4단계] 전체 상태 확인                                    │
 │                                                          │
 │    systemctl status vllm                                  │
 │    systemctl status vllm-qwen3-coder                      │
 │    systemctl status text2sql-ui                           │
 │                                                          │
 │    → 세 서비스 모두 "active (running)" 이면 정상            │
 └──────────────────────────────────────────────────────────┘
```

### 전체 시작 명령 요약

아래 명령을 순서대로 실행합니다.

```bash
# [1단계] vLLM 서비스 시작
systemctl start vllm
systemctl start vllm-qwen3-coder

# [2단계] 모델 로딩 대기 (2~5분 후 확인)
echo "모델 로딩 중... 2~5분 후 아래 명령으로 확인합니다."
sleep 180    # 3분 대기

# 모델 로딩 확인 (정상이면 모델 목록이 출력됨)
curl http://localhost:8000/v1/models
curl http://localhost:8001/v1/models

# [3단계] 웹 UI 시작
systemctl start text2sql-ui

# [4단계] 전체 상태 확인
systemctl status vllm --no-pager
systemctl status vllm-qwen3-coder --no-pager
systemctl status text2sql-ui --no-pager
```

---

## 7. 서비스 관리 명령어 빠른 참조

일상적으로 자주 사용하는 명령어를 정리합니다.

### 7.1 기본 명령어

| 명령어 | 설명 |
|--------|------|
| `systemctl start 서비스명` | 서비스를 시작합니다 |
| `systemctl stop 서비스명` | 서비스를 중지합니다 |
| `systemctl restart 서비스명` | 서비스를 중지 후 다시 시작합니다 |
| `systemctl status 서비스명` | 서비스의 현재 상태를 확인합니다 |
| `systemctl enable 서비스명` | 부팅 시 자동 시작을 활성화합니다 |
| `systemctl disable 서비스명` | 부팅 시 자동 시작을 비활성화합니다 |

> **`서비스명`에는 `.service`를 생략해도 됩니다.**
> `systemctl start vllm`과 `systemctl start vllm.service`는 동일합니다.

### 7.2 로그 확인 명령어

문제가 발생했을 때 로그를 확인하는 방법입니다.

```bash
# 특정 서비스의 로그 보기
journalctl -u vllm --no-pager -n 50

# 실시간 로그 보기 (새 로그가 자동으로 표시됨, Ctrl+C로 종료)
journalctl -u vllm -f

# 오늘 날짜의 로그만 보기
journalctl -u vllm --since today --no-pager
```

| 옵션 | 설명 |
|------|------|
| `-u 서비스명` | 특정 서비스의 로그만 필터링합니다 |
| `--no-pager` | 한 번에 전체 출력합니다 (페이지 나눔 없이) |
| `-n 50` | 최근 50줄만 출력합니다 |
| `-f` | 실시간으로 새 로그를 계속 출력합니다 (tail -f와 유사) |
| `--since today` | 오늘 날짜의 로그만 출력합니다 |

### 7.3 서비스 파일 수정 후 적용

서비스 파일(`.service`)을 수정한 경우 반드시 아래 명령을 실행해야 변경사항이 적용됩니다.

```bash
# 1. systemd에 변경사항 알림
systemctl daemon-reload

# 2. 서비스 재시작
systemctl restart 서비스명
```

> **`daemon-reload`를 잊으면?**
> 수정 전의 이전 설정으로 서비스가 실행됩니다.
> 서비스 파일을 수정한 후에는 항상 `daemon-reload`를 먼저 실행합니다.

### 7.4 전체 서비스 한 번에 확인

세 서비스의 상태를 한 번에 확인하는 명령입니다.

```bash
systemctl status vllm vllm-qwen3-coder text2sql-ui --no-pager
```

---

## 8. 확인 체크리스트

아래 항목을 모두 완료했는지 확인합니다.

```
[ ] systemd의 역할과 서비스 파일 구조([Unit], [Service], [Install]) 이해 완료
[ ] vllm.service 파일 → /etc/systemd/system/에 복사 완료
[ ] vllm-qwen3-coder.service 파일 → /etc/systemd/system/에 복사 완료
[ ] text2sql-ui.service 파일 → /etc/systemd/system/에 복사 완료
[ ] systemctl daemon-reload 실행 완료
[ ] 세 서비스 모두 enable(자동 시작) 설정 완료
[ ] 서비스 시작 순서(vLLM → 모델 로딩 확인 → 웹 UI) 이해 완료
[ ] curl localhost:8000/v1/models 으로 모델 로딩 확인 완료
[ ] systemctl status로 세 서비스 모두 "active (running)" 확인 완료
[ ] journalctl -u 서비스명 으로 로그 확인 방법 이해 완료
```

---
## 문서 탐색
| 이전 | 목차 | 다음 |
|------|------|------|
| [06-APP-DEPLOY](./06-APP-DEPLOY.md) | [00-전체 안내](./00-INDEX.md) | [08-TESTING](./08-TESTING.md) |
