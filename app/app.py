"""
HR Text2SQL Dashboard — Premium SaaS-style UI
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
from config import GRADIO_HOST, GRADIO_PORT, DEFAULT_MODEL_KEY, MODEL_REGISTRY, TARGET_TABLES
from model_registry import get_display_choices, get_available_models


# ===== Google Fonts =====
custom_head = '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">'


# ===== Hero Header HTML =====
def _build_hero_header():
    """Build the gradient hero header with live badge, clock, KPI badges, and title."""
    n_models = len([k for k, v in MODEL_REGISTRY.items() if v.get("enabled")])
    n_tables = len(TARGET_TABLES)
    return f"""
    <div style="
        position: relative;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 50%, #f093fb 100%);
        border-radius: 20px;
        padding: 40px 48px 36px 48px;
        box-shadow: 0 20px 60px rgba(102, 126, 234, 0.35);
        overflow: hidden;
        margin-bottom: 24px;
        animation: fadeInUp 0.6s ease-out;
    ">
        <!-- Decorative circles -->
        <div style="
            position: absolute; top: -40px; right: -40px;
            width: 200px; height: 200px;
            background: rgba(255,255,255,0.08);
            border-radius: 50%;
        "></div>
        <div style="
            position: absolute; bottom: -60px; left: 60px;
            width: 160px; height: 160px;
            background: rgba(255,255,255,0.06);
            border-radius: 50%;
        "></div>
        <div style="
            position: absolute; top: 30px; left: 40%;
            width: 80px; height: 80px;
            background: rgba(255,255,255,0.05);
            border-radius: 50%;
        "></div>
        <div style="
            position: absolute; bottom: 10px; right: 25%;
            width: 120px; height: 120px;
            background: rgba(255,255,255,0.04);
            border-radius: 50%;
        "></div>

        <!-- Top bar: live badge + clock on left, KPI badges on right -->
        <div style="
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 24px;
            position: relative;
            z-index: 1;
        ">
            <!-- Left: Live badge + Clock -->
            <div style="display: flex; align-items: center; gap: 16px;">
                <div style="
                    display: flex; align-items: center; gap: 8px;
                    background: rgba(255,255,255,0.15);
                    backdrop-filter: blur(10px);
                    -webkit-backdrop-filter: blur(10px);
                    border: 1px solid rgba(255,255,255,0.2);
                    border-radius: 50px;
                    padding: 6px 16px;
                    font-size: 13px;
                    color: white;
                    font-weight: 600;
                ">
                    <span style="
                        display: inline-block;
                        width: 8px; height: 8px;
                        background: #4ade80;
                        border-radius: 50%;
                        animation: pulse-dot 2s infinite;
                        box-shadow: 0 0 8px rgba(74, 222, 128, 0.6);
                    "></span>
                    Live
                </div>
                <span id="hero-clock" style="
                    color: rgba(255,255,255,0.85);
                    font-size: 13px;
                    font-weight: 500;
                    letter-spacing: 0.3px;
                "></span>
            </div>

            <!-- Right: KPI badges -->
            <div style="display: flex; gap: 12px;">
                <div style="
                    display: flex; flex-direction: column; align-items: center; justify-content: center;
                    width: 64px; height: 64px;
                    background: rgba(255,255,255,0.15);
                    backdrop-filter: blur(10px);
                    -webkit-backdrop-filter: blur(10px);
                    border: 1px solid rgba(255,255,255,0.2);
                    border-radius: 50%;
                ">
                    <span style="color: white; font-weight: 800; font-size: 18px; line-height: 1;">{n_models}</span>
                    <span style="color: rgba(255,255,255,0.7); font-size: 10px; font-weight: 500;">Models</span>
                </div>
                <div style="
                    display: flex; flex-direction: column; align-items: center; justify-content: center;
                    width: 64px; height: 64px;
                    background: rgba(255,255,255,0.15);
                    backdrop-filter: blur(10px);
                    -webkit-backdrop-filter: blur(10px);
                    border: 1px solid rgba(255,255,255,0.2);
                    border-radius: 50%;
                ">
                    <span style="color: white; font-weight: 800; font-size: 18px; line-height: 1;">{n_tables}</span>
                    <span style="color: rgba(255,255,255,0.7); font-size: 10px; font-weight: 500;">Tables</span>
                </div>
            </div>
        </div>

        <!-- Title -->
        <div style="position: relative; z-index: 1;">
            <h1 style="
                color: white;
                font-size: 2.8em;
                font-weight: 800;
                margin: 0 0 8px 0;
                letter-spacing: -0.5px;
                text-shadow: 0 2px 10px rgba(0,0,0,0.15);
                line-height: 1.1;
            ">HR Text2SQL</h1>
            <p style="
                color: rgba(255,255,255,0.8);
                font-size: 1.1em;
                margin: 0;
                font-weight: 500;
                letter-spacing: 0.2px;
            ">자연어로 Oracle HR 데이터베이스에 질의합니다</p>
        </div>
    </div>
    """


# ===== Stat Cards HTML =====
def _build_stat_cards(total_queries=0, success_rate=0, avg_rows=0):
    """Build the 3-column stat cards row."""
    cards = [
        {
            "label": "총 질의 수",
            "value": total_queries,
            "suffix": "",
            "color": "#3b82f6",
            "icon_bg": "rgba(59, 130, 246, 0.12)",
            "icon": "\U0001f50d",
            "delay": "0s",
        },
        {
            "label": "성공률",
            "value": success_rate,
            "suffix": "%",
            "color": "#10b981",
            "icon_bg": "rgba(16, 185, 129, 0.12)",
            "icon": "\u2705",
            "delay": "0.1s",
        },
        {
            "label": "평균 조회 건수",
            "value": avg_rows,
            "suffix": "",
            "color": "#8b5cf6",
            "icon_bg": "rgba(139, 92, 246, 0.12)",
            "icon": "\U0001f4ca",
            "delay": "0.2s",
        },
    ]

    cards_html = ""
    for card in cards:
        suffix_attr = f' data-suffix="{card["suffix"]}"' if card["suffix"] else ""
        display_val = f'{card["value"]}{card["suffix"]}'
        cards_html += f"""
        <div style="
            flex: 1;
            background: white;
            border-radius: 16px;
            padding: 24px 28px;
            box-shadow: 0 2px 12px rgba(0,0,0,0.06);
            border-bottom: 4px solid {card['color']};
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            cursor: default;
            animation: fadeInUp 0.5s ease-out {card['delay']} both;
        "
        onmouseover="this.style.transform='translateY(-4px)';this.style.boxShadow='0 12px 32px rgba(0,0,0,0.12)';"
        onmouseout="this.style.transform='translateY(0)';this.style.boxShadow='0 2px 12px rgba(0,0,0,0.06)';"
        >
            <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                <div>
                    <div style="color: #6b7280; font-size: 13px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px;">
                        {card['label']}
                    </div>
                    <div style="font-size: 2em; font-weight: 800; color: #1f2937; animation: countUp 0.6s ease-out;"
                         data-counter="{card['value']}"{suffix_attr}>
                        {display_val}
                    </div>
                </div>
                <div style="
                    width: 48px; height: 48px;
                    background: {card['icon_bg']};
                    border-radius: 12px;
                    display: flex; align-items: center; justify-content: center;
                    font-size: 22px;
                ">{card['icon']}</div>
            </div>
        </div>
        """

    return f"""
    <div style="
        display: flex;
        gap: 20px;
        margin-bottom: 24px;
    ">
        {cards_html}
    </div>
    """


# ===== CSS =====
custom_css = """
/* ===== SaaS Dashboard Theme ===== */

