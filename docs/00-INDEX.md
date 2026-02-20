# 00. Text2SQL HR 시스템 -- 프로젝트 안내

> **한줄 요약**: 한국어 자연어 질문을 Oracle SQL로 자동 변환하고, 조회 결과와 분석 보고서를 반환하는 인사정보 시스템입니다.

---

## 시스템 아키텍처

```
                          +-----------------------+
                          |   사용자 브라우저       |
                          +-----------+-----------+
                                      |
                                      | HTTP :7860
                                      v
                          +-----------------------+
                          |  Gradio 웹 UI         |
                          |  (인증: admin/****)    |
                          +-----------+-----------+
                                      |
                                      v
                          +-----------------------+
                          |  LangChain            |
                          |  Text2SQL 파이프라인    |
                          +-----+----------+------+
                                |          |
                   +------------+          +-------------+
                   |                                     |
                   v                                     v
    +-----------------------------+        +-------------------------+
    |  vLLM  (GPU 0-3)  :8000    |        |  Oracle DB              |
    |  gpt-oss-120b (메인)        |        |  HQ.SPELIX.CO.KR:7744  |
    |  MoE 117B, TP4             |        |  SID: HISTPRD           |
    +-----------------------------+        |  스키마: HRAI_CON       |
    +-----------------------------+        +-------------------------+
    |  vLLM  (GPU 4)    :8001    |
    |  Qwen3-Coder 30B (테스트)   |
    |  MoE 30B, 활성 3B           |
    +-----------------------------+
```

---

## 서버 정보

| 항목 | 값 |
|------|-----|
| **IP 주소** | `192.168.10.40` |
| **운영체제** | Rocky Linux 9.6 |
| **CPU** | AMD EPYC 9454 (96코어) |
| **RAM** | ~503 GB |
| **GPU** | NVIDIA H100 NVL x 5장 (95 GB VRAM 각) |
| **Conda 환경 (앱)** | `text2sql` -- Gradio + LangChain + oracledb |
| **Conda 환경 (vLLM)** | `py312_sr` -- vLLM 모델 서빙 전용 |
| **웹 UI** | `http://192.168.10.40:7860` |
| **vLLM API (메인)** | `http://192.168.10.40:8000/v1` |
| **vLLM API (테스트)** | `http://192.168.10.40:8001/v1` |

---

## 문서 로드맵

목적에 따라 아래 세 가지 경로 중 하나를 선택합니다.

### 경로 A: 처음부터 전체 시스템을 구축하는 경우

아래 순서대로 따라가세요:

| 순서 | 문서 | 내용 |
|------|------|------|
| 1 | [01-시스템 아키텍처](./01-ARCHITECTURE.md) | 전체 구조 이해 |
| 2 | [02-서버 환경 설정](./02-SERVER-SETUP.md) | SSH, GPU, 방화벽 |
| 3 | [03-Python 환경](./03-PYTHON-ENV.md) | Miniconda, 가상환경 |
| 4 | [04-vLLM 배포](./04-VLLM-DEPLOY.md) | LLM 모델 서빙 |
| 5 | [05-Oracle DB](./05-ORACLE-DB.md) | 데이터베이스 연결 |
| 6 | [06-앱 배포](./06-APP-DEPLOY.md) | 애플리케이션 설치 |
| 7 | [07-서비스 등록](./07-SERVICES.md) | systemd 자동화 |
| 8 | [08-통합 테스트](./08-TESTING.md) | 전체 검증 |

### 경로 B: 이미 운영 중

시스템이 가동 중이며, 일상 운영 또는 문제 해결이 필요한 경우입니다.

| 문서 | 내용 |
|------|------|
| [09-OPERATIONS](./09-OPERATIONS.md) | 서비스 관리, 모니터링, 설정 변경 |
| [10-TROUBLESHOOTING](./10-TROUBLESHOOTING.md) | 증상별 원인 분석 및 해결 방법 |

### 경로 C: 모델 추가/교체

GPU 4에 새로운 LLM 모델을 배포하거나, 기존 모델을 교체하는 경우입니다.

| 문서 | 내용 |
|------|------|
| [11-MODEL-MANAGEMENT](./11-MODEL-MANAGEMENT.md) | 모델 레지스트리, vLLM 서비스 생성, 성능 비교 |

### 빠른 참조

| 문서 | 내용 |
|------|------|
| [99-REFERENCE](./99-REFERENCE.md) | 환경변수 목록, 포트 매핑, 명령어 치트시트 |

---

## 프로젝트 파일 구조

