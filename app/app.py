"""
Step 6: Gradio 웹 UI (v3 — Split Generate/Execute, Editable SQL, History SQL, Animations)
자연어로 Oracle HR DB에 질의하는 웹 인터페이스
실행: python app.py
"""
import os
import datetime
import tempfile
import threading

import gradio as gr
import pandas as pd

from text2sql_pipeline import generate_sql, execute_sql, generate_report
from config import GRADIO_HOST, GRADIO_PORT, DEFAULT_MODEL_KEY, MODEL_REGISTRY
from model_registry import get_display_choices, get_available_models


# ===== CSS =====
custom_css = """
/* === 전체 배경 및 폰트 === */
.gradio-container {
    max-width: 1200px !important;
    margin: auto !important;
    font-family: 'Pretendard', 'Apple SD Gothic Neo', 'Noto Sans KR', sans-serif !important;
}

/* === 헤더 스타일 === */
.main-title {
    text-align: center !important;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    font-size: 2.2em !important;
    font-weight: 800 !important;
    margin-bottom: 0 !important;
}
.sub-title {
    text-align: center !important;
    color: #6b7280 !important;
    font-size: 1.05em !important;
    margin-top: 4px !important;
}

/* === 카드 스타일 (섹션 구분) === */
.model-section {
    background: linear-gradient(to right, #f0f4ff, #faf5ff) !important;
    border: 1px solid #e0e7ff !important;
    border-radius: 12px !important;
    padding: 16px !important;
    margin-bottom: 12px !important;
}

/* === 버튼 스타일 === */
.primary-btn {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
    border: none !important;
    color: white !important;
    font-weight: 600 !important;
    border-radius: 10px !important;
    padding: 10px 24px !important;
    transition: all 0.3s ease !important;
    box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3) !important;
}
.primary-btn:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 6px 20px rgba(102, 126, 234, 0.4) !important;
}

/* === 상태 표시 === */
.status-success { color: #059669 !important; font-weight: 600 !important; }
.status-error { color: #dc2626 !important; font-weight: 600 !important; }

/* === SQL 코드 블록 === */
.sql-output {
    border-radius: 10px !important;
    border: 1px solid #e5e7eb !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08) !important;
}

/* === 데이터프레임 === */
.result-table {
    border-radius: 10px !important;
    overflow: hidden !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08) !important;
}

/* === 탭 스타일 === */
.tabs > .tab-nav > button {
    font-weight: 600 !important;
    font-size: 1.05em !important;
    padding: 10px 20px !important;
}
.tabs > .tab-nav > button.selected {
    border-bottom: 3px solid #667eea !important;
    color: #667eea !important;
}

/* === 아코디언 (보고서) === */
.report-accordion {
    border: 1px solid #e0e7ff !important;
    border-radius: 10px !important;
    margin-top: 12px !important;
}

/* === 스키마 탭 크기 보정 === */
.schema-tab { font-size: 1.1em !important; line-height: 1.8 !important; }
.schema-tab table { width: 100% !important; }
.schema-tab th, .schema-tab td { padding: 8px 12px !important; }
"""