/* Global */
.gradio-container {
    max-width: 1280px !important;
    margin: auto !important;
    font-family: 'Inter', 'Pretendard', 'Apple SD Gothic Neo', sans-serif !important;
    background: #f0f2f5 !important;
    padding: 24px !important;
}

/* Live badge pulse */
@keyframes pulse-dot {
    0%, 100% { opacity: 1; transform: scale(1); }
    50% { opacity: 0.5; transform: scale(0.85); }
}

/* Fade in animation */
@keyframes fadeInUp {
    from { opacity: 0; transform: translateY(24px); }
    to { opacity: 1; transform: translateY(0); }
}

@keyframes slideInRight {
    from { opacity: 0; transform: translateX(30px); }
    to { opacity: 1; transform: translateX(0); }
}

@keyframes countUp {
    from { opacity: 0; transform: scale(0.5); }
    to { opacity: 1; transform: scale(1); }
}

/* Tab navigation - pill style */
.tabs > .tab-nav {
    background: white !important;
    border-radius: 14px !important;
    padding: 6px !important;
    box-shadow: 0 2px 12px rgba(0,0,0,0.06) !important;
    margin-bottom: 20px !important;
    border: none !important;
}
.tabs > .tab-nav > button {
    border-radius: 10px !important;
    font-weight: 600 !important;
    font-size: 14px !important;
    padding: 10px 24px !important;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
    border: none !important;
    color: #6b7280 !important;
}
.tabs > .tab-nav > button:hover {
    background: #f3f4f6 !important;
    color: #374151 !important;
}
.tabs > .tab-nav > button.selected {
    background: linear-gradient(135deg, #667eea, #764ba2) !important;
    color: white !important;
    box-shadow: 0 4px 15px rgba(102, 126, 234, 0.35) !important;
    border-bottom: none !important;
}

/* Model section card */
.model-section {
    background: white !important;
    border: none !important;
    border-radius: 16px !important;
    box-shadow: 0 2px 12px rgba(0,0,0,0.06) !important;
    padding: 20px 24px !important;
    margin-bottom: 20px !important;
    animation: fadeInUp 0.5s ease-out !important;
}

/* Primary button - gradient */
.primary-btn {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
    border: none !important;
    color: white !important;
    font-weight: 600 !important;
    border-radius: 12px !important;
    padding: 12px 28px !important;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
    box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3) !important;
    font-size: 14px !important;
}
.primary-btn:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 8px 25px rgba(102, 126, 234, 0.45) !important;
}
.primary-btn:active {
    transform: translateY(0) !important;
}

