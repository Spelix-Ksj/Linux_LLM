# Team Decisions Log

## 미션
- 원본 요청: WebUI에서 조회 결과 하단에 어떻게 이런 결과가 나왔는지 결과 보고서도 보여줘
- 시작 시각: 2026-02-19 17:00
- 완료 시각: 2026-02-19

## 작업 분석
- 유형: UI 개선 + 기능 개발
- 복잡도: 보통
- 현재 UI 구성: 질문 입력 → 생성된 SQL(Code) → 조회 결과(Dataframe)
- 요구사항: 조회 결과 아래에 "결과 보고서" 섹션 추가 — SQL이 어떻게 생성되었는지, 어떤 테이블/컬럼을 사용했는지, 결과 요약을 자연어로 설명
- 대상 파일: app.py (UI), text2sql_pipeline.py (보고서 생성 로직)
- 제약: 기존 vLLM(GPU 0-3) 영향 없어야 함

## 팀 구성
1. 설계자 (team-architect): 보고서 UI/데이터 구조 설계
2. 개발자 (general-purpose): 코드 구현
3. 검토자 (team-critic): 비판적 검토 (2회 수행)

## 설계 결정
- 접근법: reasoning_content 캡처 + 2차 LLM 호출 하이브리드
- reasoning_content: SQL 생성 시 LLM의 사고과정 (추가 비용 없음) → 접기 형태로 표시
- 2차 LLM 호출: 쿼리 결과 DataFrame 상위 20행을 기반으로 자연어 보고서 생성
- UI: gr.Accordion + gr.Markdown으로 보고서 표시
- 보고서 구성: SQL 분석(테이블/컬럼/건수) + LLM 추론과정(접기) + 결과 요약(자연어)

## 변경된 파일
1. text2sql_pipeline.py
   - import logging, logger 모듈 레벨 설정
   - report_llm 별도 인스턴스 (max_tokens=1024, timeout=30)
   - REPORT_PROMPT 상수 추가
   - generate_report() 함수 추가 (result_preview 3000자 제한, report_llm 사용, 예외 로깅)
   - ask_hr() 반환값에 reasoning 키 추가
   - _is_safe_sql() 위험 키워드 확장 (GRANT, REVOKE, CALL, COMMENT, RENAME 추가)
2. app.py
   - generate_report import 추가
   - process_question 4값 반환 (sql, df, status, report)
   - gr.Accordion("결과 보고서") 래핑 + gr.Markdown 보고서 컴포넌트
   - 하드코딩된 기본 비밀번호 제거 → 환경변수 필수 검증 (RuntimeError)

## 리뷰 이력

### 1차 리뷰 (NEEDS_IMPROVEMENT)
- HIGH #2: result_preview 크기 제한 없음 → 수정: 3000자 초과 시 5행으로 축소
- HIGH #3: 2차 LLM 호출 timeout/max_tokens 없음 → 수정: report_llm 별도 인스턴스
- MEDIUM #4: generate_report exception 로깅 없음 → 수정: logger.error 추가
- MEDIUM #5: gr.Markdown label 미표시 → 수정: gr.Accordion 래핑

### 2차 리뷰 (NEEDS_IMPROVEMENT → CRITICAL 수정 후 배포)
- 1차 이슈 4건 모두 수정 확인됨
- CRITICAL #1: _is_safe_sql에 GRANT/REVOKE/CALL/COMMENT/RENAME 미차단 → 수정 완료
- CRITICAL #2: 기본 인증 비밀번호 하드코딩 → 수정 완료 (환경변수 필수)
### WARNING 5건 수정 (2026-02-20)
- W1: 메인 llm 인스턴스에 timeout=60 추가 → 수정 완료
- W2: SQL 실행에 Oracle call_timeout=30000ms 추가 (engine.connect → dbapi_connection) → 수정 완료
- W3: 보고서 프롬프트 인젝션 방지 (question[:500] + <user_input> 구분자) → 수정 완료
- W4: _strip_sql_comments() 함수 추가, _is_safe_sql에서 주석 제거 후 검사 → 수정 완료
- W5: ask_hr() try/except를 LLM 호출(1단계)과 SQL 실행(2단계)으로 분리, 오류 메시지 세분화 → 수정 완료

---

## 미션 2: 모델 선택 UI
- 원본 요청: WebUI에서 현재 선택된 모델을 보여주고 다른 LLM 모델을 선택할 수 있게 해줘
- 부가 질문: 현재 모델이 TEXT2SQL에만 특화된 건지, 범용 AI 챗봇 기능도 가능한지
- 시작 시각: 2026-02-20

