"""
Step 6: Gradio 웹 UI
자연어로 Oracle HR DB에 질의하는 웹 인터페이스
실행: python app.py
"""
import os
import gradio as gr
import pandas as pd

from text2sql_pipeline import ask_hr, generate_report
from config import GRADIO_HOST, GRADIO_PORT, DEFAULT_MODEL_KEY, MODEL_REGISTRY
from model_registry import get_display_choices, get_available_models


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
    """모델 목록 새로고침 — Dropdown choices 및 상태 마크다운 갱신"""
    choices = get_display_choices()
    # 현재 선택값이 새 목록에 있으면 유지, 없으면 기본값
    current_keys = [c[1] for c in choices]
    default = DEFAULT_MODEL_KEY if DEFAULT_MODEL_KEY in current_keys else (current_keys[0] if current_keys else DEFAULT_MODEL_KEY)
    status_md = _build_model_status(default)
    return gr.update(choices=choices, value=default), status_md


def _on_model_change(model_key):
    """모델 드롭다운 변경 시 상태 마크다운 업데이트"""
    return _build_model_status(model_key)


def process_question(question: str, model_key: str):
    """자연어 질문을 처리하여 SQL과 결과를 반환"""
    if not question or not question.strip():
        return "", pd.DataFrame(), "", ""

    # model_key 유효성 검증 (클라이언트 측 조작 방지)
    if model_key not in MODEL_REGISTRY:
        model_key = DEFAULT_MODEL_KEY

    result = ask_hr(question.strip(), model_key=model_key)
    sql = result["sql"]
    df = result["result"]
    error = result.get("error")
    reasoning = result.get("reasoning", "")

    if error:
        status = f"오류 발생: {error}"
        return sql, df, status, ""
    else:
        status = f"조회 완료: {len(df)}건"

    report = generate_report(question.strip(), sql, df, reasoning, model_key=model_key)

    return sql, df, status, report


# ===== Gradio UI 구성 =====
with gr.Blocks(title="HR Text2SQL 시스템", theme=gr.themes.Soft()) as demo:
    gr.Markdown("# 인사정보 Text2SQL 시스템")
    gr.Markdown("자연어로 질문하면 Oracle HR DB에서 결과를 조회합니다.")

    # 모델 선택 영역
    with gr.Row():
        model_dropdown = gr.Dropdown(
            label="모델 선택",
            choices=get_display_choices(),
            value=DEFAULT_MODEL_KEY,
            scale=4,
        )
        refresh_btn = gr.Button("새로고침", size="sm", scale=1)

    model_status = gr.Markdown(value=_build_model_status(DEFAULT_MODEL_KEY))

    # 질문 입력 영역
    with gr.Row():
        question_input = gr.Textbox(
            label="질문 입력",
            placeholder="예: 직급별 인원 수를 구해줘",
            lines=2,
            scale=4,
        )
        submit_btn = gr.Button("SQL 생성 및 실행", variant="primary", scale=1)

    status_output = gr.Textbox(label="상태", interactive=False)

    with gr.Row():
        sql_output = gr.Code(label="생성된 SQL", language="sql")

    with gr.Row():
        result_output = gr.Dataframe(label="조회 결과", wrap=True)

    with gr.Accordion("결과 보고서", open=True):
        report_output = gr.Markdown(value="")

    # 예시 질문
    gr.Examples(
        examples=[
            ["직급별 인원 수를 구해줘"],
            ["평균 나이가 가장 높은 부서는 어디야?"],
            ["IT 부서에서 대리급 이상의 직원들만 보여줘"],
            ["최근 입사한 직원 10명을 보여줘"],
            ["부서별 평균 근속연수를 구해줘"],
        ],
        inputs=question_input,
    )

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

    # SQL 생성 및 실행
    submit_btn.click(
        fn=process_question,
        inputs=[question_input, model_dropdown],
        outputs=[sql_output, result_output, status_output, report_output],
        concurrency_limit=3,
    )
    question_input.submit(
        fn=process_question,
        inputs=[question_input, model_dropdown],
        outputs=[sql_output, result_output, status_output, report_output],
        concurrency_limit=3,
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
