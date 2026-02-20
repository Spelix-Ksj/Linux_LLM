# CHANGELOG

Text2SQL 프로젝트의 모든 변경사항을 역순(최신 -> 과거)으로 기록합니다.

Rocky Linux H100 GPU 서버에서 한국어 자연어를 Oracle SQL로 변환하는 시스템입니다.

---

## [2026-02-20] Phase 8: 프롬프트 개선 및 모델 역할 확정

GPT-OSS vs Qwen3-Coder 비교 분석 결과를 바탕으로 SYSTEM_PROMPT를 강화하고, 각 모델의 역할을 확정했습니다.

### 추가
- `app/text2sql_pipeline.py` SYSTEM_PROMPT에 3개 규칙 추가:
  - **Rule 7**: 출력 컬럼에 한글 별칭 사용 지시 (AS "한글명")
    - 예: `COUNT(*) AS "인원수"`, `org_nm AS "부서명"`
  - **Rule 8**: 여러 테이블 정보가 필요하면 적절한 JOIN 사용 (명시적 ON 조건 포함)
    - 예: `move_item_master m JOIN move_org_master o ON m.org_nm = o.org_nm`
  - **Rule 9**: 단일 테이블로 충분한 경우 불필요한 JOIN 금지
    - 예: 직급별 인원수는 `move_item_master`만 사용

### 변경
- `app/config.py`: Qwen3-Coder display_name을 "Qwen3-Coder 30B (테스트)"로 변경
- `app/config.py`: Qwen3-Coder description을 "테스트/비교용 모델"로 변경
- `DEFAULT_MODEL_KEY = "gpt-oss-120b"` 유지 확인

### 관련 파일
- `app/text2sql_pipeline.py` (SYSTEM_PROMPT 규칙 추가)
- `app/config.py` (모델 표시명 변경)

---

## [2026-02-20] Phase 7: GPT-OSS vs Qwen3-Coder 비교 분석

4개 테스트 질의를 통해 두 모델의 Text2SQL 성능을 비교 평가했습니다.

### 비교 결과
- **GPT-OSS 120B**: 4/4 성공 (100%) -- 단순하고 안정적인 Oracle SQL 생성
- **Qwen3-Coder 30B**: 3/4 성공 (75%) -- 한글 별칭(AS "한글명") 자동 사용은 우수하나, 불필요한 JOIN으로 오류 발생

### 결정
- GPT-OSS 120B를 메인 추론 모델로 유지
- Qwen3-Coder 30B를 테스트/비교용으로 유지 (향후 프롬프트 개선 시 재평가)

---

## [2026-02-20] Phase 6: Oracle 최적 모델 전수 조사 및 Qwen3-Coder 배포

Oracle SQL 전용 Text2SQL 오픈소스 모델이 존재하지 않음을 확인하고, 대안으로 범용 코딩 모델 Qwen3-Coder를 배포했습니다.

### 조사 결과
- Oracle SQL 전용 Text2SQL 오픈소스 모델: **존재하지 않음**
- BIRD/Spider 벤치마크 = 100% SQLite 기반 -> 전문 모델은 모두 SQLite 전용
- 대안: 범용 코딩 모델 중 Oracle 지원 가능한 모델 탐색
- 장기적 대안: SQLGlot(SQLite -> Oracle 자동 변환), ExeSQL 방식 파인튜닝 검토

### 추가
- `vllm-qwen3-coder.service` (systemd 서비스 신규 생성)
  - 모델: `Qwen3-Coder-30B-A3B-Instruct` (MoE 30B, 활성 파라미터 3B)
  - GPU 4, 포트 8001, `max-model-len=32768`
  - conda 환경: `py312_sr`
- `app/config.py`: `qwen3-coder-30b` 모델 레지스트리 항목 추가 (enabled)

### 변경
- `app/config.py`: `arctic-text2sql-7b` 항목 주석 처리 (비활성화)
- vllm-arctic 서비스 중지 및 비활성화

### 서버 상태
- GPU 4 VRAM 사용량: 87,485 / 95,830 MiB (91.3%)
- 모델 로딩 소요시간: 약 9분
- 추론 테스트: Oracle 문법 (NVL, TO_NUMBER, FETCH FIRST) 정상 사용 확인

### 관련 파일
- `app/config.py` (MODEL_REGISTRY 수정)
- `vllm-qwen3-coder.service` (서버: `/etc/systemd/system/`)

---

## [2026-02-20] Phase 5: Text2SQL 최적 모델 탐색

gpt-oss-120b 대비 더 정확한 Text2SQL 모델을 조사하고, Arctic-Text2SQL-R1-7B를 배포 후 Oracle 비호환 문제를 발견했습니다.