### 모델 조사 결과
- gpt-oss-120b: OpenAI 범용 오픈소스 추론 모델 (MoE 117B, Apache 2.0)
- Text2SQL 전용 아님 → 챗봇, 코딩, 수학, 도구 사용 등 모든 범용 AI 작업 가능
- reasoning_content 필드 지원 (추론 과정 노출)
- 현재 GPU 0-3에 TP4로 서빙 중 (각 GPU ~90GB 사용)

### 서버 모델 현황
- GPU 4: 유휴 (95GB VRAM)
- 서버 내 약 90개 모델 디렉토리 보유 (Llama-3.3-70B, Qwen3 시리즈, EXAONE, Phi-4 등)
- 현재 vLLM에는 gpt-oss-120b 1개만 로드됨

### 설계 결정
- 접근법: 모델 레지스트리(MODEL_REGISTRY) 기반 멀티 vLLM 인스턴스 라우팅
- 근거: vLLM은 인스턴스당 1모델 서빙 → 별도 포트에 별도 모델 → UI에서 선택 시 base_url만 변경
- 파일 변경: config.py(레지스트리 추가), model_registry.py(신규), text2sql_pipeline.py(LLM 팩토리), app.py(드롭다운)
- UI: 상단에 모델 드롭다운 + 새로고침 버튼 + 상태 표시
- 캐싱: 모델별 ChatOpenAI 인스턴스 캐싱 (thread-safe, lock 내부 생성)
- 확장: GPU 4에 새 모델 추가 시 config만 수정하면 됨

### 리뷰 및 수정
- C2: LLM 캐시 TOCTOU race condition → 인스턴스 생성을 lock 내부로 이동
- W2: model_key 클라이언트 조작 방지 → process_question에서 MODEL_REGISTRY 검증
- W5: 미사용 글로벌 llm/report_llm 인스턴스 제거 → get_llm()/get_report_llm() 팩토리만 사용
- C1(.env 관리): 운영 보안 주의사항으로 기록 (코드 변경 아닌 운영 대응 필요)

### GPU 4 모델 추가 (2026-02-20)
- Qwen3-30B-A3B-Thinking-2507-FP8 → GPU 4, 포트 8001, systemd: vllm-qwen3 (초기 배포)
- EXAONE-Deep-32B → config에 주석 등록 (Qwen3과 교체 가능)
- Llama-4-Scout-17B-16E → 제외 (405GB, 단일 GPU 불가)

### Qwen3 → EXAONE 교체 (2026-02-20)
- 사용자 요청: "Qwen3 대신에 Exaone을 사용하는게 좋겠어"
- 배경: GPU가 물리적으로 분리되어 있어 2개 모델 동시 로드 시 성능 영향 없음
- 작업 내용:
  - vllm-qwen3 서비스 중지 및 비활성화 (inactive, disabled)
  - vllm-exaone.service 생성 → EXAONE-Deep-32B, GPU 4, 포트 8001 (active, enabled)
  - config.py: exaone-deep-32b 활성화, qwen3-30b 주석 처리
  - text2sql-ui 서비스 재시작
- EXAONE 추론 테스트 성공: "안녕하세요! 저는 LG AI Research에서 개발한 대규모 언어 모델 EXAONE입니다"
- GPU 4 VRAM 사용량: ~88GB / 95GB

### 최종 완료 상태
- text2sql-ui: active (정상)
- vllm (gpt-oss-120b, GPU 0-3, 포트 8000): 정상
- vllm-exaone (EXAONE-Deep-32B, GPU 4, 포트 8001): active, enabled
- vllm-qwen3: inactive, disabled (서비스 파일 유지, 필요 시 교체 가능)
- UI 드롭다운: 2개 모델 표시 (GPT-OSS 120B + EXAONE Deep 32B)

### EXAONE 컨텍스트 초과 수정 (2026-02-20)
- 문제: 시스템 프롬프트(~7289토큰) + max_tokens(4096) = 11,385 > max_model_len(8192) → 400 에러
- 수정 1: MODEL_REGISTRY에 모델별 max_tokens 필드 추가 (EXAONE: 1024, gpt-oss: 4096)
- 수정 2: get_llm()/get_report_llm()에서 config["max_tokens"] 참조
- 수정 3: EXAONE --max-model-len 8192 → 16384 (vllm-exaone.service)
- 수정 4: GRADIO_PASSWORD를 admin으로 변경 (.env)
- 배포 및 테스트 완료: EXAONE 추론 정상 확인

