# 99. 참조 자료 모음

> **이 문서를 읽으면**: 서버 정보, 포트 맵, 환경변수, 파일 경로 등 자주 참조하는 정보를 한 곳에서 찾을 수 있습니다.
> **소요 시간**: 약 10분 (전체 읽기) / 필요한 항목만 참고 시 1~2분
> **선행 조건**: 없음 (독립 참조 문서)

---

## 목차

1. [서버 정보](#1-서버-정보)
2. [포트 맵](#2-포트-맵)
3. [환경변수 전체 목록](#3-환경변수-전체-목록)
4. [Python 패키지 목록](#4-python-패키지-목록)
5. [systemd 서비스 목록](#5-systemd-서비스-목록)
6. [파일 경로 맵](#6-파일-경로-맵)
7. [Oracle HR 테이블 스키마 요약](#7-oracle-hr-테이블-스키마-요약)
8. [유용한 외부 링크](#8-유용한-외부-링크)

---

## 1. 서버 정보

| 항목 | 값 |
|------|-----|
| **IP 주소** | `192.168.10.40` |
| **운영체제** | Rocky Linux 9.6 |
| **CPU** | AMD EPYC 9454 (96코어) |
| **RAM** | 약 503 GB |
| **GPU** | NVIDIA H100 NVL x 5장 (각 95 GB VRAM) |
| **GPU 할당** | GPU 0~3: GPT-OSS-120B (TP4), GPU 4: Qwen3-Coder |
| **SSH 사용자** | `root` |
| **SSH 접속** | `ssh root@192.168.10.40` |
| **Conda 환경 (앱)** | `text2sql` -- Gradio + LangChain + oracledb |
| **Conda 환경 (vLLM)** | `py312_sr` -- vLLM 모델 서빙 전용 |

---

## 2. 포트 맵

| 포트 | 프로토콜 | 서비스 | 접속 URL | 용도 |
|------|----------|--------|----------|------|
| **22** | TCP | SSH | `ssh root@192.168.10.40` | 원격 서버 접속 |
| **7860** | TCP | Gradio 웹 UI | `http://192.168.10.40:7860` | Text2SQL 사용자 인터페이스 |
| **8000** | TCP | vLLM (GPT-OSS-120B) | `http://192.168.10.40:8000/v1` | 메인 LLM API (GPU 0~3) |
| **8001** | TCP | vLLM (Qwen3-Coder) | `http://192.168.10.40:8001/v1` | 테스트 LLM API (GPU 4) |

### 포트 사용 현황 확인 명령어

```bash
# 방화벽에서 열린 포트 확인
firewall-cmd --list-ports

# 현재 리스닝 중인 포트 확인
ss -tlnp | grep -E '(7860|8000|8001|22)'
```

---

## 3. 환경변수 전체 목록

`.env` 파일 위치: `/root/text2sql/app/.env`

| 번호 | 변수명 | 기본값 | 용도 | 필수 |
|------|--------|--------|------|------|
| 1 | `ORACLE_USER` | `HRAI_CON` | Oracle DB 사용자명 | 필수 |
| 2 | `ORACLE_PASSWORD` | (없음) | Oracle DB 비밀번호 | 필수 |
| 3 | `ORACLE_HOST` | `HQ.SPELIX.CO.KR` | Oracle DB 호스트 | 필수 |
| 4 | `ORACLE_PORT` | `7744` | Oracle DB 포트 | 필수 |
| 5 | `ORACLE_SID` | `HISTPRD` | Oracle DB SID | 필수 |
| 6 | `VLLM_BASE_URL_0` | `http://localhost:8000/v1` | 메인 vLLM API URL (GPT-OSS-120B) | 선택 |
| 7 | `VLLM_MODEL_0` | `/install_file_backup/tessinu/gpt-oss-120b` | 메인 모델 경로/이름 | 선택 |
| 8 | `VLLM_BASE_URL_1` | `http://localhost:8001/v1` | 보조 vLLM API URL (Qwen3-Coder) | 선택 |
| 9 | `SSH_PASSWORD` | (없음) | SSH 접속 비밀번호 (배포 스크립트용) | 선택 |
| 10 | `GRADIO_HOST` | `0.0.0.0` | Gradio 서버 바인딩 주소 | 선택 |
| 11 | `GRADIO_PORT` | `7860` | Gradio 서버 포트 | 선택 |
| 12 | `GRADIO_USER` | (없음) | 웹 UI 로그인 사용자명 | 필수 |
| 13 | `GRADIO_PASSWORD` | (없음) | 웹 UI 로그인 비밀번호 | 필수 |

### .env 파일 예시

```bash
# Oracle DB 설정
ORACLE_USER=HRAI_CON
ORACLE_PASSWORD=your_password_here
ORACLE_HOST=HQ.SPELIX.CO.KR
ORACLE_PORT=7744
ORACLE_SID=HISTPRD

# vLLM 설정
VLLM_BASE_URL_0=http://localhost:8000/v1
VLLM_MODEL_0=/install_file_backup/tessinu/gpt-oss-120b
VLLM_BASE_URL_1=http://localhost:8001/v1

# SSH 서버 접속 (배포 스크립트용)
SSH_PASSWORD=your_ssh_password_here

# Gradio 웹 UI 설정
GRADIO_HOST=0.0.0.0
GRADIO_PORT=7860
GRADIO_USER=admin
GRADIO_PASSWORD=your_password_here
```

> **주의**: `.env` 파일에는 비밀번호가 포함되어 있으므로 Git에 커밋하지 않습니다. `.env.example` 파일을 복사하여 사용합니다.

---

## 4. Python 패키지 목록

### text2sql 환경 (Gradio 앱)

Conda 환경 이름: `text2sql`

| 패키지 | 용도 |
|--------|------|
| `langchain` | LLM 체인 프레임워크 (Text2SQL 파이프라인) |
| `langchain-openai` | OpenAI 호환 LLM 연결 (vLLM과 통신) |
| `langchain-community` | LangChain 커뮤니티 유틸리티 (SQLDatabase) |
| `oracledb` | Oracle DB 드라이버 (python-oracledb) |
| `sqlalchemy` | Python SQL 툴킷 및 ORM |
| `pandas` | 데이터 처리 및 테이블 표시 |
| `gradio` | 웹 UI 프레임워크 |

패키지 확인 명령어:

```bash
conda activate text2sql
pip list
```

### py312_sr 환경 (vLLM)

Conda 환경 이름: `py312_sr`

| 패키지 | 용도 |
|--------|------|
| `vllm` | 대규모 언어 모델 서빙 엔진 |
| `torch` | PyTorch (GPU 연산 프레임워크) |
| `transformers` | HuggingFace Transformers (모델 로딩) |

패키지 확인 명령어:

```bash
conda activate py312_sr
pip list
```

---

## 5. systemd 서비스 목록

### 활성 서비스 (3개)

| 서비스명 | 상태 | 파일 위치 | 용도 |
|----------|------|-----------|------|
| `vllm.service` | active | `/etc/systemd/system/vllm.service` | GPT-OSS-120B 모델 서빙 (GPU 0~3, 포트 8000) |
| `vllm-qwen3-coder.service` | active | `/etc/systemd/system/vllm-qwen3-coder.service` | Qwen3-Coder 모델 서빙 (GPU 4, 포트 8001) |
| `text2sql-ui.service` | active | `/etc/systemd/system/text2sql-ui.service` | Gradio 웹 UI (포트 7860) |

### 비활성(masked) 서비스 (1개)

| 서비스명 | 상태 | 파일 위치 | 비활성 이유 |
|----------|------|-----------|-------------|
| `vllm-7b.service` | masked | `/etc/systemd/system/vllm-7b.service` | sqlcoder-7b 테스트 전용. 현재 사용하지 않아 mask 처리됨 |

### 서비스 관리 명령어 요약

```bash
# 상태 확인
systemctl status 서비스명

# 시작 / 중지 / 재시작
systemctl start 서비스명
systemctl stop 서비스명
systemctl restart 서비스명

# 부팅 시 자동 시작 설정 / 해제
systemctl enable 서비스명
systemctl disable 서비스명

# 설정 파일 변경 후 반영
systemctl daemon-reload

# 로그 확인
journalctl -u 서비스명 -n 50 --no-pager
```

---

## 6. 파일 경로 맵

### 서버 내 주요 경로

| 경로 | 내용 |
|------|------|
| `/root/text2sql/` | 프로젝트 루트 디렉토리 |
| `/root/text2sql/app/` | Python 애플리케이션 소스 코드 |
| `/root/text2sql/app/app.py` | Gradio 웹 UI 메인 스크립트 |
| `/root/text2sql/app/config.py` | 환경 설정 + MODEL_REGISTRY |
| `/root/text2sql/app/db_setup.py` | Oracle DB 연결 설정 |
| `/root/text2sql/app/model_registry.py` | 모델 헬스체크 + Dropdown 연동 |
| `/root/text2sql/app/text2sql_pipeline.py` | LangChain Text2SQL 핵심 파이프라인 |
| `/root/text2sql/app/test_e2e.py` | 통합 테스트 스크립트 |
| `/root/text2sql/app/.env` | 환경변수 파일 (비밀번호 포함, Git 미추적) |
| `/root/text2sql/app/.env.example` | 환경변수 템플릿 |
| `/root/miniconda3/` | Miniconda 설치 경로 |
| `/root/miniconda3/envs/text2sql/` | text2sql Conda 환경 |
| `/root/miniconda3/envs/py312_sr/` | py312_sr Conda 환경 (vLLM) |
| `/install_file_backup/tessinu/` | LLM 모델 파일 저장 경로 |
| `/install_file_backup/tessinu/gpt-oss-120b` | GPT-OSS-120B 모델 파일 |
| `/etc/systemd/system/` | systemd 서비스 파일 |
| `/etc/systemd/system/vllm.service` | GPT-OSS-120B vLLM 서비스 정의 |
| `/etc/systemd/system/vllm-qwen3-coder.service` | Qwen3-Coder vLLM 서비스 정의 |
| `/etc/systemd/system/text2sql-ui.service` | Gradio 웹 UI 서비스 정의 |

### Windows 개발 환경 경로 (참고)

| 경로 | 내용 |
|------|------|
| `D:\Dev\Linux_LLM\` | 프로젝트 루트 (Windows) |
| `D:\Dev\Linux_LLM\app\` | Python 애플리케이션 소스 코드 |
| `D:\Dev\Linux_LLM\services\` | systemd 서비스 정의 파일 |
| `D:\Dev\Linux_LLM\deploy\` | 서버 배포 스크립트 |
| `D:\Dev\Linux_LLM\docs\` | 프로젝트 문서 |

---

## 7. Oracle HR 테이블 스키마 요약

스키마 이름: `HRAI_CON`

### move_item_master (인사이동 대상 직원 마스터)

| 컬럼명 | 설명 | 자주 사용하는 쿼리 |
|--------|------|-------------------|
| `emp_nm` | 직원 이름 | 직원 검색, 목록 조회 |
| `pos_grd_nm` | 직급 (사원, 대리, 과장 등) | 직급별 집계, 조건 필터 |
| `org_nm` | 현재 소속 조직명 | 부서별 집계, JOIN 키 |
| `lvl1_nm` ~ `lvl5_nm` | 조직 계층 (레벨 1~5) | 조직 구조 분석 |
| `job_type1`, `job_type2` | 직종 구분 | 직종별 분석 |
| `gender_nm` | 성별 | 성별 통계 |
| `year_desc` | 연령대 | 평균 나이, 연령 분석 |
| `org_work_mon` | 조직 근무 개월 수 | 근속 분석 |
| `region_type` | 지역 구분 | 지역별 분석 |

### move_case_item (인사이동 배치안 상세)

| 컬럼명 | 설명 | 자주 사용하는 쿼리 |
|--------|------|-------------------|
| `new_lvl1_nm` ~ `new_lvl5_nm` | 새 조직 계층 (이동 후) | 인사이동 분석 |
| `must_stay_yn` | 잔류 필수 여부 (Y/N) | 이동 제약 분석 |
| `must_move_yn` | 이동 필수 여부 (Y/N) | 이동 필수 대상 조회 |

### move_case_cnst_master (인사이동 제약조건)

| 컬럼명 | 설명 | 자주 사용하는 쿼리 |
|--------|------|-------------------|
| `cnst_nm` | 제약조건 이름 | 제약조건 목록 조회 |
| `cnst_val` | 제약조건 값 | 제약조건 상세 |
| `penalty_val` | 위반 시 패널티 값 | 패널티 분석 |

### move_org_master (조직 마스터)

| 컬럼명 | 설명 | 자주 사용하는 쿼리 |
|--------|------|-------------------|
| `org_nm` | 조직명 | 조직 목록, JOIN 키 |
| `org_type` | 조직 유형 | 유형별 분류 |
| `tot_to` | 정원 | 정원 대비 현원 비교 |
| `region_type` | 지역 구분 | 지역별 분석 |
| `job_type1`, `job_type2` | 직종 구분 | 직종별 분석 |

### 테이블 간 관계

```
move_item_master (직원)
       |
       | org_nm (부서명)
       |
       v
move_org_master (조직)
       |
       | org_nm
       |
move_case_item (배치안)
       |
move_case_cnst_master (제약조건)
```

- `move_item_master`와 `move_org_master`는 `org_nm` 컬럼으로 JOIN할 수 있습니다.
- 부서별 정원(move_org_master.tot_to)과 현원(move_item_master의 COUNT)을 비교할 때 JOIN을 사용합니다.

---

## 8. 유용한 외부 링크

### 핵심 프레임워크 문서

| 프레임워크 | 공식 문서 URL | 이 프로젝트에서의 용도 |
|------------|--------------|----------------------|
| **vLLM** | https://docs.vllm.ai/ | LLM 모델 서빙 엔진 |
| **LangChain** | https://python.langchain.com/docs/ | Text2SQL 파이프라인 구성 |
| **Gradio** | https://www.gradio.app/docs/ | 웹 UI 프레임워크 |
| **python-oracledb** | https://python-oracledb.readthedocs.io/ | Oracle DB 접속 드라이버 |

### 참고 자료

| 자료 | URL | 내용 |
|------|-----|------|
| **SQLAlchemy** | https://docs.sqlalchemy.org/ | Python SQL 툴킷 (DB 연결 엔진) |
| **Oracle SQL Reference** | https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ | Oracle SQL 문법 레퍼런스 |
| **systemd 매뉴얼** | https://www.freedesktop.org/software/systemd/man/ | systemd 서비스 관리 |
| **Rocky Linux 문서** | https://docs.rockylinux.org/ | 서버 운영체제 문서 |
| **NVIDIA SMI 문서** | https://developer.nvidia.com/nvidia-system-management-interface | GPU 모니터링 도구 |

### 모델 관련 링크

| 모델 | URL | 비고 |
|------|-----|------|
| **Qwen3-Coder** | https://huggingface.co/Qwen | Qwen3-Coder-30B-A3B 모델 시리즈 |
| **BIRD 벤치마크** | https://bird-bench.github.io/ | Text2SQL 벤치마크 (SQLite 기반) |
| **Spider 벤치마크** | https://yale-lily.github.io/spider | Text2SQL 벤치마크 (SQLite 기반) |

---

## 문서 탐색
| 이전 | 목차 | 다음 |
|------|------|------|
| [11-MODEL-MANAGEMENT](./11-MODEL-MANAGEMENT.md) | [00-전체 안내](./00-INDEX.md) | - |