### 조사 결과
- **gpt-oss-120b**: 범용 모델, Text2SQL 추정 성능 BIRD 55~62% (중위권)
- **SQLCoder-34b**: 2023년 모델, 구세대 -- 최신 모델 대비 10%+ 열세
- **Arctic-Text2SQL-R1** (Snowflake): 2025년 BIRD 벤치마크 1위
  - 7B: BIRD 68.9%, 14B: 70.0%, 32B: 71.83%
  - Qwen2.5-Coder 기반 + GRPO RL 학습, Apache 2.0 라이선스
- **OmniSQL**: Spider 1위 (88.3%), BIRD에서는 Arctic보다 약간 열세

### 추가
- Arctic-Text2SQL-R1-7B 다운로드 및 배포 (GPU 4, 포트 8001)
  - HuggingFace에서 다운로드: `/install_file_backup/tessinu/Arctic-Text2SQL-R1-7B` (15GB)
  - vllm-arctic 서비스 생성 (`max_model_len=16384`, `gpu-memory-utilization=0.90`)
- `app/config.py`: `arctic-text2sql-7b` 모델 레지스트리 항목 추가

### 문제 발견 및 조치
- **증상**: Arctic이 `LIMIT`, `strftime()` 등 SQLite/MySQL 문법 생성 -> Oracle DB 실행 오류
- **원인**: BIRD/Spider 벤치마크가 100% SQLite 기반 -> Arctic은 SQLite SQL만 학습
- **시스템 프롬프트에 "Oracle SQL만 사용하라" 지시해도 파인튜닝이 이를 override**
- **결론**: Oracle DB 환경에서는 gpt-oss-120b(범용 117B)가 Arctic(SQLite 전문 7B)보다 우수
- **조치**: `DEFAULT_MODEL_KEY`를 `gpt-oss-120b`로 복원, Arctic은 비활성화

### 교훈
- Text2SQL 벤치마크 점수 != Oracle 환경 실전 성능
- 벤치마크 DB 엔진(SQLite)과 운영 DB 엔진(Oracle)이 다르면 성능 괴리 발생

### 관련 파일
- `app/config.py` (MODEL_REGISTRY, DEFAULT_MODEL_KEY 수정)

---

## [2026-02-20] Phase 4: SSH 키 인증 설정

Windows 개발 환경에서 Linux 서버로의 SSH 접속을 키 기반 인증으로 전환했습니다.

### 추가
- Windows에서 Ed25519 SSH 키 쌍 생성
- Linux 서버 `~/.ssh/authorized_keys`에 공개키 등록

### 변경
- SSH 접속 시 비밀번호 입력 불필요 (키 인증으로 자동화)

---

## [2026-02-20] Phase 3: EXAONE Deep 32B 배포 및 컨텍스트 초과 문제 해결

GPU 4에 EXAONE-Deep-32B를 배포하고, "[응답없음]" 오류의 원인을 분석하여 해결했습니다.

### 추가
- `vllm-exaone.service` (systemd 서비스 신규 생성)
  - 모델: `EXAONE-Deep-32B` (LG AI Research 한국어 추론 모델)
  - GPU 4, 포트 8001
- `app/config.py` MODEL_REGISTRY에 `exaone-deep-32b` 항목 추가
  - `max_tokens: 1024` (컨텍스트 초과 방지)

### 수정
- **문제**: 시스템 프롬프트(~7,289 토큰) + max_tokens(4,096) > max_model_len(8,192) -> 400 에러 -> UI에 "[응답없음]" 표시
- **해결 1**: MODEL_REGISTRY에 모델별 `max_tokens` 필드 추가
  - EXAONE: `max_tokens=1024` (짧은 컨텍스트 대응)
  - gpt-oss: `max_tokens=4096` (기본값)
- **해결 2**: `get_llm()`, `get_report_llm()`에서 `config["max_tokens"]` 참조하도록 수정
- **해결 3**: vllm-exaone.service의 `--max-model-len`을 8192 -> 16384로 증가

### 변경
- `app/.env`: `GRADIO_PASSWORD`를 `admin`으로 변경
- GPU 4 VRAM 사용량: ~88GB / 95GB

### 관련 파일
- `app/config.py` (MODEL_REGISTRY에 max_tokens 추가)
- `app/text2sql_pipeline.py` (get_llm, get_report_llm 수정)
- `app/model_registry.py` (get_model_config에서 max_tokens 반환)
- `vllm-exaone.service` (서버: `/etc/systemd/system/`)

---

## [2026-02-19] Phase 2: 조회 결과 보고서 기능 및 모델 선택 UI

쿼리 실행 결과를 자연어로 분석하는 보고서 기능을 추가하고, 다중 모델 선택이 가능한 UI를 구현했습니다.

