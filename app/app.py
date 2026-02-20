"""
Step 6: Gradio 웹 UI (v2 — Tabs, History, CSV Export, Progress)
자연어로 Oracle HR DB에 질의하는 웹 인터페이스
실행: python app.py
"""
import os
import datetime
import tempfile
import threading

import gradio as gr
import pandas as pd

from text2sql_pipeline import ask_hr, generate_report
from config import GRADIO_HOST, GRADIO_PORT, DEFAULT_MODEL_KEY, MODEL_REGISTRY
from model_registry import get_display_choices, get_available_models


# ===== 반응형 CSS =====
custom_css = """
@media (max-width: 768px) {
    .gradio-container { padding: 4px !important; }
    #model-row, #query-row { flex-direction: column !important; }
}
.status-success { color: #16a34a; font-weight: bold; }
.status-error { color: #dc2626; font-weight: bold; }
"""


# ===== 스키마 정보 마크다운 =====
schema_info_markdown = """
## 사용 가능한 테이블

### 1. move_item_master (직원 마스터)
| 컬럼명 | 한글명 | 설명 |
|--------|--------|------|
| emp_nm | 이름 | 직원 성명 |
| pos_grd_nm | 직급 | 직급명 |
| org_nm | 현재조직 | 소속 부서명 |
| lvl1~5_nm | 조직계층 | 1~5단계 조직 계층명 |
| job_type1/2 | 직종 | 직종 분류 |
| gender_nm | 성별 | 성별 |
| year_desc | 연령대 | 연령대 구분 |
| org_work_mon | 조직근무개월 | 현 조직 근무 개월수 |
| region_type | 지역구분 | 근무 지역 |

### 2. move_org_master (조직 마스터)
| 컬럼명 | 한글명 | 설명 |
|--------|--------|------|
| org_nm | 조직명 | 조직/부서명 |
| org_type | 조직유형 | 조직 유형 분류 |
| tot_to | 정원 | 배정 정원 |
| region_type | 지역구분 | 조직 소재 지역 |
| job_type1/2 | 직종 | 조직 직종 분류 |

### 3. move_case_item (배치안 상세)
| 컬럼명 | 한글명 | 설명 |
|--------|--------|------|
| new_lvl1~5_nm | 새조직계층 | 이동 후 조직 계층 |
| must_stay_yn | 잔류필수 | 잔류 필수 여부 |
| must_move_yn | 이동필수 | 이동 필수 여부 |

### 4. move_case_cnst_master (제약조건)
| 컬럼명 | 한글명 | 설명 |
|--------|--------|------|
| cnst_nm | 제약조건명 | 제약 조건 이름 |
| cnst_val | 제약값 | 제약 조건 값 |
| penalty_val | 위반패널티 | 위반 시 패널티 점수 |

### 테이블 관계
```
move_item_master ──org_nm──> move_org_master
move_item_master <──emp_no──> move_case_item
move_case_item ──case_id──> move_case_cnst_master
```
"""


# ===== 질의 이력 (in-memory) =====
_history_lock = threading.Lock()
_query_history = []  # List of dicts


def _add_to_history(question, model_key, status, count):
    """질의 이력에 새 항목 추가 (최대 50건 유지)"""
    with _history_lock:
        _query_history.insert(0, {
            "시간": datetime.datetime.now().strftime("%H:%M:%S"),
            "모델": model_key,
            "질문": question[:50],
            "상태": status,
            "건수": count,
        })
        if len(_query_history) > 50:
            _query_history.pop()


def _get_history():
    """현재 질의 이력을 DataFrame으로 반환"""
    with _history_lock:
        if not _query_history:
            return pd.DataFrame(columns=["시간", "모델", "질문", "상태", "건수"])
        return pd.DataFrame(_query_history)


def _clear_history():
    """질의 이력 전체 삭제"""
    with _history_lock:
        _query_history.clear()
    return _get_history()


# ===== CSV 내보내기 =====
def _export_csv(df):
    """조회 결과를 CSV 파일로 내보내기 (한글 Excel 호환 BOM 포함)"""
    if not isinstance(df, pd.DataFrame) or df.empty:
        return gr.update(visible=False)
    fd, path = tempfile.mkstemp(suffix=".csv", prefix="query_result_")
    os.close(fd)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return gr.update(value=path, visible=True)


# ===== 모델 상태 마크다운 빌더 =====
def _build_model_status(model_key):
    """선택된 모델의 상태 정보를 마크다운으로 반환"""
    models = get_available_models()
    for m in models:
        if m["key"] == model_key:
            status = "정상" if m["healthy"] else "응답 없음"
            return f"**현재 모델**: {m['display_name']} | **상태**: {status} | **GPU**: {m['gpu_info']}"
    return f"**현재 모델**: {model_key} (정보 없음)"


def _refresh_models():
    """모델 목록 새로고침 -- Dropdown choices 및 상태 마크다운 갱신"""
    choices = get_display_choices()
    current_keys = [c[1] for c in choices]
    default = DEFAULT_MODEL_KEY if DEFAULT_MODEL_KEY in current_keys else (current_keys[0] if current_keys else DEFAULT_MODEL_KEY)
    status_md = _build_model_status(default)
    return gr.update(choices=choices, value=default), status_md


def _on_model_change(model_key):
    """모델 드롭다운 변경 시 상태 마크다운 업데이트"""
    return _build_model_status(model_key)