---

## 미션 3: Text2SQL 최적 모델 조사 (2026-02-20)
- 원본 요청: gpt-oss-120b가 Text2SQL 최고 모델인가? SQLCoder보다 나은가? 더 좋은 모델 조사해줘
- EXAONE은 쿼리 오류 지속으로 사용 불가 판단

### 조사 결과 요약
- gpt-oss-120b: 범용 모델, Text2SQL 추정 성능 BIRD 55~62% (중위권)
- SQLCoder-34b: 2023년 모델, 구세대 — 최신 모델 대비 10%+ 열세
- **Arctic-Text2SQL-R1 (Snowflake)**: 2025년 BIRD 1위, 오픈소스 Text2SQL 최강
  - 7B: BIRD 68.9%, 14B: 70.0%, 32B: 71.83%
  - Qwen2.5-Coder 기반 + GRPO RL 학습, Apache 2.0
  - 14B 모델은 FP16 ~28GB → H100 1장에 여유
- OmniSQL: Spider 1위 (88.3%), BIRD에서는 Arctic보다 약간 열세
- 서버 보유 모델 중 주목: **Qwen3-Coder-30B-A3B-Instruct** (114GB, MoE 활성 3B)

### 추천
- 1순위: Arctic-Text2SQL-R1-14B 다운로드 → GPU 4 배포 (28GB, 가볍고 정확)
- 2순위: 서버 내 Qwen3-Coder-30B-A3B-Instruct → GPU 4 배포 (코딩 특화)
- gpt-oss-120b는 GPU 0-3에서 메인 모델로 유지

### Arctic-Text2SQL-R1-7B 배포 (2026-02-20)
- Arctic-Text2SQL-R1-32B는 HuggingFace 미공개 → 7B 선택 (BIRD 68.9%, 32B ExCoT 68.25%보다 높음)
- HuggingFace에서 다운로드 완료: /install_file_backup/tessinu/Arctic-Text2SQL-R1-7B (15GB)
- vllm-exaone 중지 → vllm-arctic 서비스 생성 (GPU 4, 포트 8001, py312_sr 환경)
- max_model_len=16384, gpu-memory-utilization=0.90
- GPU 4 VRAM: 87,321 / 95,830 MiB
- config.py: arctic-text2sql-7b = 메인(DEFAULT), gpt-oss-120b = 서브
- 추론 테스트 성공: "직급별 인원 수" → 정확한 Oracle SQL 생성 확인
- 서비스 상태: vllm-arctic active, text2sql-ui active

### Arctic 모델 Oracle 비호환 문제 발견 (2026-02-20)
- 증상: Arctic이 LIMIT, strftime() 등 SQLite/MySQL 문법을 생성 → Oracle DB에서 실행 오류
- 원인: BIRD/Spider 벤치마크가 100% SQLite 기반 → Arctic은 SQLite SQL만 학습
- 시스템 프롬프트에 "Oracle SQL만 사용하라"고 지시해도 파인튜닝이 이를 override
- 결론: Oracle DB 환경에서는 gpt-oss-120b(범용 117B)가 Arctic(SQLite 전문 7B)보다 우수
- 조치: DEFAULT_MODEL_KEY를 gpt-oss-120b로 복원, Arctic은 참고용으로 유지
- 교훈: Text2SQL 벤치마크 점수 ≠ Oracle 환경 실전 성능. 벤치마크 DB 엔진(SQLite)과 운영 DB 엔진(Oracle)이 다르면 성능 괴리 발생

### Oracle SQL 최적 모델 조사 (2026-02-20)
- 결론: Oracle SQL 전용 Text2SQL 오픈소스 모델은 존재하지 않음
- BIRD/Spider 벤치마크 = 100% SQLite → 전문 모델은 모두 SQLite 전용
- gpt-oss-120b (117B 범용)가 Oracle SQL에는 현재 최선의 선택
- GPU 4 대안 후보: Qwen3-Coder-30B-A3B-Instruct (서버에 이미 있음, 코딩 특화 MoE)
- 프롬프트 강화 + Few-shot Oracle SQL 예시 추가로 정확도 향상 가능
- 장기적: SQLGlot(SQLite→Oracle 변환), ExeSQL 방식 파인튜닝 검토