### 추가 (보고서 기능)
- `app/text2sql_pipeline.py`:
  - `REPORT_PROMPT` 상수 추가 (보고서 생성용 시스템 프롬프트)
  - `generate_report()` 함수 추가 (SQL 분석 + LLM 결과 요약)
    - 결과 미리보기 3,000자 제한 (LLM 컨텍스트 초과 방지)
    - `result_preview` 3,000자 초과 시 5행으로 자동 축소
  - `get_report_llm()` 함수 추가 (보고서 전용 LLM 인스턴스, max_tokens=1024, timeout=30)
  - `ask_hr()` 반환값에 `reasoning` 키 추가 (LLM 추론 과정 캡처)
  - `_strip_sql_comments()` 함수 추가 (SQL 주석 제거)
  - `_is_safe_sql()` 위험 키워드 확장 (GRANT, REVOKE, CALL, COMMENT, RENAME 추가)
- `app/app.py`:
  - `generate_report` import 추가
  - `process_question()`: 4값 반환 (sql, df, status, report)
  - `gr.Accordion("결과 보고서")` + `gr.Markdown` 보고서 컴포넌트 추가

### 추가 (모델 선택 UI)
- `app/model_registry.py` **(신규 파일)**:
  - `_check_health()`: vLLM 인스턴스 헬스체크 (`/v1/models` 엔드포인트)
  - `get_available_models()`: enabled 모델 목록 + 헬스체크 결과
  - `get_model_config()`: 모델별 base_url, model_name, max_tokens 반환
  - `get_display_choices()`: Gradio Dropdown용 `[(label, key)]` 리스트 (상태 아이콘 포함)
- `app/config.py`:
  - `MODEL_REGISTRY` 딕셔너리 추가 (다중 vLLM 인스턴스 라우팅)
  - `DEFAULT_MODEL_KEY = "gpt-oss-120b"` 추가
- `app/app.py`:
  - 모델 선택 Dropdown + 새로고침 버튼 + 상태 마크다운 추가
  - `_build_model_status()`, `_refresh_models()`, `_on_model_change()` 함수 추가

### 수정
- `app/text2sql_pipeline.py`:
  - 메인 LLM 인스턴스에 `timeout=60` 추가
  - SQL 실행에 Oracle `call_timeout=30000ms` 추가
  - 보고서 프롬프트 인젝션 방지: `question[:500]` + `<user_input>` 구분자
  - `ask_hr()` try/except를 LLM 호출(1단계)과 SQL 실행(2단계)으로 분리, 오류 메시지 세분화
- `app/app.py`:
  - 하드코딩된 기본 비밀번호 제거 -> 환경변수 필수 검증 (`RuntimeError` 발생)
  - `model_key` 클라이언트 측 조작 방지 (MODEL_REGISTRY 유효성 검증)
- `app/text2sql_pipeline.py`:
  - 미사용 글로벌 `llm`/`report_llm` 인스턴스 제거 -> `get_llm()`/`get_report_llm()` 팩토리만 사용
  - LLM 캐시 TOCTOU 경쟁 조건 수정: 인스턴스 생성을 lock 내부로 이동

### 관련 파일
- `app/app.py` (UI, 보고서, 모델 선택)
- `app/text2sql_pipeline.py` (보고서 생성, LLM 팩토리, 보안 강화)
- `app/model_registry.py` **(신규)** (모델 헬스체크, Dropdown 연동)
- `app/config.py` (MODEL_REGISTRY, DEFAULT_MODEL_KEY)
- `decisions.md` (설계 결정 및 리뷰 이력 기록)

---

## [2026-02-18~19] Phase 1: 초기 구축 (서버 환경 -> 웹 UI 배포)

Rocky Linux 9.6 H100 GPU 서버에 Text2SQL 시스템을 처음부터 구축했습니다.

### 서버 환경
- **OS**: Rocky Linux 9.6
- **GPU**: NVIDIA H100 80GB x 5장
- **CPU**: AMD EPYC 9454 (96코어)
- **메모리**: 충분한 시스템 RAM

### 추가 (환경 설정)
- Miniconda 설치 및 conda 환경 구성
  - `text2sql` 환경: vLLM + LangChain + Gradio
  - `py312_sr` 환경: 보조 모델 서빙용
- vLLM 설치 및 gpt-oss-120b 모델 배포
  - GPU 0-3, Tensor Parallel 4, 포트 8000
- 방화벽 포트 개방: 8000 (vLLM API), 7860 (Gradio UI)

### 추가 (배포 스크립트)
- `deploy/01_check_environment.sh` (서버 환경 확인)
- `deploy/02_install_system_deps.sh` (시스템 의존성 설치)
- `deploy/03_install_miniconda.sh` (Miniconda 설치)
- `deploy/04_install_vllm.sh` (vLLM 설치)
- `deploy/05_install_app_deps.sh` (앱 의존성 설치)
- `deploy/06_setup_services.sh` (systemd 서비스 등록)
- `deploy/deploy_all.sh` (전체 배포 원클릭)

