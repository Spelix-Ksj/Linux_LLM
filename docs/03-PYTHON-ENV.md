# 03. Miniconda 설치 및 Python 환경 구성

> **이 문서를 읽으면**: Miniconda를 설치하고, Text2SQL 프로젝트에 필요한 두 개의 Python 가상환경을 생성하여 패키지 의존성 충돌 없이 개발 환경을 구축할 수 있습니다.
> **소요 시간**: 약 20분
> **선행 조건**: [02-서버 환경 확인 및 기본 설정](./02-SERVER-SETUP.md)
> **관련 스크립트**: deploy/03_python_env.sh

---

## 목차

1. [Miniconda란?](#1-miniconda란)
2. [Miniconda 다운로드 및 설치](#2-miniconda-다운로드-및-설치)
3. [가상환경 생성](#3-가상환경-생성)
4. [환경 관리 명령어 요약](#4-환경-관리-명령어-요약)
5. [확인 체크리스트](#5-확인-체크리스트)

---

## 1. Miniconda란?

### 1-1. 개념 설명

Miniconda는 **Python 패키지 관리**와 **가상환경 관리**를 동시에 수행하는 도구입니다.

이름을 분해하면 이해하기 쉽습니다.

| 구성 요소 | 의미 |
|-----------|------|
| **Mini** | 최소 설치 버전이라는 뜻입니다. 필요한 것만 설치하므로 가볍습니다 |
| **conda** | 패키지와 환경을 관리하는 핵심 도구의 이름입니다 |

### 1-2. 왜 Miniconda를 사용하는가?

리눅스 서버에는 시스템용 Python이 이미 설치되어 있습니다. 그런데 왜 별도로 Miniconda를 설치할까요?

| 문제 상황 | Miniconda의 해결 방법 |
|-----------|----------------------|
| 시스템 Python을 건드리면 OS 기능이 망가질 수 있습니다 | 별도의 Python을 설치하여 시스템과 완전히 분리합니다 |
| 프로젝트마다 필요한 Python 버전이 다릅니다 | 가상환경별로 서로 다른 Python 버전을 사용할 수 있습니다 |
| 패키지 A가 요구하는 라이브러리 버전과 패키지 B가 요구하는 버전이 충돌합니다 | 가상환경을 분리하여 각 환경에 독립적인 패키지를 설치합니다 |

### 1-3. 가상환경의 비유

가상환경은 **독립된 작업 공간**이라고 생각하면 됩니다.

```
서버 (한 대의 컴퓨터)
├── 시스템 Python ← 건드리지 않습니다
├── Miniconda
│   ├── text2sql 환경 (Python 3.11) ← Gradio 앱 전용
│   └── py312_sr 환경 (Python 3.12) ← vLLM 전용
```

각 환경은 서로 영향을 주지 않습니다. `text2sql` 환경에서 패키지를 설치하거나 삭제해도 `py312_sr` 환경에는 아무런 변화가 없습니다.

---

## 2. Miniconda 다운로드 및 설치

### 2-1. 설치 파일 다운로드

```bash
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
```

| 항목 | 설명 |
|------|------|
| **무엇을 하는 명령인가** | Anaconda 공식 저장소에서 Miniconda 최신 설치 파일(약 120MB)을 다운로드합니다 |
| **기대 결과** | 현재 디렉토리에 `Miniconda3-latest-Linux-x86_64.sh` 파일이 생성됩니다. `100%` 진행률 표시와 함께 다운로드가 완료됩니다 |
| **실패 시 대처** | `Resolving failed` — DNS 문제입니다. `ping repo.anaconda.com`으로 연결 가능한지 확인합니다. 다운로드 속도가 너무 느리면 `-q` 옵션을 추가하여 `wget -q ...`로 실행하면 출력이 간소화됩니다 |

### 2-2. 설치 실행

```bash
bash Miniconda3-latest-Linux-x86_64.sh -b -p /root/miniconda3
```

| 항목 | 설명 |
|------|------|
| **무엇을 하는 명령인가** | Miniconda를 `/root/miniconda3` 경로에 설치합니다 |
| **기대 결과** | 여러 줄의 설치 로그가 출력된 후 마지막에 `Thank you for installing Miniconda3!` 메시지가 표시됩니다 |
| **실패 시 대처** | `already exists` — 이미 설치되어 있는 경우입니다. 기존 설치를 사용하거나 `rm -rf /root/miniconda3`로 삭제 후 재설치합니다. 권한 오류 — `root` 계정으로 접속했는지 확인합니다 |

옵션 설명:

| 옵션 | 의미 |
|------|------|
| `-b` | **batch 모드**입니다. 라이선스 동의 등의 대화형 질문을 건너뛰고 자동으로 설치합니다 |
| `-p /root/miniconda3` | **설치 경로를 지정**합니다. `/root/miniconda3`에 설치합니다 |

### 2-3. 쉘 초기화 및 적용

```bash
/root/miniconda3/bin/conda init bash && source ~/.bashrc
```

| 항목 | 설명 |
|------|------|
| **무엇을 하는 명령인가** | `conda init bash`는 bash 쉘 설정 파일(`~/.bashrc`)에 conda 초기화 코드를 추가합니다. `source ~/.bashrc`는 변경된 설정을 현재 세션에 즉시 적용합니다 |
| **기대 결과** | 명령 프롬프트 앞에 `(base)`가 표시됩니다. 예: `(base) [root@server ~]#` |
| **실패 시 대처** | 프롬프트에 `(base)`가 나타나지 않으면 터미널을 완전히 닫고 SSH를 다시 접속합니다 |

> **`(base)`란?**: conda가 활성화되면 기본적으로 `base`라는 기본 환경이 활성화됩니다. 괄호 안의 이름은 현재 활성화된 가상환경을 나타냅니다.

### 2-4. 설치 파일 정리

```bash
rm -f Miniconda3-latest-Linux-x86_64.sh
```

| 항목 | 설명 |
|------|------|
| **무엇을 하는 명령인가** | 다운로드한 설치 파일을 삭제합니다. 설치가 완료되었으므로 더 이상 필요하지 않습니다 |
| **기대 결과** | 아무런 출력 없이 파일이 삭제됩니다 |
| **실패 시 대처** | `No such file` — 이미 삭제되었거나 다른 경로에 있습니다. 무시해도 됩니다 |

---

## 3. 가상환경 생성

이 프로젝트에서는 두 개의 가상환경을 사용합니다. 각 환경의 역할이 다르기 때문에 분리합니다.

### 3-1. 환경 구성 개요

| 환경 이름 | Python 버전 | 용도 | 분리 이유 |
|-----------|-------------|------|-----------|
| **text2sql** | 3.11 | Gradio 웹 앱, Oracle 연동, 프롬프트 처리 | Gradio와 oracledb 패키지가 Python 3.11에서 안정적으로 동작합니다 |
| **py312_sr** | 3.12 | vLLM 모델 서빙 엔진 | vLLM 최신 버전이 Python 3.12를 요구합니다 |

> **왜 별도 환경인가?** Gradio 앱에서 사용하는 `oracledb`, `pandas` 등의 패키지와 vLLM이 사용하는 `torch`, `triton` 등의 패키지는 요구하는 의존성 버전이 서로 다릅니다. 하나의 환경에 모두 설치하면 "패키지 A는 numpy 1.x가 필요하고 패키지 B는 numpy 2.x가 필요하다"와 같은 **의존성 충돌**이 발생합니다. 환경을 분리하면 이 문제를 완전히 해결할 수 있습니다.

### 3-2. text2sql 환경 생성 (Gradio 앱용)

```bash
conda create -n text2sql python=3.11 -y
```

| 항목 | 설명 |
|------|------|
| **무엇을 하는 명령인가** | `text2sql`이라는 이름의 가상환경을 Python 3.11 버전으로 생성합니다 |
| **기대 결과** | 패키지 다운로드 및 설치 과정이 표시된 후, 환경 활성화 방법 안내가 출력됩니다 |
| **실패 시 대처** | `CondaValueError: prefix already exists` — 이미 같은 이름의 환경이 존재합니다. `conda env remove -n text2sql`로 삭제 후 재생성하거나 기존 환경을 사용합니다 |

옵션 설명:

| 옵션 | 의미 |
|------|------|
| `-n text2sql` | 환경 이름을 `text2sql`로 지정합니다 |
| `python=3.11` | Python 3.11 버전을 설치합니다 |
| `-y` | 확인 질문에 자동으로 "예"를 입력합니다 |

**환경 활성화 확인:**

```bash
conda activate text2sql
python --version
```

| 항목 | 설명 |
|------|------|
| **무엇을 하는 명령인가** | `text2sql` 환경을 활성화하고 Python 버전을 확인합니다 |
| **기대 결과** | 프롬프트가 `(text2sql)`로 변경되고, `Python 3.11.x`가 출력됩니다 |
| **실패 시 대처** | `conda activate`가 동작하지 않으면 `source activate text2sql`을 시도합니다 |

### 3-3. py312_sr 환경 생성 (vLLM용)

```bash
conda create -n py312_sr python=3.12 -y
```

| 항목 | 설명 |
|------|------|
| **무엇을 하는 명령인가** | `py312_sr`이라는 이름의 가상환경을 Python 3.12 버전으로 생성합니다 |
| **기대 결과** | 패키지 다운로드 및 설치 과정이 표시된 후, 환경 활성화 방법 안내가 출력됩니다 |
| **실패 시 대처** | `text2sql` 환경과 동일한 방법으로 대처합니다 |

**환경 활성화 확인:**

```bash
conda activate py312_sr
python --version
```

| 항목 | 설명 |
|------|------|
| **무엇을 하는 명령인가** | `py312_sr` 환경을 활성화하고 Python 버전을 확인합니다 |
| **기대 결과** | 프롬프트가 `(py312_sr)`로 변경되고, `Python 3.12.x`가 출력됩니다 |
| **실패 시 대처** | `conda activate`가 동작하지 않으면 `source activate py312_sr`을 시도합니다 |

활성화된 환경에서 나가려면 다음 명령어를 사용합니다.

```bash
conda deactivate
```

---

## 4. 환경 관리 명령어 요약

일상적으로 사용하는 conda 명령어를 정리합니다.

### 4-1. 환경 관리

| 명령어 | 설명 |
|--------|------|
| `conda env list` | 생성된 모든 가상환경 목록을 확인합니다. 현재 활성화된 환경에 `*` 표시가 됩니다 |
| `conda activate 환경이름` | 특정 가상환경을 활성화합니다 |
| `conda deactivate` | 현재 활성화된 가상환경을 비활성화하고 `base`로 돌아갑니다 |
| `conda env remove -n 환경이름` | 가상환경을 완전히 삭제합니다. 주의: 해당 환경에 설치된 모든 패키지도 함께 삭제됩니다 |

### 4-2. 패키지 관리

| 명령어 | 설명 |
|--------|------|
| `conda list` | 현재 활성화된 환경에 설치된 패키지 목록을 확인합니다 |
| `pip install 패키지이름` | pip으로 패키지를 설치합니다. conda 환경 안에서 pip을 사용할 수 있습니다 |
| `pip list` | pip으로 설치된 패키지 목록을 확인합니다 |
| `pip install 패키지이름==버전` | 특정 버전의 패키지를 설치합니다. 예: `pip install gradio==4.44.1` |

### 4-3. 정보 확인

| 명령어 | 설명 |
|--------|------|
| `conda info` | conda 설치 정보(버전, 경로, 채널 등)를 확인합니다 |
| `which python` | 현재 사용 중인 Python 실행 파일의 경로를 확인합니다 |
| `which pip` | 현재 사용 중인 pip의 경로를 확인합니다 |

> **중요**: `which python` 명령어로 항상 올바른 환경의 Python을 사용하고 있는지 확인하는 습관을 들이는 것이 좋습니다. 예를 들어 `text2sql` 환경에서는 `/root/miniconda3/envs/text2sql/bin/python`이 출력되어야 합니다.

---

## 5. 확인 체크리스트

다음 단계로 넘어가기 전에 모든 항목을 확인합니다.

| 순번 | 확인 항목 | 확인 명령어 | 기대 결과 |
|------|-----------|-------------|-----------|
| 1 | conda 설치 확인 | `conda --version` | `conda 24.x.x` (버전 번호 출력) |
| 2 | 프롬프트에 (base) 표시 | 쉘 프롬프트 확인 | `(base) [root@server ~]#` |
| 3 | text2sql 환경 존재 | `conda env list` | `text2sql` 항목 존재 |
| 4 | py312_sr 환경 존재 | `conda env list` | `py312_sr` 항목 존재 |
| 5 | text2sql Python 버전 | `conda activate text2sql && python --version` | `Python 3.11.x` |
| 6 | py312_sr Python 버전 | `conda activate py312_sr && python --version` | `Python 3.12.x` |

모든 항목이 확인되면 다음 문서로 진행합니다.

---
## 문서 탐색
| 이전 | 목차 | 다음 |
|------|------|------|
| [이전](./02-SERVER-SETUP.md) | [00-전체 안내](./00-INDEX.md) | [다음](./04-VLLM-DEPLOY.md) |