/* Execute button - different color */
.execute-btn {
    background: linear-gradient(135deg, #10b981 0%, #059669 100%) !important;
    border: none !important;
    color: white !important;
    font-weight: 600 !important;
    border-radius: 12px !important;
    padding: 12px 28px !important;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
    box-shadow: 0 4px 15px rgba(16, 185, 129, 0.3) !important;
    font-size: 14px !important;
}
.execute-btn:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 8px 25px rgba(16, 185, 129, 0.45) !important;
}

/* Input fields */
.gradio-container textarea, .gradio-container input[type="text"] {
    border-radius: 12px !important;
    border: 2px solid #e5e7eb !important;
    transition: all 0.3s ease !important;
    font-size: 14px !important;
}
.gradio-container textarea:focus, .gradio-container input[type="text"]:focus {
    border-color: #667eea !important;
    box-shadow: 0 0 0 4px rgba(102, 126, 234, 0.1) !important;
}

/* Dataframe table */
.result-table {
    border-radius: 16px !important;
    overflow: hidden !important;
    box-shadow: 0 2px 12px rgba(0,0,0,0.06) !important;
    border: none !important;
    animation: fadeInUp 0.5s ease-out !important;
}

/* Report accordion */
.report-accordion {
    border: none !important;
    border-radius: 16px !important;
    box-shadow: 0 2px 12px rgba(0,0,0,0.06) !important;
    margin-top: 16px !important;
    overflow: hidden !important;
}

/* SQL output area */
.sql-area textarea {
    font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace !important;
    background: #1e1e2e !important;
    color: #cdd6f4 !important;
    border: none !important;
    border-radius: 12px !important;
    padding: 16px !important;
    font-size: 13px !important;
    line-height: 1.6 !important;
}
.sql-area textarea:focus {
    box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.2) !important;
}

/* Status textbox */
.status-display input {
    font-weight: 600 !important;
    border-radius: 10px !important;
}