### 추가 (애플리케이션)
- `app/config.py`: 환경 설정 로더 (.env 파싱, Oracle DB 설정, vLLM 설정, Gradio 설정)
- `app/.env.example`: 환경변수 템플릿 (Oracle DB, vLLM, Gradio 비밀번호)
- `app/db_setup.py`: Oracle DB 연결 (oracledb + SQLAlchemy, 커넥션 풀링)
  - 대상 테이블: `move_item_master`, `move_case_item`, `move_case_cnst_master`, `move_org_master`
- `app/text2sql_pipeline.py`: LangChain Text2SQL 핵심 파이프라인
  - 시스템 프롬프트 + 테이블 스키마 자동 주입
  - SQL 생성 -> 정제 -> 안전성 검증 -> 실행
  - `_clean_sql()`: LLM 출력에서 순수 SQL 추출 (마크다운 코드블록, 설명 텍스트 제거)
  - `_is_safe_sql()`: SELECT/WITH만 허용, 위험 키워드 차단
  - `ask_hr()`: 자연어 질문 -> SQL 변환 -> 실행 -> DataFrame 반환 (최대 1,000행 제한)
- `app/app.py`: Gradio 웹 UI
  - 질문 입력 -> SQL 표시 -> 결과 테이블 -> 예시 질문
  - Gradio Blocks + Soft 테마
- `app/test_e2e.py`: 통합 테스트 스크립트 (DB 연결, vLLM 연결, SQL 생성, 다양한 질문)

### 추가 (systemd 서비스)
- `services/vllm.service`: gpt-oss-120b 서빙 (GPU 0-3, TP4, 포트 8000)
- `services/vllm-7b.service`: sqlcoder-7b-2 테스트용 (포트 8000)
- `services/text2sql-ui.service`: Gradio 웹 UI (포트 7860, vllm.service 의존)

### 추가 (원격 배포 유틸리티)
- `remote_deploy.py`: Windows에서 Linux로 원격 배포
- `remote_exec.py`: 원격 명령 실행
- `run_on_server.py`: 서버 실행 유틸리티
- `upload_to_server.sh`: 파일 업로드 스크립트
- `fix_and_start.py`, `fix_service.py`: 서비스 문제 해결 유틸리티
- `verify_deploy.py`: 배포 검증
- `deploy_report.py`: 배포 리포트 생성

### 관련 파일 (전체)
- `app/` 디렉토리: `config.py`, `db_setup.py`, `text2sql_pipeline.py`, `app.py`, `test_e2e.py`, `.env.example`
- `deploy/` 디렉토리: 01~06 배포 스크립트, `deploy_all.sh`
- `services/` 디렉토리: `vllm.service`, `vllm-7b.service`, `text2sql-ui.service`
- 유틸리티: `remote_deploy.py`, `remote_exec.py`, `run_on_server.py`, `upload_to_server.sh`

---

## 프로젝트 구조 요약

```
Linux_LLM/
  app/
    app.py                  # Gradio 웹 UI (메인 인터페이스)
    config.py               # 환경 설정 + MODEL_REGISTRY
    db_setup.py             # Oracle DB 연결 (SQLAlchemy)
    model_registry.py       # 모델 헬스체크 + Dropdown 연동
    text2sql_pipeline.py    # LangChain Text2SQL 핵심 파이프라인
    test_e2e.py             # 통합 테스트
    .env                    # 환경변수 (Git 미추적)
    .env.example            # 환경변수 템플릿
  deploy/
    01_check_environment.sh # 서버 환경 확인
    02_install_system_deps.sh
    03_install_miniconda.sh
    04_install_vllm.sh
    05_install_app_deps.sh
    06_setup_services.sh    # systemd 서비스 등록
    deploy_all.sh           # 전체 배포 원클릭
  services/
    vllm.service            # gpt-oss-120b (GPU 0-3, 포트 8000)
    vllm-7b.service         # sqlcoder-7b 테스트용
    text2sql-ui.service     # Gradio UI (포트 7860)
  decisions.md              # 설계 결정 및 리뷰 이력
  CHANGELOG.md              # 이 파일
```

## 서버 최종 배포 상태

| 서비스 | 모델 | GPU | 포트 | 상태 |
|--------|------|-----|------|------|
| vllm (메인) | gpt-oss-120b (117B MoE) | 0-3 (TP4) | 8000 | active |
| vllm-qwen3-coder | Qwen3-Coder-30B-A3B (테스트) | 4 | 8001 | active |
| text2sql-ui | Gradio 웹 UI | - | 7860 | active |
