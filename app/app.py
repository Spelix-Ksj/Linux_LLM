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
    """Build a compact single-line gradient hero header."""
    n_models = len([k for k, v in MODEL_REGISTRY.items() if v.get("enabled")])
    n_tables = len(TARGET_TABLES)
    now = datetime.datetime.now()
    return f"""
    <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 50%, #f093fb 100%);
                border-radius: 14px; padding: 14px 28px 12px 28px; margin-bottom: 16px;
                box-shadow: 0 8px 30px rgba(102, 126, 234, 0.25);
                animation: fadeInUp 0.6s ease-out;">
        <div style="display: flex; align-items: center; justify-content: space-between;">
            <div style="display:flex;align-items:center;gap:16px;">
                <span style="color:white;font-size:1.4em;font-weight:800;letter-spacing:-0.02em;">HR Text2SQL</span>
                <span style="background:rgba(255,255,255,0.2);backdrop-filter:blur(10px);
                             padding:4px 12px;border-radius:12px;color:white;font-size:12px;
                             font-weight:600;display:flex;align-items:center;gap:6px;">
                    <span style="width:7px;height:7px;background:#4ade80;border-radius:50%;
                                 display:inline-block;animation:pulse-dot 2s infinite;"></span>
                    Live
                </span>
                <span id="hero-clock" style="color:rgba(255,255,255,0.8);font-size:13px;font-weight:500;">
                    {now.strftime("%Y년 %m월 %d일")}
                </span>
            </div>
            <div style="display:flex;gap:20px;align-items:center;">
                <div style="display:flex;align-items:center;gap:6px;">
                    <span style="background:rgba(255,255,255,0.2);width:28px;height:28px;border-radius:50%;
                                 display:flex;align-items:center;justify-content:center;color:white;
                                 font-size:13px;font-weight:700;">{n_models}</span>
                    <span style="color:rgba(255,255,255,0.7);font-size:12px;">Models</span>
                </div>
                <div style="display:flex;align-items:center;gap:6px;">
                    <span style="background:rgba(255,255,255,0.2);width:28px;height:28px;border-radius:50%;
                                 display:flex;align-items:center;justify-content:center;color:white;
                                 font-size:13px;font-weight:700;">{n_tables}</span>
                    <span style="color:rgba(255,255,255,0.7);font-size:12px;">Tables</span>
                </div>
            </div>
        </div>
        <div style="margin-top:6px;">
            <span style="color:rgba(255,255,255,0.7);font-size:13px;font-weight:400;">자연어 질문을 Oracle SQL로 변환하여 인사정보 데이터베이스를 조회하는 AI 시스템</span>
        </div>
    </div>
    """