# ===== React-style JavaScript effects =====
custom_js = """
function() {
    // Fade-in animation for elements
    const style = document.createElement('style');
    style.textContent = `
        @keyframes fadeInUp {
            from { opacity: 0; transform: translateY(20px); }
            to { opacity: 1; transform: translateY(0); }
        }
        @keyframes slideIn {
            from { opacity: 0; transform: translateX(-20px); }
            to { opacity: 1; transform: translateX(0); }
        }
        @keyframes pulse {
            0% { box-shadow: 0 0 0 0 rgba(102, 126, 234, 0.4); }
            70% { box-shadow: 0 0 0 10px rgba(102, 126, 234, 0); }
            100% { box-shadow: 0 0 0 0 rgba(102, 126, 234, 0); }
        }
        .gradio-container .tabs > .tab-nav > button { transition: all 0.3s ease !important; }
        .gradio-container .tabs > .tab-nav > button:hover { transform: scale(1.05); }
        .gradio-container .tabs > .tab-nav > button.selected { animation: pulse 2s infinite; }
        .gradio-container input, .gradio-container textarea { transition: border-color 0.3s ease, box-shadow 0.3s ease !important; }
        .gradio-container input:focus, .gradio-container textarea:focus {
            border-color: #667eea !important;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.15) !important;
        }
        .result-table { animation: fadeInUp 0.5s ease-out; }
        .report-accordion { animation: fadeInUp 0.6s ease-out; }
        .model-section { animation: slideIn 0.4s ease-out; }
    `;
    document.head.appendChild(style);

    // Observe for dynamically loaded content and animate
    const observer = new MutationObserver((mutations) => {
        mutations.forEach((mutation) => {
            mutation.addedNodes.forEach((node) => {
                if (node.nodeType === 1 && node.querySelector) {
                    const targets = node.querySelectorAll('.result-table, .report-accordion, .sql-output');
                    targets.forEach((el) => { el.style.animation = 'fadeInUp 0.5s ease-out'; });
                    if (node.classList && (node.classList.contains('result-table') || node.classList.contains('report-accordion'))) {
                        node.style.animation = 'fadeInUp 0.5s ease-out';
                    }
                }
            });
        });
    });

    const container = document.querySelector('.gradio-container');
    if (container) {
        observer.observe(container, { childList: true, subtree: false });
    }
}
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
_query_history = []  # List of dicts (display fields)
_query_history_sqls = []  # Parallel list of full SQL strings


def _add_to_history(question, model_key, status, count, sql):
    """질의 이력에 새 항목 추가 (최대 50건 유지)"""
    with _history_lock:
        _query_history.insert(0, {
            "시간": datetime.datetime.now().strftime("%H:%M:%S"),
            "모델": model_key,
            "질문": question[:50],
            "상태": status,
            "건수": count,
        })
        _query_history_sqls.insert(0, sql or "")
        if len(_query_history) > 50:
            _query_history.pop()
            _query_history_sqls.pop()


def _get_history():
    """현재 질의 이력을 DataFrame으로 반환"""
    with _history_lock:
        if not _query_history:
            return pd.DataFrame(columns=["시간", "모델", "질문", "상태", "건수"])
        return pd.DataFrame(_query_history)


def _get_history_sqls():
    """현재 질의 이력의 SQL 목록을 반환 (State용)"""
    with _history_lock:
        return list(_query_history_sqls)


def _clear_history():
    """질의 이력 전체 삭제"""
    with _history_lock:
        _query_history.clear()
        _query_history_sqls.clear()
    return _get_history(), [], ""


def _on_history_select(evt: gr.SelectData, sqls):
    """이력 테이블 행 선택 시 해당 SQL 표시"""
    if isinstance(sqls, list) and evt.index and 0 <= evt.index[0] < len(sqls):
        return sqls[evt.index[0]]
    return ""


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


# ===== SQL 생성 (실행하지 않음) =====
def process_generate(question: str, model_key: str, progress=gr.Progress()):
    """SQL만 생성 (실행하지 않음)"""
    if not question or not question.strip():
        return "", "질문을 입력해주세요.", ""
    if model_key not in MODEL_REGISTRY:
        model_key = DEFAULT_MODEL_KEY

    progress(0.3, desc="SQL 생성 중...")
    result = generate_sql(question.strip(), model_key=model_key)
    progress(1.0, desc="완료")

    if result["error"]:
        return result.get("sql", ""), f"오류: {result['error']}", result.get("reasoning", "")
    return result["sql"], "SQL 생성 완료", result.get("reasoning", "")


# ===== SQL 실행 및 결과 반환 =====
def process_execute(sql_text: str, question: str, model_key: str, reasoning: str, progress=gr.Progress()):
    """생성된 SQL을 실행하고 결과 반환"""
    if not sql_text or not sql_text.strip():
        return pd.DataFrame(), "실행할 SQL이 없습니다.", "", _get_history(), _get_history_sqls()
    if model_key not in MODEL_REGISTRY:
        model_key = DEFAULT_MODEL_KEY

    progress(0.3, desc="SQL 실행 중...")
    result = execute_sql(sql_text.strip())

    if result["error"]:
        _add_to_history(question or "(직접 실행)", model_key, "오류", 0, sql_text)
        return pd.DataFrame(), f"오류: {result['error']}", "", _get_history(), _get_history_sqls()

    df = result["result"]

    progress(0.7, desc="보고서 생성 중...")
    report = generate_report(question or "", sql_text, df, reasoning, model_key=model_key)

    progress(1.0, desc="완료")
    _add_to_history(question or "(직접 실행)", model_key, "성공", len(df), sql_text)

    return df, f"조회 완료: {len(df)}건", report, _get_history(), _get_history_sqls()


# ===== Gradio UI 구성 =====
with gr.Blocks(title="HR Text2SQL 시스템", js=custom_js, css=custom_css, theme=gr.themes.Soft()) as demo:
    gr.Markdown(
        "# 인사정보 Text2SQL 시스템",
        elem_classes=["main-title"],
    )
    gr.Markdown(
        "자연어로 질문하면 Oracle HR DB에서 결과를 조회합니다",
        elem_classes=["sub-title"],
    )

    # 모델 선택 영역 (탭 밖 — 항상 표시)
    with gr.Row(elem_id="model-row", elem_classes=["model-section"]):
        model_dropdown = gr.Dropdown(
            label="모델 선택",
            choices=get_display_choices(),
            value=DEFAULT_MODEL_KEY,
            scale=4,
        )
        refresh_btn = gr.Button("새로고침", size="sm", scale=1)

    model_status = gr.Markdown(value=_build_model_status(DEFAULT_MODEL_KEY))

    # Hidden state for reasoning (passed between generate and execute)
    reasoning_state = gr.State("")

    with gr.Tabs():
        # ===== 탭 1: SQL 질의 =====
        with gr.Tab("SQL 질의"):
            with gr.Row(elem_id="query-row"):
                question_input = gr.Textbox(
                    label="질문 입력",
                    placeholder="예: 직급별 인원 수를 구해줘",
                    lines=2,
                    scale=3,
                    min_width=300,
                )
                generate_btn = gr.Button(
                    "SQL 생성",
                    variant="primary",
                    scale=1,
                    min_width=120,
                    elem_classes=["primary-btn"],
                )

            status_output = gr.Textbox(label="상태", interactive=False)

            sql_output = gr.Textbox(
                label="생성된 SQL",
                lines=8,
                max_lines=20,
                interactive=True,
                info="SQL을 직접 수정한 후 'SQL 실행' 버튼을 클릭하세요",
            )

            with gr.Row():
                execute_btn = gr.Button(
                    "SQL 실행",
                    variant="primary",
                    min_width=120,
                    elem_classes=["primary-btn"],
                )
                download_btn = gr.Button("CSV 다운로드", size="sm", variant="secondary")

            download_file = gr.File(label="다운로드", visible=False)

            result_output = gr.Dataframe(
                label="조회 결과",
                wrap=True,
                max_height=500,
                elem_classes=["result-table"],
            )

            with gr.Accordion("결과 보고서", open=True, elem_classes=["report-accordion"]):
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
            history_sql_display = gr.Code(label="선택된 SQL", language="sql")
            history_sqls_state = gr.State([])
            clear_history_btn = gr.Button("이력 삭제", size="sm", variant="stop")

        # ===== 탭 3: 스키마 정보 =====
        with gr.Tab("스키마 정보", elem_classes=["schema-tab"]):
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

    # SQL 생성 (버튼 클릭)
    generate_btn.click(
        fn=process_generate,
        inputs=[question_input, model_dropdown],
        outputs=[sql_output, status_output, reasoning_state],
        concurrency_limit=3,
    )

    # SQL 생성 (Enter 키 제출)
    question_input.submit(
        fn=process_generate,
        inputs=[question_input, model_dropdown],
        outputs=[sql_output, status_output, reasoning_state],
        concurrency_limit=3,
    )

    # SQL 실행 (버튼 클릭)
    execute_btn.click(
        fn=process_execute,
        inputs=[sql_output, question_input, model_dropdown, reasoning_state],
        outputs=[result_output, status_output, report_output, history_output, history_sqls_state],
        concurrency_limit=3,
    )

    # CSV 다운로드
    download_btn.click(
        fn=_export_csv,
        inputs=[result_output],
        outputs=[download_file],
    )

    # 이력 행 선택 시 SQL 표시
    history_output.select(
        fn=_on_history_select,
        inputs=[history_sqls_state],
        outputs=[history_sql_display],
    )

    # 이력 삭제
    clear_history_btn.click(
        fn=_clear_history,
        inputs=[],
        outputs=[history_output, history_sqls_state, history_sql_display],
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
    )