### Qwen3-Coder-30B-A3B-Instruct 배포 (2026-02-20)
- Arctic 중지/비활성화 → Qwen3-Coder 서비스 생성 (GPU 4, 포트 8001)
- vllm-qwen3-coder.service: py312_sr 환경, max-model-len=32768
- GPU 4 VRAM: 87,485 / 95,830 MiB (91.3%)
- 모델 로딩 소요시간: 약 9분
- 추론 테스트 성공: Oracle 문법 완벽 사용 (NVL, TO_NUMBER, FETCH FIRST)
- config.py: qwen3-coder-30b 활성화, arctic 주석 처리
- 서비스 상태: vllm-qwen3-coder active, text2sql-ui active

## 서버 배포 상태
- text2sql-ui 서비스: active (정상)
- vLLM 서비스 (gpt-oss-120b, GPU 0-3, 포트 8000): 정상
- vLLM 서비스 (EXAONE-Deep-32B, GPU 4, 포트 8001): 정상
- 총 5회 배포 (초기 구현 → 1차 이슈 수정 → 2차 CRITICAL 수정 → WARNING 5건 수정 → 모델 선택 UI + EXAONE 교체)

---

## [2026-02-20] GPT-OSS vs Qwen3-Coder 비교 분석 및 프롬프트 개선

### 모델 비교 결과
- GPT-OSS 120B: 4/4 성공 (100%), 단순하고 안정적인 쿼리
- Qwen3-Coder 30B: 3/4 성공 (75%), 한글 별칭 사용하나 JOIN 오류 발생
- **결론**: GPT-OSS를 메인 모델로 유지, Qwen3-Coder는 테스트용

### 변경사항
1. **config.py**: Qwen3-Coder display_name → "(테스트)", description → "테스트/비교용 모델"
2. **text2sql_pipeline.py SYSTEM_PROMPT**: 3개 규칙 추가
   - Rule 7: 한글 별칭 사용 지시 (AS "한글명")
   - Rule 8: 다중 테이블 JOIN 가이드 (명시적 ON 조건 포함)
   - Rule 9: 불필요한 JOIN 금지 (단일 테이블 충분 시)
3. DEFAULT_MODEL_KEY = "gpt-oss-120b" (기존 유지 확인)

### 리뷰 결과
- 1차 리뷰: NEEDS_IMPROVEMENT (JOIN 예시 모호)
- 수정 후 배포: Rule 8 JOIN 예시를 명시적 ON 조건으로 수정
- 서비스 재시작 완료 (active/running)

---

## [2026-02-20] Git 이력 관리 시스템 구축

### 결정사항
- Git 로컬 저장소 초기화 + GitHub 프라이빗 저장소 생성
- 모든 비밀번호를 환경변수로 교체 (보안 강화)

### 생성된 파일
1. **.gitignore** — .env, __pycache__, IDE, OS 파일 제외
2. **app/.env.example** — 환경변수 템플릿 (비밀번호 플레이스홀더)
3. **CHANGELOG.md** — 8개 Phase 전체 작업 이력 기록 (역순)
4. **OPERATIONS.md** — Linux 초보자용 서버 운영 가이드 (한국어, 11개 섹션)