# ===== Stat Cards HTML =====
def _build_stat_cards(total_queries=0, success_rate=0, avg_rows=0):
    """Build compact single-line stat cards row."""
    cards = [
        {"label": "총 질의 수", "value": total_queries, "suffix": "", "color": "#3b82f6"},
        {"label": "성공률", "value": success_rate, "suffix": "%", "color": "#10b981"},
        {"label": "평균 조회 건수", "value": avg_rows, "suffix": "", "color": "#8b5cf6"},
    ]

    cards_html = ""
    for card in cards:
        suffix_attr = f' data-suffix="{card["suffix"]}"' if card["suffix"] else ""
        display_val = f'{card["value"]}{card["suffix"]}'
        cards_html += f"""
        <div style="flex:1;background:white;border-radius:10px;padding:12px 18px;
                    box-shadow:0 2px 8px rgba(0,0,0,0.04);border-left:3px solid {card['color']};
                    display:flex;align-items:center;justify-content:space-between;">
            <span style="color:#6b7280;font-size:13px;">{card['label']}</span>
            <span data-counter="{card['value']}"{suffix_attr}
                  style="font-size:1.2em;font-weight:700;color:#111827;">{display_val}</span>
        </div>
        """

    return f"""
    <div style="display:flex;gap:16px;margin-bottom:16px;animation:fadeInUp 0.4s ease-out;">
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

/* === Universal Round Effects === */
/* All Gradio block containers */
.gradio-container .block {
    border-radius: 16px !important;
}
/* Dropdown */
.gradio-container .wrap {
    border-radius: 12px !important;
}
.gradio-container select,
.gradio-container .secondary-wrap {
    border-radius: 12px !important;
}

/* All panels and groups */
.gradio-container .panel {
    border-radius: 16px !important;
}
.gradio-container .form {
    border-radius: 16px !important;
}

/* Tab content panel */
.gradio-container .tabitem {
    border-radius: 16px !important;
    background: white !important;
    padding: 24px !important;
    box-shadow: 0 2px 12px rgba(0,0,0,0.04) !important;
    margin-top: -8px !important;
}

/* Input containers */
.gradio-container .input-container {
    border-radius: 12px !important;
}

/* File upload/download areas */
.gradio-container .file-preview {
    border-radius: 12px !important;
}

/* Accordion */
.gradio-container .accordion {
    border-radius: 16px !important;
    overflow: hidden !important;
}

/* Code blocks */
.gradio-container .code-wrap {
    border-radius: 12px !important;
    overflow: hidden !important;
}

/* Examples grid */
.gradio-container .examples-holder {
    border-radius: 12px !important;
}
.gradio-container .examples-holder .gallery-item {
    border-radius: 10px !important;
}

/* Markdown containers */
.gradio-container .markdown-text {
    border-radius: 12px !important;
}

/* === Unified Button Heights === */
.gradio-container button {
    min-height: 42px !important;
    height: 42px !important;
    border-radius: 12px !important;
    font-weight: 600 !important;
    font-size: 14px !important;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
}

/* Exception: tab nav buttons should keep their own height */
.tabs > .tab-nav > button {
    height: auto !important;
    min-height: auto !important;
}

/* Exception: example buttons should be smaller */
.gradio-container .examples-holder button {
    height: 36px !important;
    min-height: 36px !important;
    border-radius: 8px !important;
    font-size: 13px !important;
}

/* === 2025 Design Trends === */
/* Soft elevation for all interactive elements */
.gradio-container .block:hover {
    box-shadow: 0 4px 20px rgba(0,0,0,0.08) !important;
    transition: box-shadow 0.3s ease !important;
}

/* Frosted glass effect on dropdowns */
.gradio-container .dropdown-container {
    background: rgba(255,255,255,0.8) !important;
    backdrop-filter: blur(8px) !important;
    border-radius: 12px !important;
}

/* Subtle gradient backgrounds on section containers */
.gradio-container .gr-group {
    background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%) !important;
    border-radius: 16px !important;
    border: 1px solid rgba(0,0,0,0.04) !important;
}

/* Modern scrollbar */
.gradio-container ::-webkit-scrollbar {
    width: 6px;
    height: 6px;
}
.gradio-container ::-webkit-scrollbar-track {
    background: transparent;
}
.gradio-container ::-webkit-scrollbar-thumb {
    background: #d1d5db;
    border-radius: 3px;
}
.gradio-container ::-webkit-scrollbar-thumb:hover {
    background: #9ca3af;
}

/* Hover effect for example buttons */
.gradio-container .examples-holder button:hover {
    background: linear-gradient(135deg, #667eea15, #764ba215) !important;
    border-color: #667eea !important;
    color: #667eea !important;
    transform: translateY(-1px) !important;
}

/* Secondary button style */
.gradio-container button.secondary {
    background: white !important;
    border: 1.5px solid #e5e7eb !important;
    color: #374151 !important;
    border-radius: 12px !important;
}
.gradio-container button.secondary:hover {
    border-color: #667eea !important;
    color: #667eea !important;
    background: #f8fafc !important;
}

/* Stop button (이력 삭제) */
.gradio-container button.stop {
    background: white !important;
    border: 1.5px solid #fca5a5 !important;
    color: #dc2626 !important;
    border-radius: 12px !important;
}
.gradio-container button.stop:hover {
    background: #fef2f2 !important;
    border-color: #dc2626 !important;
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

    // ---- Column Resize ----
    document.addEventListener('mousedown', function(e) {
        if (!e.target.classList.contains('col-resize-handle')) return;
        var th = e.target.parentElement;
        var startX = e.pageX;
        var startWidth = th.offsetWidth;
        var table = th.closest('table');
        if (table) table.style.tableLayout = 'fixed';

        function onMouseMove(ev) {
            var newWidth = startWidth + (ev.pageX - startX);
            if (newWidth > 40) {
                th.style.width = newWidth + 'px';
            }
        }
        function onMouseUp() {
            document.removeEventListener('mousemove', onMouseMove);
            document.removeEventListener('mouseup', onMouseUp);
        }
        document.addEventListener('mousemove', onMouseMove);
        document.addEventListener('mouseup', onMouseUp);
        e.preventDefault();
    });

    document.addEventListener('mouseover', function(e) {
        if (e.target.classList.contains('col-resize-handle')) {
            e.target.style.background = '#667eea';
            e.target.style.opacity = '0.5';
        }
    });
    document.addEventListener('mouseout', function(e) {
        if (e.target.classList.contains('col-resize-handle')) {
            e.target.style.background = 'transparent';
            e.target.style.opacity = '1';
        }
    });
}
"""