```
Linux_LLM/
|
+-- app/                            # 애플리케이션 소스 코드
|   +-- app.py                      # Gradio 웹 UI (메인 인터페이스)
|   +-- config.py                   # 환경 설정 + MODEL_REGISTRY (다중 모델)
|   +-- db_setup.py                 # Oracle DB 연결 (oracledb + SQLAlchemy)
|   +-- model_registry.py           # 모델 헬스체크 + Dropdown 연동
|   +-- text2sql_pipeline.py        # LangChain Text2SQL 핵심 파이프라인
|   +-- test_e2e.py                 # 통합 테스트 (DB/vLLM/SQL 생성 검증)
|   +-- .env                        # 환경변수 (Git 미추적)
|   +-- .env.example                # 환경변수 템플릿
|
+-- deploy/                         # 서버 배포 스크립트 (순서대로 실행)
|   +-- 01_check_environment.sh     # 서버 환경 확인
|   +-- 02_install_system_deps.sh   # 시스템 의존성 설치
|   +-- 03_install_miniconda.sh     # Miniconda 설치
|   +-- 04_install_vllm.sh          # vLLM 설치
|   +-- 05_install_app_deps.sh      # 앱 의존성 설치
|   +-- 06_setup_services.sh        # systemd 서비스 등록
|   +-- deploy_all.sh               # 전체 배포 원클릭 실행
|
+-- services/                       # systemd 서비스 정의 파일
|   +-- vllm.service                # gpt-oss-120b (GPU 0-3, TP4, 포트 8000)
|   +-- vllm-7b.service             # sqlcoder-7b 테스트용 (사용 중지)
|   +-- text2sql-ui.service         # Gradio UI (포트 7860, vllm 의존)
|
+-- docs/                           # 프로젝트 문서
|   +-- 00-INDEX.md                 # 이 파일 (프로젝트 안내)
|   +-- 01-ARCHITECTURE.md          # 시스템 아키텍처
|   +-- 02-SERVER-SETUP.md          # 서버 환경 확인 및 기본 설정
|   +-- 03-PYTHON-ENV.md            # Miniconda 설치 및 Python 환경 구성
|   +-- 04-VLLM-DEPLOY.md           # vLLM 설치 및 LLM 모델 배포
|   +-- 05-ORACLE-DB.md             # Oracle DB 연결 설정
|   +-- 06-APP-DEPLOY.md            # 애플리케이션 배포
|   +-- 07-SERVICES.md              # systemd 서비스 등록 및 자동화
|   +-- 08-TESTING.md               # 통합 테스트 및 검증
|   +-- 09-OPERATIONS.md            # 운영 가이드
|   +-- 10-TROUBLESHOOTING.md       # 문제 해결
|   +-- 11-MODEL-MANAGEMENT.md      # 모델 관리
|   +-- 99-REFERENCE.md             # 빠른 참조
|
+-- remote_deploy.py                # Windows -> Linux 원격 배포
+-- remote_exec.py                  # 원격 명령 실행
+-- run_on_server.py                # 서버 실행 유틸리티
+-- upload_to_server.sh             # SCP 파일 업로드
+-- fix_and_start.py                # 서비스 문제 해결 유틸리티
+-- fix_service.py                  # 서비스 수정 유틸리티
+-- verify_deploy.py                # 배포 검증
+-- deploy_report.py                # 배포 리포트 생성
+-- deploy_fixes.py                 # 배포 수정 사항 적용
+-- disable_vllm_svc.py             # vLLM 서비스 비활성화
+-- CHANGELOG.md                    # 전체 변경 이력 (Phase 1~8)
+-- OPERATIONS.md                   # 서버 운영 가이드 (Linux 초보자용)
+-- decisions.md                    # 설계 결정 및 리뷰 이력
```

---

## 관련 문서

| 문서 | 설명 |
|------|------|
| [CHANGELOG.md](../CHANGELOG.md) | Phase 1(초기 구축)부터 Phase 8(프롬프트 개선)까지의 전체 변경 이력을 역순으로 기록합니다. |
| [decisions.md](../decisions.md) | 각 미션별 설계 결정, 코드 리뷰 이력, 모델 비교 분석 결과를 기록합니다. |
| [OPERATIONS.md](../OPERATIONS.md) | Linux 명령어를 모르는 개발자를 위한 서버 운영 가이드입니다. SSH 접속부터 문제 해결까지 11개 섹션으로 구성되어 있습니다. |

---

## 빠른 시작

시스템이 이미 가동 중이라면 아래 정보만으로 즉시 사용할 수 있습니다.

1. 브라우저에서 `http://192.168.10.40:7860` 에 접속합니다.
2. 로그인 정보: `.env` 파일의 `GRADIO_USER` / `GRADIO_PASSWORD` 값을 사용합니다.
3. 질문 입력란에 한국어 질문을 입력합니다 (예: "직급별 인원 수를 구해줘").
4. "SQL 생성 및 실행" 버튼을 클릭합니다.
5. 생성된 SQL, 조회 결과 테이블, 분석 보고서가 차례로 표시됩니다.

---

*이 문서는 2026-02-20에 작성되었습니다.*