# ===== 핵심 질의 처리 =====
def process_question(question: str, model_key: str, progress=gr.Progress()):
    """자연어 질문을 처리하여 SQL, 결과, 상태, 보고서, 이력을 반환"""
    if not question or not question.strip():
        return "", pd.DataFrame(), "", "", _get_history()

    # model_key 유효성 검증 (클라이언트 측 조작 방지)
    if model_key not in MODEL_REGISTRY:
        model_key = DEFAULT_MODEL_KEY

    progress(0.1, desc="SQL 생성 중...")
    result = ask_hr(question.strip(), model_key=model_key)
    sql = result["sql"]
    df = result["result"]
    error = result.get("error")
    reasoning = result.get("reasoning", "")

    progress(0.5, desc="결과 처리 중...")

    if error:
        status = f"오류 발생: {error}"
        _add_to_history(question.strip(), model_key, "오류", 0)
        progress(1.0, desc="완료")
        return sql, df, status, "", _get_history()

    status = f"조회 완료: {len(df)}건"

    progress(0.8, desc="보고서 생성 중...")
    report = generate_report(question.strip(), sql, df, reasoning, model_key=model_key)

    progress(1.0, desc="완료")
    _add_to_history(question.strip(), model_key, "성공", len(df))

    return sql, df, status, report, _get_history()


# ===== Gradio UI 구성 =====
with gr.Blocks(title="HR Text2SQL 시스템") as demo:
    gr.Markdown("# 인사정보 Text2SQL 시스템")
    gr.Markdown("자연어로 질문하면 Oracle HR DB에서 결과를 조회합니다.")

    # 모델 선택 영역 (탭 밖 — 항상 표시)
    with gr.Row(elem_id="model-row"):
        model_dropdown = gr.Dropdown(
            label="모델 선택",
            choices=get_display_choices(),
            value=DEFAULT_MODEL_KEY,
            scale=4,
        )
        refresh_btn = gr.Button("새로고침", size="sm", scale=1)

    model_status = gr.Markdown(value=_build_model_status(DEFAULT_MODEL_KEY))

    with gr.Tabs():
        # ===== 탭 1: SQL 질의 =====
        with gr.Tab("SQL 질의"):
            with gr.Row(elem_id="query-row"):
                question_input = gr.Textbox(
                    label="질문 입력",
                    placeholder="예: 직급별 인원 수를 구해줘",
                    lines=2,
                    scale=4,
                    min_width=300,
                )
                submit_btn = gr.Button(
                    "SQL 생성 및 실행",
                    variant="primary",
                    scale=1,
                    min_width=120,
                )

            status_output = gr.Textbox(label="상태", interactive=False)

            with gr.Row():
                with gr.Column(scale=1):
                    sql_output = gr.Code(label="생성된 SQL", language="sql")
                    download_btn = gr.Button("CSV 다운로드", size="sm", variant="secondary")
                    download_file = gr.File(label="다운로드", visible=False)

            result_output = gr.Dataframe(
                label="조회 결과",
                wrap=True,
                max_height=500,
            )

            with gr.Accordion("결과 보고서", open=True):
                report_output = gr.Markdown(value="")

            # 예시 질문
            gr.Examples(
                examples=[
                    ["직급별 인원 수를 구해줘"],
                    ["조직별 평균 조직근무개월을 구해줘"],
                    ["성별 인원 분포를 보여줘"],
                    ["지역구분별 인원 수를 구해줘"],
                    ["이동필수 대상자 목록을 보여줘"],
                ],
                inputs=question_input,
            )

        # ===== 탭 2: 질의 이력 =====
        with gr.Tab("질의 이력"):
            history_output = gr.Dataframe(
                label="최근 질의 이력",
                headers=["시간", "모델", "질문", "상태", "건수"],
                wrap=True,
            )
            clear_history_btn = gr.Button("이력 삭제", size="sm", variant="stop")

        # ===== 탭 3: 스키마 정보 =====
        with gr.Tab("스키마 정보"):
            gr.Markdown(schema_info_markdown)

    # ===== 이벤트 핸들러 =====

    # 모델 드롭다운 변경 시 상태 업데이트
    model_dropdown.change(
        fn=_on_model_change,
        inputs=model_dropdown,
        outputs=model_status,
    )

    # 새로고침 버튼 클릭 시 모델 목록 및 상태 갱신
    refresh_btn.click(
        fn=_refresh_models,
        inputs=[],
        outputs=[model_dropdown, model_status],
    )

    # SQL 생성 및 실행 (버튼 클릭)
    submit_btn.click(
        fn=process_question,
        inputs=[question_input, model_dropdown],
        outputs=[sql_output, result_output, status_output, report_output, history_output],
        concurrency_limit=3,
    )

    # SQL 생성 및 실행 (Enter 키 제출)
    question_input.submit(
        fn=process_question,
        inputs=[question_input, model_dropdown],
        outputs=[sql_output, result_output, status_output, report_output, history_output],
        concurrency_limit=3,
    )

    # CSV 다운로드
    download_btn.click(
        fn=_export_csv,
        inputs=[result_output],
        outputs=[download_file],
    )

    # 이력 삭제
    clear_history_btn.click(
        fn=_clear_history,
        inputs=[],
        outputs=[history_output],
    )


# 서버 시작
if __name__ == "__main__":
    gradio_user = os.environ.get("GRADIO_USER")
    gradio_password = os.environ.get("GRADIO_PASSWORD")
    if not gradio_user or not gradio_password:
        raise RuntimeError("GRADIO_USER and GRADIO_PASSWORD environment variables must be set")

    demo.launch(
        server_name=GRADIO_HOST,
        server_port=GRADIO_PORT,
        share=False,
        show_error=False,
        auth=(gradio_user, gradio_password),
        theme=gr.themes.Soft(),
        css=custom_css,
    )
