 H100 GPU 서버 Text2SQL LLM 시스템 구축 계획
                                                            
 Context                             

 Rocky Linux 9.6 서버(H100 GPU 3장, AMD EPYC 9454, 503GB RAM)에 Local LLM 기반 Text2SQL 시스템을 구축한다.
 Oracle HR 데이터베이스(인사정보)에 자연어로 질의하면 SQL을 자동 생성하고 결과를 반환하는 웹 애플리케이션을 만드는 것이 목표.

 확정 사항:
 - LLM 서빙: vLLM (H100 최적화, OpenAI 호환 API)
 - UI: Gradio 웹 인터페이스
 - SSH 접속: 이미 가능
 - GPU 드라이버/CUDA: 이미 설치됨

 ---
 전체 아키텍처

 [사용자 브라우저] → [Gradio 웹 UI (포트 7860)]
                          ↓
               [LangChain Text2SQL 파이프라인]
                     ↓              ↓
         [vLLM 서버 (포트 8000)]   [Oracle DB (HQ.SPELIX.CO.KR:7744)]
         (SQLCoder-34b 모델)        (SID: HISTPRD, User: HRAI_CON)
         (H100 GPU x2~3장)

 ---
 Step 1: 서버 환경 확인 및 기본 설정

 1-1. SSH 접속 후 GPU/CUDA 상태 확인

 # GPU 상태 확인
 nvidia-smi

 # CUDA 버전 확인
 nvcc --version

 # GPU 간 NVLink 연결 확인
 nvidia-smi topo -m

 1-2. 시스템 필수 패키지 설치

 # 개발 도구 및 라이브러리
 sudo dnf groupinstall -y "Development Tools"
 sudo dnf install -y git wget curl bzip2 libffi-devel openssl-devel

 1-3. 방화벽 포트 개방

 # vLLM API 포트 (8000)
 sudo firewall-cmd --permanent --add-port=8000/tcp

 # Gradio 웹 UI 포트 (7860)
 sudo firewall-cmd --permanent --add-port=7860/tcp

 # 적용
 sudo firewall-cmd --reload

 ---
 Step 2: Miniconda 설치 및 Python 환경 구성

 2-1. Miniconda 설치

 # Miniconda 다운로드 및 설치
 wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
 bash Miniconda3-latest-Linux-x86_64.sh -b -p /opt/miniconda3

 # 환경변수 설정
 echo 'export PATH="/opt/miniconda3/bin:$PATH"' >> ~/.bashrc
 source ~/.bashrc
 conda init bash
 source ~/.bashrc

 2-2. 전용 가상환경 생성

 conda create -n text2sql python=3.11 -y
 conda activate text2sql

 ---
 Step 3: vLLM 설치 및 LLM 모델 배포

 3-1. vLLM 설치

 conda activate text2sql
 pip install vllm

 3-2. Text2SQL 모델 다운로드 및 서빙

 권장 모델: defog/sqlcoder-34b-alpha (Text2SQL 특화)
 - SQL 생성 정확도가 GPT-4를 능가하는 오픈소스 모델
 - 34B 파라미터 → FP16 기준 ~70GB VRAM (H100 2장이면 충분)

 # vLLM 서버 시작 (백그라운드 서비스로 실행)
 python -m vllm.entrypoints.openai.api_server \
     --model defog/sqlcoder-34b-alpha \
     --tensor-parallel-size 2 \
     --gpu-memory-utilization 0.90 \
     --max-model-len 4096 \
     --host 0.0.0.0 \
     --port 8000

 옵션: 더 가벼운 모델로 먼저 테스트하려면
 # SQLCoder 7B (빠른 테스트용, GPU 1장)
 python -m vllm.entrypoints.openai.api_server \
     --model defog/sqlcoder-7b-2 \
     --host 0.0.0.0 \
     --port 8000

 3-3. vLLM systemd 서비스 등록 (자동 시작)

 # /etc/systemd/system/vllm.service 파일 생성
 sudo tee /etc/systemd/system/vllm.service << 'EOF'
 [Unit]
 Description=vLLM Text2SQL Server
 After=network.target

 [Service]
 Type=simple
 User=root
 WorkingDirectory=/root
 Environment="PATH=/opt/miniconda3/envs/text2sql/bin:/usr/local/bin:/usr/bin"
 ExecStart=/opt/miniconda3/envs/text2sql/bin/python -m vllm.entrypoints.openai.api_server \
     --model defog/sqlcoder-34b-alpha \
     --tensor-parallel-size 2 \
     --gpu-memory-utilization 0.90 \
     --max-model-len 4096 \
     --host 0.0.0.0 \
     --port 8000
 Restart=on-failure
 RestartSec=10

 [Install]
 WantedBy=multi-user.target
 EOF

 sudo systemctl daemon-reload
 sudo systemctl enable vllm
 sudo systemctl start vllm

 3-4. vLLM 동작 확인

 curl http://localhost:8000/v1/models
 curl http://localhost:8000/v1/completions \
     -H "Content-Type: application/json" \
     -d '{"model": "defog/sqlcoder-34b-alpha", "prompt": "SELECT", "max_tokens": 50}'

 ---
 Step 4: Oracle DB 연결 설정

 4-1. Python Oracle 라이브러리 설치

 conda activate text2sql
 pip install oracledb sqlalchemy

 python-oracledb Thin 모드 사용 → Oracle Instant Client 설치 불필요

 4-2. DB 연결 및 테이블 스키마 확인 스크립트

 # db_setup.py
 import oracledb
 from sqlalchemy import create_engine, inspect, text

 # Oracle DB 접속 설정
 DB_CONFIG = {
     "user": "HRAI_CON",
     "password": "(환경변수 ORACLE_PASSWORD 참조)",
     "host": "HQ.SPELIX.CO.KR",
     "port": 7744,
     "sid": "HISTPRD"
 }

 # SQLAlchemy 엔진 생성
 engine = create_engine(
     "oracle+oracledb://",
     connect_args=DB_CONFIG,
     pool_size=5,
     max_overflow=10
 )

 # 연결 테스트
 with engine.connect() as conn:
     result = conn.execute(text("SELECT 1 FROM dual"))
     print("DB 연결 성공:", result.fetchone())

 # 대상 테이블 스키마 조회
 inspector = inspect(engine)
 target_tables = ["move_item_master", "move_case_item",
                  "move_case_cnst_master", "move_org_master"]

 for table_name in target_tables:
     columns = inspector.get_columns(table_name, schema="HRAI_CON")
     print(f"\n=== {table_name} ===")
     for col in columns:
         print(f"  {col['name']}: {col['type']}")

 4-3. 네트워크 연결 확인

 # DNS 확인
 nslookup HQ.SPELIX.CO.KR

 # 포트 연결 확인
 nc -zv HQ.SPELIX.CO.KR 7744

 ---
 Step 5: LangChain Text2SQL 파이프라인 구축

 5-1. 필요 패키지 설치

 pip install langchain langchain-openai langchain-community langchain-experimental
 pip install pandas

 5-2. Text2SQL 파이프라인 코드

 파일: /root/text2sql/text2sql_pipeline.py
 from langchain_openai import ChatOpenAI
 from langchain_community.utilities import SQLDatabase
 from langchain.chains import create_sql_query_chain
 from langchain_core.prompts import PromptTemplate
 from langchain_core.output_parsers import StrOutputParser
 from sqlalchemy import create_engine, text
 import pandas as pd

 # ===== 1. 데이터베이스 연결 =====
 DB_CONFIG = {
     "user": "HRAI_CON",
     "password": "(환경변수 ORACLE_PASSWORD 참조)",
     "host": "HQ.SPELIX.CO.KR",
     "port": 7744,
     "sid": "HISTPRD"
 }

 engine = create_engine("oracle+oracledb://", connect_args=DB_CONFIG)
 db = SQLDatabase.from_uri(
     engine.url,
     include_tables=["move_item_master", "move_case_item",
                     "move_case_cnst_master", "move_org_master"],
     sample_rows_in_table_info=3
 )

 # ===== 2. Local LLM 연결 (vLLM) =====
 llm = ChatOpenAI(
     model="defog/sqlcoder-34b-alpha",
     base_url="http://localhost:8000/v1",
     api_key="not-needed",
     temperature=0.0,
 )

 # ===== 3. Oracle 전용 Text2SQL 프롬프트 =====
 ORACLE_PROMPT = """당신은 Oracle SQL 전문가입니다.
 아래 테이블 스키마를 참고하여 사용자의 질문에 맞는 Oracle SQL을 생성하세요.

 테이블 정보:
 {table_info}

 규칙:
 1. Oracle SQL 문법만 사용 (NVL, DECODE, ROWNUM 등)
 2. SELECT 문만 생성 (INSERT/UPDATE/DELETE 금지)
 3. SQL 끝에 세미콜론(;) 붙이지 않기
 4. 한글 컬럼명은 큰따옴표로 감싸기
 5. 필요한 컬럼만 조회 (SELECT * 지양)

 질문: {input}

 Oracle SQL:"""

 # ===== 4. 체인 구성 =====
 chain = create_sql_query_chain(llm, db, prompt=PromptTemplate.from_template(ORACLE_PROMPT))

 # ===== 5. 질의 실행 함수 =====
 def ask_hr(question: str) -> dict:
     """자연어 질문을 SQL로 변환하고 실행"""
     generated_sql = chain.invoke({"question": question})

     # SQL 실행
     df = pd.read_sql(text(generated_sql), engine)

     return {
         "question": question,
         "sql": generated_sql,
         "result": df
     }

 참고: 실제 테이블 스키마를 확인한 후, 프롬프트의 테이블 설명과 Few-shot 예시를 보강해야 함

 ---
 Step 6: Gradio 웹 UI 구축

 6-1. Gradio 설치

 pip install gradio

 6-2. 웹 애플리케이션 코드

 파일: /root/text2sql/app.py
 import gradio as gr
 from text2sql_pipeline import ask_hr, engine
 from sqlalchemy import text
 import pandas as pd

 def process_question(question):
     """자연어 질문 처리"""
     try:
         result = ask_hr(question)
         sql = result["sql"]
         df = result["result"]
         return sql, df
     except Exception as e:
         return f"오류 발생: {str(e)}", pd.DataFrame()

 # Gradio UI 구성
 with gr.Blocks(title="HR Text2SQL 시스템", theme=gr.themes.Soft()) as demo:
     gr.Markdown("# 인사정보 Text2SQL 시스템")
     gr.Markdown("자연어로 질문하면 Oracle HR DB에서 결과를 조회합니다.")

     with gr.Row():
         question_input = gr.Textbox(
             label="질문 입력",
             placeholder="예: 직급별 인원 수를 구해줘",
             lines=2
         )

     submit_btn = gr.Button("SQL 생성 및 실행", variant="primary")

     with gr.Row():
         sql_output = gr.Code(label="생성된 SQL", language="sql")

     with gr.Row():
         result_output = gr.Dataframe(label="조회 결과")

     # 예시 질문
     gr.Examples(
         examples=[
             ["직급별 인원 수를 구해줘"],
             ["평균 나이가 가장 높은 부서는 어디야?"],
             ["IT 부서에서 대리급 이상의 직원들만 보여줘"],
         ],
         inputs=question_input,
     )

     submit_btn.click(
         fn=process_question,
         inputs=question_input,
         outputs=[sql_output, result_output]
     )

 # 서버 시작 (외부 접속 허용)
 demo.launch(server_name="0.0.0.0", server_port=7860, share=False)

 6-3. Gradio 앱 systemd 서비스 등록

 sudo tee /etc/systemd/system/text2sql-ui.service << 'EOF'
 [Unit]
 Description=Text2SQL Gradio Web UI
 After=network.target vllm.service

 [Service]
 Type=simple
 User=root
 WorkingDirectory=/root/text2sql
 Environment="PATH=/opt/miniconda3/envs/text2sql/bin:/usr/local/bin:/usr/bin"
 ExecStart=/opt/miniconda3/envs/text2sql/bin/python app.py
 Restart=on-failure
 RestartSec=10

 [Install]
 WantedBy=multi-user.target
 EOF

 sudo systemctl daemon-reload
 sudo systemctl enable text2sql-ui
 sudo systemctl start text2sql-ui

 ---
 Step 7: 테스트 및 검증

 7-1. 단계별 검증 체크리스트

 ┌────────────┬────────────────┬──────────────────────────────────────────────────────────────────────────────────┐
 │    단계    │   확인 사항    │                                   명령어/방법                                    │
 ├────────────┼────────────────┼──────────────────────────────────────────────────────────────────────────────────┤
 │ GPU        │ H100 3장 인식  │ nvidia-smi                                                                       │
 ├────────────┼────────────────┼──────────────────────────────────────────────────────────────────────────────────┤
 │ vLLM       │ 모델 서빙 동작 │ curl http://localhost:8000/v1/models                                             │
 ├────────────┼────────────────┼──────────────────────────────────────────────────────────────────────────────────┤
 │ Oracle     │ DB 연결 성공   │ python db_setup.py                                                               │
 ├────────────┼────────────────┼──────────────────────────────────────────────────────────────────────────────────┤
 │ 파이프라인 │ SQL 생성 정상  │ python -c "from text2sql_pipeline import ask_hr; print(ask_hr('직급별 인원수'))" │
 ├────────────┼────────────────┼──────────────────────────────────────────────────────────────────────────────────┤
 │ 웹 UI      │ 브라우저 접속  │ http://192.168.10.40:7860                                                        │
 └────────────┴────────────────┴──────────────────────────────────────────────────────────────────────────────────┘

 7-2. 통합 테스트

 # test_e2e.py
 from text2sql_pipeline import ask_hr

 questions = [
     "직급별 인원 수를 구해줘",
     "평균 나이가 가장 높은 부서는 어디야?",
     "IT 부서에서 대리급 이상의 직원들만 보여줘"
 ]

 for q in questions:
     result = ask_hr(q)
     print(f"\n질문: {result['question']}")
     print(f"SQL:\n{result['sql']}")
     print(f"결과:\n{result['result']}\n")

 ---
 설치 패키지 요약

 시스템 레벨 (dnf)

 - Development Tools (그룹), git, wget, curl

 Python 패키지 (pip)

 ┌──────────────────────────────────────────────────┬─────────────────────────────────┐
 │                      패키지                      │              용도               │
 ├──────────────────────────────────────────────────┼─────────────────────────────────┤
 │ vllm                                             │ LLM 모델 서빙 (OpenAI 호환 API) │
 ├──────────────────────────────────────────────────┼─────────────────────────────────┤
 │ langchain, langchain-openai, langchain-community │ Text2SQL 파이프라인             │
 ├──────────────────────────────────────────────────┼─────────────────────────────────┤
 │ oracledb                                         │ Oracle DB 연결 (Thin 모드)      │
 ├──────────────────────────────────────────────────┼─────────────────────────────────┤
 │ sqlalchemy                                       │ DB ORM / 스키마 반영            │
 ├──────────────────────────────────────────────────┼─────────────────────────────────┤
 │ pandas                                           │ 쿼리 결과 DataFrame 처리        │
 ├──────────────────────────────────────────────────┼─────────────────────────────────┤
 │ gradio                                           │ 웹 UI                           │
 └──────────────────────────────────────────────────┴─────────────────────────────────┘

 ---
 실행 순서 요약

 1. SSH 접속 → 서버 환경 확인 (nvidia-smi, nvcc)
 2. Miniconda 설치 → conda 가상환경 생성
 3. vLLM 설치 → SQLCoder 모델 다운로드 → 서빙 시작
 4. Oracle 연결 테스트 → 테이블 스키마 확인
 5. LangChain Text2SQL 파이프라인 코드 작성
 6. Gradio 웹 UI 코드 작성
 7. 통합 테스트 → systemd 서비스 등록

 ---
 주의사항

 1. 모델 첫 다운로드: SQLCoder-34b는 약 68GB → 네트워크 속도에 따라 시간 소요
 2. DB 비밀번호 관리: 코드에 직접 넣지 않고 환경변수(ORACLE_PASSWORD) 사용 권장
 3. 테이블 스키마 확인 필수: 실제 컬럼명/데이터타입을 확인한 후 프롬프트를 정교화해야 SQL 정확도가 올라감
 4. 먼저 작은 모델(7B)로 테스트 후 34B로 업그레이드하는 것을 권장
 5. vLLM 서버가 완전히 시작된 후 (모델 로딩 완료) Gradio 앱을 시작해야 함