/* Schema tab */
.schema-tab {
    font-size: 1.05em !important;
    line-height: 1.8 !important;
    padding: 20px !important;
}
.schema-tab table { width: 100% !important; border-collapse: collapse !important; }
.schema-tab th {
    background: #f8fafc !important;
    font-weight: 600 !important;
    padding: 10px 14px !important;
    text-align: left !important;
}
.schema-tab td { padding: 8px 14px !important; border-bottom: 1px solid #f1f5f9 !important; }

/* History SQL display */
.history-sql-display {
    border-radius: 12px !important;
    overflow: hidden !important;
}

/* Download file */
.download-section {
    margin-top: 8px !important;
}
"""


# ===== JavaScript =====
custom_js = """
function() {
    // ---- Live Clock ----
    function updateClock() {
        var el = document.getElementById('hero-clock');
        if (!el) return;
        var now = new Date();
        var pad = function(n) { return String(n).padStart(2, '0'); };
        var dateStr = now.getFullYear() + '년 ' + (now.getMonth()+1) + '월 ' + now.getDate() + '일 ';
        var ampm = now.getHours() >= 12 ? '오후' : '오전';
        var h = now.getHours() > 12 ? now.getHours() - 12 : (now.getHours() === 0 ? 12 : now.getHours());
        el.textContent = dateStr + ampm + ' ' + pad(h) + ':' + pad(now.getMinutes()) + ':' + pad(now.getSeconds());
    }
    setInterval(updateClock, 1000);
    updateClock();

    // ---- Number Counter Animation ----
    function animateCounters() {
        document.querySelectorAll('[data-counter]').forEach(function(el) {
            if (el.dataset.animated) return;
            el.dataset.animated = 'true';
            var target = parseFloat(el.dataset.counter);
            var isPercent = el.dataset.suffix === '%';
            if (isNaN(target) || target === 0) {
                el.textContent = isPercent ? '0%' : '0';
                return;
            }
            var current = 0;
            var duration = 1000;
            var steps = 40;
            var increment = target / steps;
            var stepTime = duration / steps;
            var timer = setInterval(function() {
                current += increment;
                if (current >= target) {
                    current = target;
                    clearInterval(timer);
                }
                el.textContent = isPercent ? current.toFixed(0) + '%' : Math.round(current).toLocaleString();
            }, stepTime);
        });
    }

    // Run counter animation initially and on DOM changes
    setTimeout(animateCounters, 500);
    let counterTimeout = null;
    const counterObserver = new MutationObserver(() => {
        if (counterTimeout) clearTimeout(counterTimeout);
        counterTimeout = setTimeout(animateCounters, 300);
    });
    const statArea = document.querySelector('.gradio-container');
    if (statArea) {
        counterObserver.observe(statArea, { childList: true, subtree: true });
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


# ===== 통계 추적 =====
_stats_lock = threading.Lock()
_stats = {"total": 0, "success": 0, "total_rows": 0}


def _update_stats(status, row_count):
    """Update global query statistics."""
    with _stats_lock:
        _stats["total"] += 1
        if status == "성공":
            _stats["success"] += 1
        _stats["total_rows"] += row_count


def _get_stat_values():
    """Return (total_queries, success_rate, avg_rows) tuple."""
    with _stats_lock:
        total = _stats["total"]
        success = _stats["success"]
        rate = round(success / total * 100) if total > 0 else 0
        avg = round(_stats["total_rows"] / total) if total > 0 else 0
        return total, rate, avg


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
    """생성된 SQL을 실행하고 결과 반환 (stat cards도 갱신)"""
    if not sql_text or not sql_text.strip():
        total, rate, avg = _get_stat_values()
        return (
            pd.DataFrame(),
            "실행할 SQL이 없습니다.",
            "",
            _get_history(),
            _get_history_sqls(),
            _build_stat_cards(total, rate, avg),
        )
    if model_key not in MODEL_REGISTRY:
        model_key = DEFAULT_MODEL_KEY

    progress(0.3, desc="SQL 실행 중...")
    result = execute_sql(sql_text.strip())

    if result["error"]:
        _add_to_history(question or "(직접 실행)", model_key, "오류", 0, sql_text)
        _update_stats("오류", 0)
        total, rate, avg = _get_stat_values()
        return (
            pd.DataFrame(),
            f"오류: {result['error']}",
            "",
            _get_history(),
            _get_history_sqls(),
            _build_stat_cards(total, rate, avg),
        )

    df = result["result"]

    progress(0.7, desc="보고서 생성 중...")
    report = generate_report(question or "", sql_text, df, reasoning, model_key=model_key)

    progress(1.0, desc="완료")
    _add_to_history(question or "(직접 실행)", model_key, "성공", len(df), sql_text)
    _update_stats("성공", len(df))

    total, rate, avg = _get_stat_values()
    return (
        df,
        f"조회 완료: {len(df)}건",
        report,
        _get_history(),
        _get_history_sqls(),
        _build_stat_cards(total, rate, avg),
    )


# ===== Gradio UI 구성 =====
with gr.Blocks(
    title="HR Text2SQL Dashboard",
    css=custom_css,
    js=custom_js,
    head=custom_head,
    theme=gr.themes.Soft(),
) as demo:

    # Hero Header
    hero_header = gr.HTML(value=_build_hero_header())

    # Stat Cards
    stat_cards = gr.HTML(value=_build_stat_cards(0, 0, 0))

    # Model Selection
    with gr.Row(elem_classes=["model-section"]):
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
            with gr.Row():
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

            status_output = gr.Textbox(
                label="상태",
                interactive=False,
                elem_classes=["status-display"],
            )

            sql_output = gr.Textbox(
                label="생성된 SQL",
                lines=8,
                max_lines=20,
                interactive=True,
                info="SQL을 직접 수정한 후 'SQL 실행' 버튼을 클릭하세요",
                elem_classes=["sql-area"],
            )

            with gr.Row():
                execute_btn = gr.Button(
                    "SQL 실행",
                    variant="primary",
                    min_width=120,
                    elem_classes=["execute-btn"],
                )
                download_btn = gr.Button("CSV 다운로드", size="sm", variant="secondary")

            download_file = gr.File(label="다운로드", visible=False, elem_classes=["download-section"])

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
            history_sql_display = gr.Code(
                label="선택된 SQL",
                language="sql",
                elem_classes=["history-sql-display"],
            )
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

    # SQL 실행 (버튼 클릭) — now also updates stat_cards
    execute_btn.click(
        fn=process_execute,
        inputs=[sql_output, question_input, model_dropdown, reasoning_state],
        outputs=[result_output, status_output, report_output, history_output, history_sqls_state, stat_cards],
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
