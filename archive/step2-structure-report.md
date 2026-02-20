프로젝트 구조

 D:\Dev\Linux_LLM/
 ├── upload_to_server.sh           ← 로컬→서버 파일 전송 (SCP)
 │
 ├── deploy/                       ← 서버 설치 스크립트
 │   ├── 01_check_environment.sh   ← GPU/CUDA/메모리 확인
 │   ├── 02_install_system_deps.sh ← dnf 패키지, 방화벽 설정
 │   ├── 03_install_miniconda.sh   ← Miniconda + text2sql 가상환경
 │   ├── 04_install_vllm.sh        ← vLLM 설치
 │   ├── 05_install_app_deps.sh    ← oracledb, langchain, gradio 등
 │   ├── 06_setup_services.sh      ← systemd 서비스 등록
 │   └── deploy_all.sh             ← 마스터 배포 (전체 or 단계별)
 │
 ├── app/                          ← Python 애플리케이션
 │   ├── .env                      ← 환경 설정 (DB 비밀번호 등)
 │   ├── config.py                 ← .env 로더 + 설정 상수
 │   ├── db_setup.py               ← Oracle DB 연결 테스트/스키마 확인
 │   ├── text2sql_pipeline.py      ← LangChain Text2SQL 핵심 파이프라인
 │   ├── app.py                    ← Gradio 웹 UI
 │   └── test_e2e.py               ← 통합 테스트
 │
 └── services/                     ← systemd 서비스 파일
     ├── vllm.service              ← 34B 모델 서빙 (프로덕션)
     ├── vllm-7b.service           ← 7B 모델 서빙 (테스트용)
     └── text2sql-ui.service       ← Gradio 웹 UI

 계획 대비 개선 사항

 1. 보안: DB 비밀번호를 .env 파일로 분리하고 config.py가 환경변수 우선으로 로드
 2. SQL 안전장치: _is_safe_sql() 함수로 DML/DDL 차단, _clean_sql()로 LLM 출력 정리
 3. 7B 테스트 서비스: vllm-7b.service 추가 (34B 전에 빠르게 검증 가능)
 4. 마스터 스크립트: deploy_all.sh에서 --from N / --step N 으로 단계별 실행 지원
 5. 파일 전송 스크립트: upload_to_server.sh로 SCP 원클릭 업로드

 배포 순서

 # 1. 로컬에서 서버로 파일 전송
 bash upload_to_server.sh root@192.168.10.40

 # 2. 서버 SSH 접속
 ssh root@192.168.10.40

 # 3. 전체 배포 실행
 cd /root/text2sql
 bash deploy/deploy_all.sh

 # 4. vLLM 시작 (7B로 먼저 테스트 권장)
 sudo systemctl start vllm-7b

 # 5. DB 연결 확인
 conda activate text2sql && python db_setup.py

 # 6. 웹 UI 시작
 sudo systemctl start text2sql-ui

 # 7. 브라우저 접속: http://192.168.10.40:7860

 | 항목 | 계획 | 실제 |
 |------|------|------|
 | GPU | H100 x3 | H100 NVL x5 |
 | Miniconda | /opt/miniconda3 (미설치) | /root/miniconda3 (설치됨) |
 | vLLM | 미설치 | 이미 실행 중 (gpt-oss-120b, TP4, GPU 0~3) |
 | conda env | text2sql (미생성) | py312_sr (Python 3.12, vLLM 포함) |
 | 모델 | defog/sqlcoder-34b-alpha | gpt-oss-120b (120B 범용 모델) |