# ===== 스키마 정보 마크다운 =====
schema_info_markdown = """
## 데이터베이스 스키마 정보

### 테이블 요약
| 테이블 | 건수 | 설명 |
|--------|------|------|
| MOVE_ITEM_MASTER | 31,025 | 직원 마스터 (인사정보) |
| MOVE_CASE_ITEM | 148,029 | 배치안 상세 (케이스별 직원 배정) |
| MOVE_CASE_CNST_MASTER | 1,082,117 | 제약조건 (조직별 규칙) |
| MOVE_ORG_MASTER | 14,713 | 조직 마스터 (부서 정보) |

---

### 1. MOVE_ITEM_MASTER (직원 마스터)
| 컬럼명 | 한글명 | 설명 |
|--------|--------|------|
| ftr_move_std_id | 배치기준ID | 배치 기준 기간 (YYYYMM) |
| emp_id | 사원ID | 직원 고유번호 (PK) |
| emp_no | 사원번호 | 사번 |
| emp_nm | 이름 | 직원 성명 |
| lvl1_nm ~ lvl5_nm | 조직계층 | 1~5단계 조직 계층명 |
| org_nm | 현재조직 | 소속 부서명 |
| prev_org_nm | 이전조직 | 직전 소속 부서명 |
| job_type1/2/3 | 직종 | 직종 분류 |
| pos_grd_nm | 직급 | 직급명 (대리, 과장 등) |
| pos_grd_year | 직급년차 | 현 직급 근속 년수 |
| gender_nm | 성별 | 남자/여자 |
| year_desc | 연령대 | 연령대 구분 |
| birth_ymd | 생년월일 | 생년월일(숫자) |
| org_work_mon | 조직근무개월 | 현 조직 근무 개월수 |
| c_area_work_mon | 권역근무개월 | 현 권역 근무 개월수 |
| region_type | 지역구분 | 근무 지역 |
| self_move_yn | 자기신청이동 | 자기 신청 이동 여부 (1/0) |
| tot_score | 종합점수 | 배치 평가 점수 |
| married | 기혼여부 | 기혼 여부 (1/0) |
| have_children | 자녀유무 | 자녀 유무 (1/0) |
| labor_pos | 노조직책 | 노조 직책 |
| addr | 주소 | 직원 주소 |

### 2. MOVE_CASE_ITEM (배치안 상세)
| 컬럼명 | 한글명 | 설명 |
|--------|--------|------|
| ftr_move_std_id | 배치기준ID | 배치 기준 기간 (PK) |
| case_id | 케이스ID | 배치안 번호 (PK) |
| case_det_id | 상세ID | 배치안 상세 ID (PK) |
| rev_id | 리비전ID | 수정 버전 (PK) |
| emp_id | 사원ID | 직원 고유번호 (PK) |
| new_org_id | 새조직ID | 이동 대상 조직 ID |
| new_lvl1_nm ~ new_lvl5_nm | 새조직계층 | 이동 후 조직 계층 |
| new_job_type1/2 | 새직종 | 이동 후 직종 |
| must_stay_yn | 잔류필수 | 잔류 필수 여부 (1/0) |
| must_move_yn | 이동필수 | 이동 필수 여부 (1/0) |
| must_stay_reason | 잔류사유 | 잔류 필수 사유 |
| must_move_reason | 이동사유 | 이동 필수 사유 |
| fixed_yn | 확정여부 | 배치 확정 여부 (Y/N) |
| cand_yn | 후보여부 | 이동 후보 여부 |

### 3. MOVE_CASE_CNST_MASTER (제약조건)
| 컬럼명 | 한글명 | 설명 |
|--------|--------|------|
| ftr_move_std_id | 배치기준ID | 배치 기준 기간 (PK) |
| case_id | 케이스ID | 배치안 번호 (PK) |
| org_id | 조직ID | 대상 조직 ID (PK) |
| org_nm | 조직명 | 대상 조직명 |
| cnst_cd | 제약코드 | 제약 조건 코드 (PK) |
| cnst_nm | 제약조건명 | 제약 조건 이름 |
| cnst_gbn | 제약구분 | 제약 조건 구분 (분류) |
| apply_target | 적용대상 | 제약 조건 적용 대상 |
| cnst_val | 제약값 | 제약 조건 수치 |
| penalty_val | 패널티 | 위반 시 패널티 점수 |
| use_yn | 사용여부 | 사용 여부 (Y/N) |
| cnst_des | 설명 | 제약 조건 상세 설명 |

### 4. MOVE_ORG_MASTER (조직 마스터)
| 컬럼명 | 한글명 | 설명 |
|--------|--------|------|
| ftr_move_std_id | 배치기준ID | 배치 기준 기간 (PK) |
| org_id | 조직ID | 조직 고유번호 (PK) |
| parent_org_id | 상위조직ID | 상위 조직 ID |
| org_cd | 조직코드 | 조직 코드 |
| org_nm | 조직명 | 조직/부서명 |
| org_type | 조직유형 | 조직 유형 분류 |
| lvl1_nm ~ lvl5_nm | 조직계층 | 1~5단계 조직 계층명 |
| full_path | 전체경로 | 조직 전체 경로 |
| lvl | 레벨 | 조직 계층 레벨(단계) |
| job_type1/2 | 직종 | 조직 직종 분류 |
| tot_to | 정원 | 배정 정원 |
| region_type | 지역구분 | 조직 소재 지역 |
| addr | 주소 | 조직 주소 |

---

### 테이블 관계 (JOIN 조건)
```
┌──────────────────┐     FTR_MOVE_STD_ID + EMP_ID     ┌──────────────────┐
│ MOVE_ITEM_MASTER │◄────────────────────────────────►│  MOVE_CASE_ITEM  │
│   (직원 마스터)    │                                   │  (배치안 상세)     │
└──────────────────┘                                   └──────────────────┘
                                                              │
                           FTR_MOVE_STD_ID + CASE_ID          │ NEW_ORG_ID = ORG_ID
                           + CASE_DET_ID + REV_ID             │
                                                              ▼
┌──────────────────────┐   FTR_MOVE_STD_ID + ORG_ID   ┌──────────────────┐
│MOVE_CASE_CNST_MASTER │◄────────────────────────────►│ MOVE_ORG_MASTER  │
│   (제약조건)          │                               │  (조직 마스터)    │
└──────────────────────┘                               └──────────────────┘
```

### JOIN SQL 예시
| 조인 | SQL |
|------|-----|
| 직원 ↔ 배치안 | `m JOIN c ON m.ftr_move_std_id = c.ftr_move_std_id AND m.emp_id = c.emp_id` |
| 배치안 ↔ 제약조건 | `c JOIN cn ON c.ftr_move_std_id = cn.ftr_move_std_id AND c.case_id = cn.case_id AND c.case_det_id = cn.case_det_id AND c.rev_id = cn.rev_id` |
| 제약조건 ↔ 조직 | `cn JOIN o ON cn.ftr_move_std_id = o.ftr_move_std_id AND cn.org_id = o.org_id` |
| 배치안 → 새조직 | `c JOIN o ON c.ftr_move_std_id = o.ftr_move_std_id AND c.new_org_id = o.org_id` |
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


# ===== DataFrame → HTML 테이블 변환 =====
def _df_to_html(df):
    """DataFrame을 스타일된 HTML 테이블로 변환 (동적 높이)"""
    if not isinstance(df, pd.DataFrame) or df.empty:
        return '<div style="padding:20px;text-align:center;color:#9ca3af;">조회 결과가 없습니다.</div>'

    max_display = 500  # Show scrollbar if more than this
    total = len(df)

    # Build HTML table
    html = '<div style="border-radius:12px;overflow:hidden;border:1px solid #e5e7eb;">'

    # If many rows, add scrollable container
    if total > 30:
        html += '<div style="max-height:500px;overflow:auto;">'

    html += '<table style="width:100%;border-collapse:collapse;font-size:13px;">'

    # Header
    html += '<thead style="position:sticky;top:0;z-index:1;"><tr>'
    for col in df.columns:
        html += f'<th style="background:#f8fafc;padding:10px 14px;text-align:left;font-weight:600;color:#374151;border-bottom:2px solid #e5e7eb;white-space:nowrap;position:relative;min-width:60px;">{col}<div class="col-resize-handle" style="position:absolute;right:0;top:0;bottom:0;width:5px;cursor:col-resize;background:transparent;z-index:2;"></div></th>'
    html += '</tr></thead>'

    # Body (limit to max_display rows)
    html += '<tbody>'
    display_df = df.head(max_display)
    for i, (_, row) in enumerate(display_df.iterrows()):
        bg = '#ffffff' if i % 2 == 0 else '#f9fafb'
        html += f'<tr style="background:{bg};">'
        for val in row:
            cell_val = '' if pd.isna(val) else str(val)
            html += f'<td style="padding:8px 14px;border-bottom:1px solid #f1f5f9;color:#111827;white-space:nowrap;">{cell_val}</td>'
        html += '</tr>'
    html += '</tbody></table>'

    if total > 30:
        html += '</div>'

    # Footer with count
    if total > max_display:
        html += f'<div style="padding:8px 14px;background:#f8fafc;color:#6b7280;font-size:12px;border-top:1px solid #e5e7eb;">전체 {total}건 중 {max_display}건 표시</div>'

    html += '</div>'
    return html


# ===== 모델 상태 텍스트 빌더 =====
def _build_model_status(model_key):
    """선택된 모델의 상태 정보를 평문 텍스트로 반환"""
    models = get_available_models()
    for m in models:
        if m["key"] == model_key:
            status = "정상" if m["healthy"] else "응답 없음"
            return f"{m['display_name']} | 상태: {status} | GPU: {m['gpu_info']}"
    return f"{model_key} (정보 없음)"


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
            _df_to_html(pd.DataFrame()),
            "실행할 SQL이 없습니다.",
            "",
            _get_history(),
            _get_history_sqls(),
            _build_stat_cards(total, rate, avg),
            pd.DataFrame(),
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
            _df_to_html(pd.DataFrame()),
            f"오류: {result['error']}",
            "",
            _get_history(),
            _get_history_sqls(),
            _build_stat_cards(total, rate, avg),
            pd.DataFrame(),
        )

    df = result["result"]

    progress(0.7, desc="보고서 생성 중...")
    report = generate_report(question or "", sql_text, df, reasoning, model_key=model_key)

    progress(1.0, desc="완료")
    _add_to_history(question or "(직접 실행)", model_key, "성공", len(df), sql_text)
    _update_stats("성공", len(df))

    total, rate, avg = _get_stat_values()
    return (
        _df_to_html(df),
        f"조회 완료: {len(df)}건",
        report,
        _get_history(),
        _get_history_sqls(),
        _build_stat_cards(total, rate, avg),
        df,
    )


# ===== Gradio UI 구성 =====
with gr.Blocks(title="HR Text2SQL Dashboard") as demo:

    # Compact Hero Header (single line)
    hero_header = gr.HTML(value=_build_hero_header())

    # Compact Stat Cards (single line)
    stat_cards = gr.HTML(value=_build_stat_cards(0, 0, 0))

    # Hidden state for reasoning (passed between generate and execute)
    reasoning_state = gr.State("")

    # Hidden state for raw DataFrame (used by CSV export)
    result_df_state = gr.State(pd.DataFrame())

    with gr.Tabs():
        # ===== 탭 1: SQL 질의 =====
        with gr.Tab("SQL 질의"):
            # Create question_input with render=False so we can reference it in Examples
            # before rendering it in the Row below
            question_input = gr.Textbox(
                show_label=False,
                placeholder="💬 질문을 입력하세요 (예: 직급별 인원 수를 구해줘)",
                lines=1,
                scale=4,
                min_width=300,
                container=False,
                render=False,
            )

            # 예시 질문 (at top of tab)
            gr.Examples(
                examples=[
                    ["전체 직원 수는 몇 명이야?"],
                    ["남자, 여자 인원 수를 알려줘"],
                    ["직급별 인원 수를 보여줘"],
                    ["부서별 평균 근무개월을 알려줘"],
                    ["30대 직원 목록을 보여줘"],
                    ["3년 이상 근무한 직원은 누구야?"],
                    ["지역별 직급 분포를 보여줘"],
                    ["최근 이동 대상자의 이름과 새 부서를 알려줘"],
                    ["최근 배치기준으로 부서별 정원과 현재 인원을 비교해줘"],
                    ["부서 이동이 확정된 직원 목록을 보여줘"],
                ],
                inputs=question_input,
            )

            # Row 1: Model selection (true single line — no labels)
            with gr.Row(equal_height=True):
                model_dropdown = gr.Dropdown(
                    show_label=False,
                    choices=get_display_choices(),
                    value=DEFAULT_MODEL_KEY,
                    scale=2,
                    container=False,
                )
                model_status = gr.Textbox(
                    show_label=False,
                    value=_build_model_status(DEFAULT_MODEL_KEY),
                    interactive=False,
                    scale=3,
                    container=False,
                )
                refresh_btn = gr.Button("🔄", size="sm", scale=0, min_width=50)

            # Row 2: Question input (true single line — no labels)
            with gr.Row(equal_height=True):
                question_input.render()
                generate_btn = gr.Button(
                    "SQL 생성",
                    variant="primary",
                    scale=1,
                    min_width=120,
                    elem_classes=["primary-btn"],
                )

            # Generated SQL
            sql_output = gr.Textbox(
                label="생성된 SQL",
                lines=8,
                max_lines=20,
                interactive=True,
                info="SQL을 직접 수정한 후 'SQL 실행' 버튼을 클릭하세요",
                elem_classes=["sql-area"],
            )

            # Execute + CSV row
            with gr.Row():
                execute_btn = gr.Button(
                    "SQL 실행",
                    variant="primary",
                    min_width=120,
                    elem_classes=["execute-btn"],
                )
                download_btn = gr.Button("CSV 다운로드", size="sm", variant="secondary")

            # Status (moved below execute row)
            status_output = gr.Textbox(
                label="상태",
                interactive=False,
                elem_classes=["status-display"],
            )

            download_file = gr.File(label="다운로드", visible=False, elem_classes=["download-section"])

            # Results
            gr.Markdown("**조회 결과**")
            result_output = gr.HTML(value="")

            with gr.Accordion("결과 보고서", open=True, elem_classes=["report-accordion"]):
                report_output = gr.Markdown(value="")

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

    # Footer
    gr.HTML("""
    <div style="text-align:center;padding:20px 0 8px 0;color:#9ca3af;font-size:12px;border-top:1px solid #e5e7eb;margin-top:24px;">
        <div>HR Text2SQL v2.0 — Oracle HR 인사정보 자연어 질의 시스템</div>
        <div style="margin-top:4px;">Powered by vLLM + LangChain + Gradio | GPU: NVIDIA H100 x5</div>
    </div>
    """)

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
        outputs=[result_output, status_output, report_output, history_output, history_sqls_state, stat_cards, result_df_state],
        concurrency_limit=3,
    )

    # CSV 다운로드
    download_btn.click(
        fn=_export_csv,
        inputs=[result_df_state],
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
        theme=gr.themes.Soft(),
        css=custom_css,
        js=custom_js,
        head=custom_head,
    )