### 보안 수정
- 17개 파일에서 하드코딩된 비밀번호 제거 (SSH: spelix12#$, Oracle: hrai_con01)
- 모두 os.environ.get("SSH_PASSWORD", "") 또는 (환경변수 참조) 로 교체
- Git 히스토리 완전 초기화 후 클린 커밋으로 재생성
- GitHub 저장소: https://github.com/Spelix-Ksj/Linux_LLM (PRIVATE)

### 권장 사항 (사용자 조치 필요)
- SSH 루트 비밀번호 변경 (서버 192.168.10.40)
- Oracle DB 비밀번호 변경 (HRAI_CON 계정)

---

## [2026-02-21] 미션 6: UI 기능 개선 (SQL 분리, 이력 SQL, 스키마 확대, JS 효과)

### 원본 요청
- SQL 생성 버튼과 SQL 실행 버튼 분리 (현재는 "SQL 생성 및 실행" 1개 버튼)
- 생성된 SQL 텍스트를 사용자가 수정 가능하게
- 질의 이력 탭에서 행 선택 시 해당 SQL 쿼리 표시
- 스키마 정보 탭이 너무 작게 보임 → 크기 개선
- "반응형"은 Responsive가 아니라 React 스타일 JavaScript 효과를 의미 (사용자 명확화)

### 설계 결정
1. **text2sql_pipeline.py**: `ask_hr()` 내부를 2개 함수로 분리
   - `generate_sql(question, model_key)` → SQL만 생성, dict{sql, reasoning, error} 반환
   - `execute_sql(sql_text)` → SQL 실행, dict{result(DataFrame), error} 반환
   - `ask_hr()` 유지 (하위 호환, 두 함수 순차 호출)
2. **app.py UI 변경**:
   - "SQL 생성" 버튼 + "SQL 실행" 버튼 분리
   - `gr.Code` → `gr.Textbox(lines=8, language="sql")` 또는 `gr.Code(interactive=True)` (편집 가능)
   - `_query_history`에 SQL 저장 추가
   - 질의 이력 탭에 `gr.Code` 추가하여 선택된 행의 SQL 표시
   - 스키마 정보 탭: CSS에서 폰트 크기/여백 확대
   - CSS 반응형 미디어쿼리 제거, JavaScript 효과 추가 (애니메이션, 트랜지션)

### 팀 구성
- 개발자 1: text2sql_pipeline.py 수정
- 개발자 2: app.py 전면 수정
- 검토자: 비판적 코드 리뷰
- 수정자: 검토 이슈 6건 수정

### 리뷰 결과
- 1차 리뷰: NEEDS_IMPROVEMENT (15개 이슈 발견)
- 수정 후 배포: HIGH 3건 + MEDIUM 3건 수정 완료
- 주요 수정사항:
  - CSS/theme를 demo.launch()에서 gr.Blocks()로 이동 (Critical — 스타일 미적용 문제)
  - SQL Textbox에 interactive=True + info 안내 텍스트 추가
  - MutationObserver 범위를 특정 클래스만으로 제한 (성능 개선)
  - execute_sql에서 trailing comment 제거 후 SQL 래핑
  - raw LLM 출력 에러 메시지 제거 (보안)
  - _on_history_select 타입 가드 추가

### 배포 결과
- 서버 192.168.10.40: app.py + text2sql_pipeline.py 배포 완료
- text2sql-ui 서비스: active (running), PID 2827584
- GitHub 커밋: 986b83e (main 브랜치)

---

## [2026-02-21] 미션 7: 드라마틱 SaaS 대시보드 UI 전면 개편

### 원본 요청
- "드라마틱한 효과는 없는거네? 첨부한 이미지처럼의 디자인은 안되는거야?"
- 참조 이미지: SaaS 대시보드 스타일 (보라색 그래디언트 헤더, KPI 카드, 모던 테이블)

### 설계 결정
- `gr.HTML()` 컴포넌트를 활용하여 커스텀 HTML/CSS 섹션 구현 가능 확인
- 히어로 헤더: 보라-핑크 그래디언트, Live 배지, 실시간 시계, KPI 배지
- 통계 카드: 3열 플렉스 레이아웃, 카운터 애니메이션, 호버 효과
- Google Inter 폰트 로딩 (head 파라미터)
- JavaScript: 실시간 시계, 카운터 애니메이션, MutationObserver

### 변경 내용
1. **히어로 헤더** (gr.HTML): 그래디언트 배경, 장식 원형, 유리 효과 Live 배지, 실시간 시계, KPI 원형 배지
2. **통계 카드 3개** (gr.HTML): 총 질의수/성공률/평균조회건수, 컬러 하단 보더, 이모지 아이콘, 호버 리프트 효과
3. **CSS 전면 교체**: #f0f2f5 배경, 필 스타일 탭, 그래디언트 선택 탭, 다크 테마 SQL 에디터
4. **JavaScript**: 한국어 시계(초 단위), 카운터 카운트업 애니메이션, 디바운스된 MutationObserver
5. **실행 버튼 색상 분리**: SQL 생성(보라), SQL 실행(초록)

### 리뷰 결과
- 1차: NEEDS_IMPROVEMENT (CRITICAL 1건, MEDIUM 2건, LOW 4건)
- 수정사항: hex alpha → rgba, MutationObserver 디바운스, 카운터 0값 가드, 동적 KPI 배지
- 기능 보존 완벽 확인 (모든 이벤트 핸들러 입출력 일치)

### 배포
- 서버 192.168.10.40: text2sql-ui active (running), PID 2828306
- GitHub 커밋: cab1b04 (main 브랜치, +528/-125 lines)
