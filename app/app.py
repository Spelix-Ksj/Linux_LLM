"""
HR Text2SQL Dashboard — Premium SaaS-style UI
자연어로 Oracle HR DB에 질의하는 웹 인터페이스
실행: python app.py
"""
import os
import datetime
import re
import tempfile
import threading
import concurrent.futures
import html as _html_mod

import gradio as gr
import pandas as pd

from text2sql_pipeline import generate_sql, execute_sql, generate_report, get_report_llm
from config import GRADIO_HOST, GRADIO_PORT, DEFAULT_MODEL_KEY, MODEL_REGISTRY, TARGET_TABLES
from model_registry import get_display_choices, get_available_models
from langchain_core.messages import HumanMessage, SystemMessage


def _get_move_std_choices():
    """DB에서 이동번호 목록을 조회하여 Dropdown choices 반환"""
    try:
        import oracledb
        from config import DB_CONFIG
        with oracledb.connect(
            user=DB_CONFIG["user"],
            password=DB_CONFIG["password"],
            dsn=oracledb.makedsn(DB_CONFIG["host"], DB_CONFIG["port"], sid=DB_CONFIG["sid"])
        ) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT FTR_MOVE_STD_ID, STD_NM
                    FROM HRAI_CON.FTR_MOVE_STD
                    ORDER BY FTR_MOVE_STD_ID DESC
                """)
                choices = []
                for row in cur.fetchall():
                    ftr_id = int(row[0]) if row[0] is not None else 0
                    std_nm = row[1] or str(ftr_id)
                    label = f"{ftr_id} - {std_nm}"
                    choices.append((label, str(ftr_id)))
        if not choices:
            choices = [("(이동번호 없음)", "0")]
        return choices
    except Exception as e:
        print(f"이동번호 조회 실패: {e}")
        return [("(DB 연결 실패)", "0")]


def _get_move_std_stats(move_std_id):
    """이동번호 선택 시 해당 이동의 핵심 통계를 조회하여 HTML로 반환"""
    if not move_std_id or move_std_id == "0":
        return ""
    try:
        import oracledb
        from config import DB_CONFIG
        mid = int(move_std_id)
        with oracledb.connect(
            user=DB_CONFIG["user"],
            password=DB_CONFIG["password"],
            dsn=oracledb.makedsn(DB_CONFIG["host"], DB_CONFIG["port"], sid=DB_CONFIG["sid"])
        ) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        (SELECT COUNT(*) FROM HRAI_CON.move_item_master WHERE ftr_move_std_id = :mid) AS emp_cnt,
                        (SELECT COUNT(*) FROM HRAI_CON.move_org_master WHERE ftr_move_std_id = :mid) AS org_cnt,
                        (SELECT COUNT(*) FROM HRAI_CON.move_case_master WHERE ftr_move_std_id = :mid) AS case_cnt,
                        (SELECT COUNT(*) FROM HRAI_CON.move_item_master WHERE ftr_move_std_id = :mid AND must_move_yn = '1') AS must_move,
                        (SELECT COUNT(*) FROM HRAI_CON.move_item_master WHERE ftr_move_std_id = :mid AND must_stay_yn = '1') AS must_stay
                    FROM dual
                """, {"mid": mid})
                row = cur.fetchone()
                if row:
                    emp, org, case_cnt, must_move, must_stay = row
                    return (
                        f'<div style="display:flex;gap:16px;padding:6px 12px;background:#f0f4ff;'
                        f'border-radius:8px;font-size:13px;color:#374151;align-items:center;flex-wrap:wrap;">'
                        f'<span>👥 직원 <b>{emp:,}</b>명</span>'
                        f'<span>🏢 사업소 <b>{org:,}</b>개</span>'
                        f'<span>📋 케이스 <b>{case_cnt:,}</b>개</span>'
                        f'<span>➡️ 필수이동 <b>{must_move:,}</b>명</span>'
                        f'<span>⛔ 필수유보 <b>{must_stay:,}</b>명</span>'
                        f'</div>'
                    )
        return ""
    except Exception as e:
        print(f"이동번호 통계 조회 실패: {e}")
        return '<div style="padding:6px 12px;color:#ef4444;font-size:12px;">통계 조회 실패</div>'



# ===== 제약조건 분석 함수 =====

def _cnst_summary_html(move_std_id):
    """제약조건 요약 테이블"""
    if not move_std_id or move_std_id == "0":
        return '<div style="padding:20px;text-align:center;color:#9ca3af;">이동번호를 선택하세요.</div>'
    try:
        import oracledb
        from config import DB_CONFIG
        mid = int(move_std_id)
        with oracledb.connect(user=DB_CONFIG["user"], password=DB_CONFIG["password"],
                              dsn=oracledb.makedsn(DB_CONFIG["host"], DB_CONFIG["port"], sid=DB_CONFIG["sid"])) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT c.cnst_cd, c.cnst_nm, c.cnst_gbn, c.use_yn, c.cnst_val, c.penalty_val,
                           COUNT(DISTINCT c.org_id) AS org_cnt
                    FROM HRAI_CON.MOVE_CASE_CNST_MASTER c
                    WHERE c.ftr_move_std_id = :mid AND c.rev_id = 999
                      AND c.case_id = (SELECT MAX(case_id) FROM HRAI_CON.MOVE_CASE_MASTER WHERE ftr_move_std_id = :mid)
                    GROUP BY c.cnst_cd, c.cnst_nm, c.cnst_gbn, c.use_yn, c.cnst_val, c.penalty_val
                    ORDER BY c.use_yn DESC, c.cnst_cd
                """, {"mid": mid})
                rows = cur.fetchall()
        if not rows:
            return '<div style="padding:20px;text-align:center;color:#9ca3af;">제약조건 데이터 없음</div>'
        df = pd.DataFrame(rows, columns=["제약코드", "제약조건명", "제약구분", "사용여부", "제약값", "패널티값", "적용사업소수"])
        return _cnst_df_to_html(df, title="제약조건 요약", badge_col="사용여부")
    except Exception as e:
        print(f"제약조건 요약 조회 실패: {e}")
        return f'<div style="padding:12px;color:#ef4444;">조회 오류</div>'


def _penalty_top_html(move_std_id):
    """감점 TOP 20"""
    if not move_std_id or move_std_id == "0":
        return '<div style="padding:20px;text-align:center;color:#9ca3af;">이동번호를 선택하세요.</div>'
    try:
        import oracledb
        from config import DB_CONFIG
        mid = int(move_std_id)
        with oracledb.connect(user=DB_CONFIG["user"], password=DB_CONFIG["password"],
                              dsn=oracledb.makedsn(DB_CONFIG["host"], DB_CONFIG["port"], sid=DB_CONFIG["sid"])) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT p.penalty_nm, SUM(p.vio_cnt) AS total_vio,
                           MAX(p.penalty_val) AS unit_pen, SUM(p.opt_val) AS total_pen
                    FROM HRAI_CON.MOVE_CASE_PENALTY_INFO p
                    WHERE p.ftr_move_std_id = :mid AND p.rev_id = 999 AND p.vio_cnt > 0
                      AND p.case_id = (SELECT MAX(case_id) FROM HRAI_CON.MOVE_CASE_MASTER WHERE ftr_move_std_id = :mid)
                    GROUP BY p.penalty_nm
                    ORDER BY SUM(p.opt_val) DESC
                    FETCH FIRST 20 ROWS ONLY
                """, {"mid": mid})
                rows = cur.fetchall()
        if not rows:
            return '<div style="padding:20px;text-align:center;color:#9ca3af;">감점 데이터 없음</div>'
        df = pd.DataFrame(rows, columns=["감점항목명", "총위반건수", "건당감점값", "총감점합계"])
        return _cnst_df_to_html(df, title="감점 TOP 20", rank_col=True)
    except Exception as e:
        print(f"감점 TOP 조회 실패: {e}")
        return f'<div style="padding:12px;color:#ef4444;">조회 오류</div>'


def _org_violation_html(move_std_id):
    """사업소별 제약 위반 현황"""
    if not move_std_id or move_std_id == "0":
        return '<div style="padding:20px;text-align:center;color:#9ca3af;">이동번호를 선택하세요.</div>'
    try:
        import oracledb
        from config import DB_CONFIG
        mid = int(move_std_id)
        with oracledb.connect(user=DB_CONFIG["user"], password=DB_CONFIG["password"],
                              dsn=oracledb.makedsn(DB_CONFIG["host"], DB_CONFIG["port"], sid=DB_CONFIG["sid"])) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT cn.org_nm AS org_name,
                           COUNT(DISTINCT cn.cnst_cd) AS vio_cnst_cnt,
                           SUM(p.vio_cnt) AS total_vio,
                           SUM(p.opt_val) AS total_pen
                    FROM HRAI_CON.MOVE_CASE_PENALTY_INFO p
                    JOIN HRAI_CON.MOVE_CASE_CNST_MASTER cn
                        ON p.ftr_move_std_id = cn.ftr_move_std_id
                        AND p.case_id = cn.case_id AND p.case_det_id = cn.case_det_id
                        AND p.rev_id = cn.rev_id AND cn.org_id IS NOT NULL
                    WHERE p.ftr_move_std_id = :mid AND p.rev_id = 999 AND p.vio_cnt > 0
                      AND p.case_id = (SELECT MAX(case_id) FROM HRAI_CON.MOVE_CASE_MASTER WHERE ftr_move_std_id = :mid)
                    GROUP BY cn.org_nm
                    ORDER BY SUM(p.opt_val) DESC
                    FETCH FIRST 30 ROWS ONLY
                """, {"mid": mid})
                rows = cur.fetchall()
        if not rows:
            return '<div style="padding:20px;text-align:center;color:#9ca3af;">위반 데이터 없음</div>'
        df = pd.DataFrame(rows, columns=["사업소명", "위반제약수", "총위반건수", "총감점합계"])
        return _cnst_df_to_html(df, title="사업소별 위반 현황 TOP 30", rank_col=True)
    except Exception as e:
        print(f"사업소별 위반 조회 실패: {e}")
        return f'<div style="padding:12px;color:#ef4444;">조회 오류</div>'


def _run_cnst_analysis(move_std_id):
    """3개 분석을 실행하여 (summary, penalty, org) 반환"""
    return _cnst_summary_html(move_std_id), _penalty_top_html(move_std_id), _org_violation_html(move_std_id)



# ===== 배치 결과 리포트 함수 =====

def _report_summary_html(move_std_id):
    """총 대상자/배치완료/미배치 요약 카드 HTML"""
    if not move_std_id or move_std_id == "0":
        return '<div style="padding:20px;text-align:center;color:#9ca3af;">이동번호를 선택하세요.</div>', {}
    try:
        import oracledb
        from config import DB_CONFIG
        mid = int(move_std_id)
        with oracledb.connect(user=DB_CONFIG["user"], password=DB_CONFIG["password"],
                              dsn=oracledb.makedsn(DB_CONFIG["host"], DB_CONFIG["port"], sid=DB_CONFIG["sid"])) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT 
                        COUNT(*) AS total,
                        SUM(CASE WHEN c.new_org_id IS NOT NULL AND c.new_org_id != m.org_id THEN 1 ELSE 0 END) AS moved,
                        SUM(CASE WHEN c.must_stay_yn = '1' THEN 1 ELSE 0 END) AS stayed,
                        SUM(CASE WHEN c.new_org_id IS NULL THEN 1 ELSE 0 END) AS unplaced
                    FROM HRAI_CON.move_item_master m
                    LEFT JOIN HRAI_CON.move_case_item c 
                        ON m.ftr_move_std_id = c.ftr_move_std_id AND m.emp_id = c.emp_id
                        AND c.rev_id = 999
                        AND c.case_id = (SELECT MAX(case_id) FROM HRAI_CON.MOVE_CASE_MASTER WHERE ftr_move_std_id = :mid)
                    WHERE m.ftr_move_std_id = :mid
                """, {"mid": mid})
                row = cur.fetchone()
        if not row or row[0] == 0:
            return '<div style="padding:20px;text-align:center;color:#9ca3af;">배치 결과 데이터가 없습니다.</div>', {}
        total, moved, stayed, unplaced = (int(v or 0) for v in row)
        move_rate = round(moved / total * 100, 1) if total > 0 else 0
        stats = {"total": total, "moved": moved, "stayed": stayed, "unplaced": unplaced, "move_rate": move_rate}
        cards = [
            {"label": "총 대상자", "value": f"{total:,}명", "color": "#3b82f6", "icon": "👥"},
            {"label": "배치완료(이동)", "value": f"{moved:,}명", "color": "#10b981", "icon": "✅"},
            {"label": "필수유보", "value": f"{stayed:,}명", "color": "#f59e0b", "icon": "⛔"},
            {"label": "이동율", "value": f"{move_rate}%", "color": "#8b5cf6", "icon": "📊"},
        ]
        html = '<div style="display:flex;gap:16px;flex-wrap:wrap;">'
        for c in cards:
            html += (
                f'<div style="flex:1;min-width:180px;background:white;border-radius:12px;padding:18px 22px;'
                f'box-shadow:0 2px 10px rgba(0,0,0,0.06);border-left:4px solid {c["color"]};">'
                f'<div style="font-size:12px;color:#6b7280;margin-bottom:4px;">{c["icon"]} {c["label"]}</div>'
                f'<div style="font-size:1.6em;font-weight:800;color:#111827;">{c["value"]}</div>'
                f'</div>'
            )
        html += '</div>'
        return html, stats
    except Exception as e:
        print(f"배치 결과 요약 조회 실패: {e}")
        return '<div style="padding:12px;color:#ef4444;">요약 조회 오류</div>', {}


def _report_region_html(move_std_id):
    """권역별 이동현황 테이블"""
    if not move_std_id or move_std_id == "0":
        return '<div style="padding:20px;text-align:center;color:#9ca3af;">이동번호를 선택하세요.</div>', []
    try:
        import oracledb
        from config import DB_CONFIG
        mid = int(move_std_id)
        with oracledb.connect(user=DB_CONFIG["user"], password=DB_CONFIG["password"],
                              dsn=oracledb.makedsn(DB_CONFIG["host"], DB_CONFIG["port"], sid=DB_CONFIG["sid"])) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT 
                        NVL(m.lvl2_nm, '(미지정)') AS region,
                        COUNT(*) AS total,
                        SUM(CASE WHEN c.new_org_id IS NOT NULL AND c.new_org_id != m.org_id THEN 1 ELSE 0 END) AS moved,
                        SUM(CASE WHEN c.new_org_id IS NULL OR c.new_org_id = m.org_id THEN 1 ELSE 0 END) AS stayed
                    FROM HRAI_CON.move_item_master m
                    LEFT JOIN HRAI_CON.move_case_item c 
                        ON m.ftr_move_std_id = c.ftr_move_std_id AND m.emp_id = c.emp_id
                        AND c.rev_id = 999
                        AND c.case_id = (SELECT MAX(case_id) FROM HRAI_CON.MOVE_CASE_MASTER WHERE ftr_move_std_id = :mid)
                    WHERE m.ftr_move_std_id = :mid
                    GROUP BY m.lvl2_nm
                    ORDER BY m.lvl2_nm
                """, {"mid": mid})
                rows = cur.fetchall()
        if not rows:
            return '<div style="padding:20px;text-align:center;color:#9ca3af;">권역별 데이터 없음</div>', []
        df = pd.DataFrame(rows, columns=["권역", "총원", "이동", "미이동"])
        region_data = [{"region": r["권역"], "total": int(r["총원"]), "moved": int(r["이동"]), "stayed": int(r["미이동"])} for _, r in df.iterrows()]
        return _cnst_df_to_html(df, title="권역별 이동현황"), region_data
    except Exception as e:
        print(f"권역별 이동현황 조회 실패: {e}")
        return '<div style="padding:12px;color:#ef4444;">조회 오류</div>', []


def _report_penalty_top10_html(move_std_id):
    """감점 상위 10개 항목"""
    if not move_std_id or move_std_id == "0":
        return '<div style="padding:20px;text-align:center;color:#9ca3af;">이동번호를 선택하세요.</div>', []
    try:
        import oracledb
        from config import DB_CONFIG
        mid = int(move_std_id)
        with oracledb.connect(user=DB_CONFIG["user"], password=DB_CONFIG["password"],
                              dsn=oracledb.makedsn(DB_CONFIG["host"], DB_CONFIG["port"], sid=DB_CONFIG["sid"])) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT p.penalty_nm, SUM(p.vio_cnt) AS total_vio,
                           MAX(p.penalty_val) AS unit_pen, SUM(p.opt_val) AS total_pen
                    FROM HRAI_CON.MOVE_CASE_PENALTY_INFO p
                    WHERE p.ftr_move_std_id = :mid AND p.rev_id = 999 AND p.vio_cnt > 0
                      AND p.case_id = (SELECT MAX(case_id) FROM HRAI_CON.MOVE_CASE_MASTER WHERE ftr_move_std_id = :mid)
                    GROUP BY p.penalty_nm
                    ORDER BY SUM(p.opt_val) DESC
                    FETCH FIRST 10 ROWS ONLY
                """, {"mid": mid})
                rows = cur.fetchall()
        if not rows:
            return '<div style="padding:20px;text-align:center;color:#9ca3af;">감점 데이터 없음</div>', []
        df = pd.DataFrame(rows, columns=["감점항목명", "총위반건수", "건당감점값", "총감점합계"])
        penalty_data = [{"name": r["감점항목명"], "vio": int(r["총위반건수"]), "pen": float(r["총감점합계"])} for _, r in df.iterrows()]
        return _cnst_df_to_html(df, title="감점 TOP 10", rank_col=True), penalty_data
    except Exception as e:
        print(f"감점 TOP 10 조회 실패: {e}")
        return '<div style="padding:12px;color:#ef4444;">조회 오류</div>', []


def _report_must_move_html(move_std_id):
    """필수이동/필수유보 처리현황"""
    if not move_std_id or move_std_id == "0":
        return '<div style="padding:20px;text-align:center;color:#9ca3af;">이동번호를 선택하세요.</div>', []
    try:
        import oracledb
        from config import DB_CONFIG
        mid = int(move_std_id)
        with oracledb.connect(user=DB_CONFIG["user"], password=DB_CONFIG["password"],
                              dsn=oracledb.makedsn(DB_CONFIG["host"], DB_CONFIG["port"], sid=DB_CONFIG["sid"])) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT 
                        CASE WHEN m.must_move_yn = '1' THEN '필수이동' 
                             WHEN m.must_stay_yn = '1' THEN '필수유보'
                             ELSE '일반' END AS category,
                        COUNT(*) AS cnt,
                        SUM(CASE WHEN c.new_org_id IS NOT NULL AND c.new_org_id != m.org_id THEN 1 ELSE 0 END) AS moved_cnt
                    FROM HRAI_CON.move_item_master m
                    LEFT JOIN HRAI_CON.move_case_item c 
                        ON m.ftr_move_std_id = c.ftr_move_std_id AND m.emp_id = c.emp_id
                        AND c.rev_id = 999
                        AND c.case_id = (SELECT MAX(case_id) FROM HRAI_CON.MOVE_CASE_MASTER WHERE ftr_move_std_id = :mid)
                    WHERE m.ftr_move_std_id = :mid
                    GROUP BY CASE WHEN m.must_move_yn = '1' THEN '필수이동' 
                                  WHEN m.must_stay_yn = '1' THEN '필수유보'
                                  ELSE '일반' END
                    ORDER BY 1
                """, {"mid": mid})
                rows = cur.fetchall()
        if not rows:
            return '<div style="padding:20px;text-align:center;color:#9ca3af;">필수이동/유보 데이터 없음</div>', []
        df = pd.DataFrame(rows, columns=["구분", "인원수", "이동완료"])
        must_data = [{"category": r["구분"], "cnt": int(r["인원수"]), "moved": int(r["이동완료"])} for _, r in df.iterrows()]
        return _cnst_df_to_html(df, title="필수이동/유보 처리현황"), must_data
    except Exception as e:
        print(f"필수이동/유보 조회 실패: {e}")
        return '<div style="padding:12px;color:#ef4444;">조회 오류</div>', []


def _report_job_type_html(move_std_id):
    """직무별 배치현황"""
    if not move_std_id or move_std_id == "0":
        return '<div style="padding:20px;text-align:center;color:#9ca3af;">이동번호를 선택하세요.</div>', []
    try:
        import oracledb
        from config import DB_CONFIG
        mid = int(move_std_id)
        with oracledb.connect(user=DB_CONFIG["user"], password=DB_CONFIG["password"],
                              dsn=oracledb.makedsn(DB_CONFIG["host"], DB_CONFIG["port"], sid=DB_CONFIG["sid"])) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT 
                        NVL(m.job_type1, '(미지정)') AS job_type,
                        COUNT(*) AS total,
                        SUM(CASE WHEN c.new_org_id IS NOT NULL AND c.new_org_id != m.org_id THEN 1 ELSE 0 END) AS moved
                    FROM HRAI_CON.move_item_master m
                    LEFT JOIN HRAI_CON.move_case_item c 
                        ON m.ftr_move_std_id = c.ftr_move_std_id AND m.emp_id = c.emp_id
                        AND c.rev_id = 999
                        AND c.case_id = (SELECT MAX(case_id) FROM HRAI_CON.MOVE_CASE_MASTER WHERE ftr_move_std_id = :mid)
                    WHERE m.ftr_move_std_id = :mid
                    GROUP BY m.job_type1
                    ORDER BY COUNT(*) DESC
                """, {"mid": mid})
                rows = cur.fetchall()
        if not rows:
            return '<div style="padding:20px;text-align:center;color:#9ca3af;">직무별 데이터 없음</div>', []
        df = pd.DataFrame(rows, columns=["직무", "총원", "이동"])
        job_data = [{"job": r["직무"], "total": int(r["총원"]), "moved": int(r["이동"])} for _, r in df.iterrows()]
        return _cnst_df_to_html(df, title="직무별 배치현황"), job_data
    except Exception as e:
        print(f"직무별 배치현황 조회 실패: {e}")
        return '<div style="padding:12px;color:#ef4444;">조회 오류</div>', []


def _report_llm_summary(stats, region_data, penalty_data, must_data, job_data):
    """LLM을 호출하여 배치 결과를 자연어로 요약"""
    if not stats:
        return "(데이터가 없어 요약을 생성할 수 없습니다.)"
    try:
        safe = lambda s: str(s).replace(chr(10), ' ').replace(chr(13), '').replace('#', '').replace('`', '')[:100]

        ctx_parts = []
        ctx_parts.append(f"총 대상자: {stats.get('total',0):,}명, 이동완료: {stats.get('moved',0):,}명, "
                         f"필수유보: {stats.get('stayed',0):,}명, 미배치: {stats.get('unplaced',0):,}명, "
                         f"이동율: {stats.get('move_rate',0)}%")
        if region_data:
            region_strs = [f"{safe(r['region'])}({r['moved']}/{r['total']})" for r in region_data]
            ctx_parts.append("권역별(이동/총원): " + ", ".join(region_strs))
        if penalty_data:
            pen_strs = [f"{safe(p['name'])}(위반{p['vio']}건,감점{p['pen']:.0f})" for p in penalty_data[:5]]
            ctx_parts.append("주요 감점항목: " + ", ".join(pen_strs))
        if must_data:
            must_strs = [f"{safe(m['category'])}({m['moved']}/{m['cnt']}명 이동)" for m in must_data]
            ctx_parts.append("필수이동/유보: " + ", ".join(must_strs))
        if job_data:
            job_strs = [f"{safe(j['job'])}({j['moved']}/{j['total']})" for j in job_data[:5]]
            ctx_parts.append("직무별(이동/총원): " + ", ".join(job_strs))

        context = chr(10).join(ctx_parts)

        system_msg = ("당신은 HR 정기인사이동(HDTP) 배치 최적화 결과를 분석하는 전문가입니다. "
                      "아래 배치 결과 데이터를 바탕으로 3~4문장의 한국어 요약을 작성하세요. "
                      "핵심 수치와 특이사항을 중심으로 간결하게 정리하세요.")
        user_msg = f"## 배치 결과 데이터{chr(10)}{context}{chr(10)}{chr(10)}위 데이터를 바탕으로 배치 결과 요약을 작성하세요."

        llm = get_report_llm()
        messages = [SystemMessage(content=system_msg), HumanMessage(content=user_msg)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            future = ex.submit(llm.invoke, messages)
            resp = future.result(timeout=60)
        return resp.content.strip()
    except Exception as e:
        print(f"LLM 요약 생성 실패: {e}")
        if stats:
            return (f"총 {stats.get('total',0):,}명 중 {stats.get('moved',0):,}명이 이동 배치되어 "
                    f"이동율 {stats.get('move_rate',0)}%를 기록했습니다. "
                    f"필수유보 {stats.get('stayed',0):,}명, 미배치 {stats.get('unplaced',0):,}명입니다. "
                    f"(LLM 요약 생성에 실패하여 기본 요약을 표시합니다.)")
        return "(요약 생성 실패)"

def _run_batch_report(move_std_id):
    """배치 결과 리포트의 모든 섹션을 실행하여 6개 출력을 반환"""
    # 섹션 1: 요약 카드
    summary_html, stats = _report_summary_html(move_std_id)
    # 섹션 2: 권역별 이동현황
    region_html, region_data = _report_region_html(move_std_id)
    # 섹션 3: 감점 TOP 10
    penalty_html, penalty_data = _report_penalty_top10_html(move_std_id)
    # 섹션 4: 필수이동/유보 처리현황
    must_html, must_data = _report_must_move_html(move_std_id)
    # 섹션 5: 직무별 배치현황
    job_html, job_data = _report_job_type_html(move_std_id)
    # 섹션 6: LLM 자연어 요약
    llm_summary = _report_llm_summary(stats, region_data, penalty_data, must_data, job_data)

    # outputs 순서: summary, region, job, must, penalty, llm (event handler와 동일)
    return summary_html, region_html, job_html, must_html, penalty_html, llm_summary

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
## 데이터베이스 스키마 정보 (HRAI_CON)

> HDTP 정기인사 전환배치 최적화 시스템 — 15개 핵심 테이블

### 조직 계층 구조 (5단계)
```
LVL1(본사) → LVL2(권역) → LVL3(사업소) → LVL4(팀) → LVL5(파트)
             A=서울  B=경기/인천  C=광역점  D=아울렛  E=기타
```

### 핵심 연결 키
- **FTR_MOVE_STD_ID** (이동번호): 거의 모든 MOVE_* 테이블의 공통 조인 키
- **REV_ID = 999**: 최종 확정 리비전 (조회 시 기본 필터)

---

### 테이블 요약
| 테이블 | 설명 | 주요 PK |
|--------|------|--------|
| FTR_MOVE_STD | 이동기준 마스터 | FTR_MOVE_STD_ID |
| MOVE_ITEM_MASTER | 직원 마스터 (76컬럼) | FTR_MOVE_STD_ID + EMP_ID |
| MOVE_ITEM_DETAIL | 발령정보 (메일 발송) | FTR_MOVE_STD_ID + EMP_NO |
| MOVE_ORG_MASTER | 사업소/조직 마스터 | FTR_MOVE_STD_ID + ORG_ID |
| MOVE_NETWORK_CHANGE | 사업소 변경정보 | FTR_MOVE_STD_ID + CHG_ID |
| MOVE_CASE_MASTER | 배치 케이스 | FTR_MOVE_STD_ID + CASE_ID |
| MOVE_CASE_DETAIL | 케이스 상세/리비전 | + CASE_DET_ID + REV_ID |
| MOVE_CASE_ITEM | 배치 결과 (직원별) | + EMP_ID |
| MOVE_CASE_ORG | 조직별 TO 설정 | + ORG_ID |
| MOVE_CASE_CNST_MASTER | 제약조건 (48개 코드) | + ORG_ID + CNST_CD |
| MOVE_CASE_PENALTY_INFO | 감점 상세 | + CNST_ID |
| MOVE_JOBTYPE_PENALTY_MATRIX | 직무 호환성 매트릭스 | JOBTYPE_PROP |
| MOVE_STAY_RULE | 필수유보 기준 | MOVE_STAY_RULE_ID |
| MOVE_EMP_EXCLUSION | 동시배치불가 직원 | EMP_NO1 + EMP_NO2 |
| ML_MAP_DICTIONARY | ML 직무분류 매핑 | DIC_ID |

---

### 1. FTR_MOVE_STD (이동기준 마스터)
| 컬럼명 | 한글명 | 설명 |
|--------|--------|------|
| ftr_move_std_id | 이동번호 | 이동기준 고유번호 (PK) |
| std_nm | 기준명 | 이동기준 이름 |
| base_ym | 기준년월 | YYYYMM 형식 |
| base_ymd | 기준일자 | YYYYMMDD 형식 |
| use_yn | 사용여부 | Y/N |

### 2. MOVE_ITEM_MASTER (직원 마스터)
| 컬럼명 | 한글명 | 설명 |
|--------|--------|------|
| ftr_move_std_id | 이동번호 | 배치 기준 (PK) |
| emp_id | 사원ID | 직원 고유번호 (PK) |
| emp_no | 사원번호 | 사번 |
| emp_nm | 이름 | 직원 성명 |
| lvl1_nm ~ lvl5_nm | 조직계층 | 1~5단계 조직 계층명 |
| org_nm | 현재조직 | 소속 부서명 |
| prev_org_nm | 이전조직 | 직전 소속 부서명 |
| job_type1/2/3 | 직종 | 직종 분류 (대/소/담당) |
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
| must_stay_yn | 필수유보 | 유보 여부 (1/0) |
| must_move_yn | 필수이동 | 이동 여부 (1/0) |

### 3. MOVE_ITEM_DETAIL (발령정보)
| 컬럼명 | 한글명 | 설명 |
|--------|--------|------|
| ftr_move_std_id | 이동번호 | PK |
| emp_no | 사원번호 | 사번 (PK) |
| org_type | 조직유형 | 조직 유형 (PK) |
| send_yn | 발송여부 | 메일 발송 여부 |
| send_date | 발송일자 | 메일 발송 일자 |

### 4. MOVE_ORG_MASTER (사업소/조직 마스터)
| 컬럼명 | 한글명 | 설명 |
|--------|--------|------|
| ftr_move_std_id | 이동번호 | PK |
| org_id | 조직ID | 조직 고유번호 (PK) |
| parent_org_id | 상위조직ID | 상위 조직 ID |
| org_cd | 조직코드 | 조직 코드 |
| org_nm | 조직명 | 조직/부서명 |
| org_type | 조직유형 | 조직 유형 분류 |
| lvl1_nm ~ lvl5_nm | 조직계층 | 1~5단계 조직 계층명 |
| full_path | 전체경로 | 조직 전체 경로 |
| lvl | 레벨 | 조직 계층 레벨(단계) |
| job_type1/2 | 직종 | 조직 직종 분류 |
| tot_to | 정원 | 배정 정원(TO) |
| region_type | 지역구분 | 조직 소재 지역 |
| addr | 주소 | 조직 주소 |

### 5. MOVE_NETWORK_CHANGE (사업소 변경정보)
| 컬럼명 | 한글명 | 설명 |
|--------|--------|------|
| ftr_move_std_id | 이동번호 | PK |
| chg_id | 변경ID | 변경 고유번호 (PK) |
| org_id | 조직ID | 대상 조직 |
| before_org_nm | 변경전조직명 | 변경 전 이름 |
| after_org_nm | 변경후조직명 | 변경 후 이름 |

### 6. MOVE_CASE_MASTER (배치 케이스)
| 컬럼명 | 한글명 | 설명 |
|--------|--------|------|
| ftr_move_std_id | 이동번호 | PK |
| case_id | 케이스ID | 배치안 번호 (PK) |
| case_nm | 케이스명 | 배치안 이름 |
| case_desc | 설명 | 배치안 설명 |
| confirm_yn | 확정여부 | 확정 여부 (Y/N) |

### 7. MOVE_CASE_DETAIL (케이스 상세/리비전)
| 컬럼명 | 한글명 | 설명 |
|--------|--------|------|
| ftr_move_std_id | 이동번호 | PK |
| case_id | 케이스ID | PK |
| case_det_id | 상세ID | 시나리오 상세 ID (PK) |
| rev_id | 리비전ID | 수정 버전 (PK, 999=최종) |
| rev_nm | 리비전명 | 리비전 이름 |
| opt_status | 최적화상태 | 최적화 실행 상태 |

### 8. MOVE_CASE_ITEM (배치 결과 — 직원별)
| 컬럼명 | 한글명 | 설명 |
|--------|--------|------|
| ftr_move_std_id | 이동번호 | PK |
| case_id | 케이스ID | PK |
| case_det_id | 상세ID | PK |
| rev_id | 리비전ID | PK (999=최종) |
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

### 9. MOVE_CASE_ORG (조직별 TO 설정)
| 컬럼명 | 한글명 | 설명 |
|--------|--------|------|
| ftr_move_std_id | 이동번호 | PK |
| case_id | 케이스ID | PK |
| case_det_id | 상세ID | PK |
| rev_id | 리비전ID | PK |
| org_id | 조직ID | PK |
| alg_tot_to | 배치가능인원 | 총 TO |
| stay_cnt | 잔류인원 | 잔류 직원 수 |
| move_in_cnt | 전입인원 | 전입 직원 수 |
| move_out_cnt | 전출인원 | 전출 직원 수 |

### 10. MOVE_CASE_CNST_MASTER (제약조건)
| 컬럼명 | 한글명 | 설명 |
|--------|--------|------|
| ftr_move_std_id | 이동번호 | PK |
| case_id | 케이스ID | PK |
| case_det_id | 상세ID | PK |
| rev_id | 리비전ID | PK |
| org_id | 조직ID | 대상 조직 ID (PK) |
| org_nm | 조직명 | 대상 조직명 |
| cnst_cd | 제약코드 | 제약 코드 (PK, TEAM001~048) |
| cnst_nm | 제약조건명 | 제약 조건 이름 |
| cnst_gbn | 제약구분 | 제약 조건 구분 |
| apply_target | 적용대상 | 적용 대상 |
| cnst_val | 제약값 | 제약 조건 수치 |
| penalty_val | 패널티 | 위반 시 패널티 점수 |
| use_yn | 사용여부 | 사용 여부 (Y/N) |
| cnst_des | 설명 | 제약 조건 상세 설명 |

### 11. MOVE_CASE_PENALTY_INFO (감점 상세)
| 컬럼명 | 한글명 | 설명 |
|--------|--------|------|
| ftr_move_std_id | 이동번호 | PK |
| case_id / case_det_id / rev_id | 케이스 키 | PK |
| cnst_id | 제약ID | 제약 고유 ID |
| penalty_nm | 감점명 | 감점 항목명 |
| vio_cnt | 위반건수 | 위반 건수 |
| penalty_val | 감점값 | 건당 감점 |
| opt_val | 최적화값 | 위반건수 x 감점값 |

### 12. MOVE_JOBTYPE_PENALTY_MATRIX (직무 호환성 매트릭스)
| 컬럼명 | 한글명 | 설명 |
|--------|--------|------|
| ftr_move_std_id | 이동번호 | PK |
| jobtype_prop | 직무속성 | 직무 분류 속성 |
| 직무별 컬럼 | 감점값 | FROM → TO 직무 전환 시 감점 |

### 13. MOVE_STAY_RULE (필수유보 기준)
| 컬럼명 | 한글명 | 설명 |
|--------|--------|------|
| ftr_move_std_id | 이동번호 | PK |
| move_stay_rule_id | 기준ID | 규칙 고유번호 (PK) |
| rule_nm | 규칙명 | 유보 규칙 이름 |
| stay_mon | 유보개월 | 유보 기간(개월) |

### 14. MOVE_EMP_EXCLUSION (동시배치불가 직원)
| 컬럼명 | 한글명 | 설명 |
|--------|--------|------|
| ftr_move_std_id | 이동번호 | PK |
| emp_no1 | 사번1 | 직원1 사번 (PK) |
| emp_no2 | 사번2 | 직원2 사번 (PK) |
| reason_type | 사유유형 | 부부/징계 등 (PK) |

### 15. ML_MAP_DICTIONARY (ML 직무분류 매핑)
| 컬럼명 | 한글명 | 설명 |
|--------|--------|------|
| dic_id | 사전ID | 매핑 고유번호 (PK) |
| dic_type | 사전유형 | 매핑 유형 |
| src_val | 원본값 | 원본 직무값 |
| tgt_val | 매핑값 | 매핑된 직무값 |

---

### 주요 제약조건 코드 (TEAM001~048)
| 코드 | 유형 | 설명 |
|------|------|------|
| TEAM001 | 필수 | TO(충원기준인원) 초과 불가 |
| TEAM002 | 필수 | 필수이동 직원 반드시 이동 |
| TEAM003 | 필수 | 미배치자 반드시 배치 |
| TEAM004 | 필수 | 징계 가해자/피해자 동일사업소 금지 |
| TEAM006 | 필수 | 부부 동일사업소 금지 |
| TEAM007 | 감점 | 권역별 종합점수 평균 ±10% 균형 |
| TEAM020 | 감점 | 사업소 이동비율 제약 (보통 40%) |
| TEAM021 | 감점 | 남성직원 최소 1인 |
| TEAM022 | 감점 | 팀 전원이동 금지 |
| TEAM023 | 감점 | 동일팀→동일팀 이동 불가 |
| TEAM033 | 필수 | 18개월 이내 이동 제한 |
| TEAM035 | 필수 | 24개월 이내 이동 제한 |
| TEAM048 | 감점 | 희망직무 배정 가점 |

---

### 테이블 관계 (JOIN 조건)
```
┌──────────────┐                                     ┌──────────────────┐
│ FTR_MOVE_STD │──(FTR_MOVE_STD_ID)──────────────────►  모든 MOVE_* 테이블 │
│  (이동기준)    │                                     └──────────────────┘
└──────────────┘

┌──────────────────┐     FTR_MOVE_STD_ID + EMP_ID     ┌──────────────────┐
│ MOVE_ITEM_MASTER │◄────────────────────────────────►│  MOVE_CASE_ITEM  │
│   (직원 마스터)    │                                   │  (배치 결과)      │
└──────────────────┘                                   └──────────────────┘
                                                              │
                           FTR_MOVE_STD_ID + CASE_ID          │ NEW_ORG_ID = ORG_ID
                           + CASE_DET_ID + REV_ID             │
                                                              ▼
┌──────────────────────┐   FTR_MOVE_STD_ID + ORG_ID   ┌──────────────────┐
│MOVE_CASE_CNST_MASTER │◄────────────────────────────►│ MOVE_ORG_MASTER  │
│   (제약조건)          │                               │  (조직 마스터)    │
└──────────────────────┘                               └──────────────────┘

┌──────────────────┐    CASE_ID + CASE_DET_ID + REV_ID  ┌──────────────────┐
│ MOVE_CASE_MASTER │───────────────────────────────────►│ MOVE_CASE_DETAIL │
│  (배치 케이스)     │                                    │  (리비전 관리)    │
└──────────────────┘                                    └──────────────────┘
```

### JOIN SQL 예시
| 조인 | SQL |
|------|-----|
| 직원 ↔ 배치결과 | `m JOIN c ON m.ftr_move_std_id = c.ftr_move_std_id AND m.emp_id = c.emp_id` |
| 배치결과 → 새조직 | `c JOIN o ON c.ftr_move_std_id = o.ftr_move_std_id AND c.new_org_id = o.org_id` |
| 제약조건 ↔ 조직 | `cn JOIN o ON cn.ftr_move_std_id = o.ftr_move_std_id AND cn.org_id = o.org_id` |
| 직원 → 발령정보 | `m JOIN d ON m.ftr_move_std_id = d.ftr_move_std_id AND m.emp_no = d.emp_no` |
| 케이스 → 상세 | `cm JOIN cd ON cm.ftr_move_std_id = cd.ftr_move_std_id AND cm.case_id = cd.case_id` |
| 배치결과 → 감점 | `ci JOIN p ON ci.ftr_move_std_id = p.ftr_move_std_id AND ci.case_id = p.case_id` |
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
            cell_val = '' if pd.isna(val) else _html_mod.escape(str(val))
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



def _cnst_df_to_html(df, title="", badge_col=None, rank_col=False):
    """제약조건 분석 전용 HTML 테이블 렌더러"""
    if not isinstance(df, pd.DataFrame) or df.empty:
        return '<div style="padding:20px;text-align:center;color:#9ca3af;">데이터 없음</div>'
    header = ""
    if title:
        header = (f'<div style="padding:10px 16px 8px;font-weight:700;font-size:14px;'
                  f'color:#374151;border-bottom:2px solid #667eea20;">{title}'
                  f'<span style="margin-left:8px;font-size:12px;font-weight:400;color:#9ca3af;">({len(df)}건)</span></div>')
    html = f'<div style="border-radius:12px;overflow:hidden;border:1px solid #e5e7eb;box-shadow:0 2px 8px rgba(0,0,0,0.04);">{header}'
    if len(df) > 25:
        html += '<div style="max-height:420px;overflow:auto;">'
    html += '<table style="width:100%;border-collapse:collapse;font-size:13px;">'
    html += '<thead style="position:sticky;top:0;z-index:1;"><tr>'
    if rank_col:
        html += '<th style="background:#f8fafc;padding:9px 10px;text-align:center;font-weight:600;color:#6b7280;border-bottom:2px solid #e5e7eb;width:36px;">#</th>'
    for col in df.columns:
        html += f'<th style="background:#f8fafc;padding:9px 14px;text-align:left;font-weight:600;color:#374151;border-bottom:2px solid #e5e7eb;white-space:nowrap;">{col}</th>'
    html += '</tr></thead><tbody>'
    for i, (_, row) in enumerate(df.iterrows()):
        bg = '#ffffff' if i % 2 == 0 else '#f9fafb'
        html += f'<tr style="background:{bg};">'
        if rank_col:
            rc = "#667eea" if i < 3 else "#9ca3af"
            html += f'<td style="padding:8px 10px;text-align:center;color:{rc};font-weight:700;border-bottom:1px solid #f1f5f9;">{i+1}</td>'
        for col in df.columns:
            val = row[col]
            import html as _html
            cell = '' if pd.isna(val) else _html.escape(str(val))
            style = "padding:8px 14px;border-bottom:1px solid #f1f5f9;color:#111827;"
            if col == badge_col:
                if cell == 'Y':
                    cell = '<span style="background:#10b98120;color:#10b981;padding:2px 8px;border-radius:10px;font-size:12px;font-weight:600;">Y</span>'
                else:
                    cell = '<span style="background:#9ca3af20;color:#9ca3af;padding:2px 8px;border-radius:10px;font-size:12px;font-weight:600;">N</span>'
            elif isinstance(val, (int, float)) and not pd.isna(val):
                try:
                    cell = f'{int(val):,}' if float(val) == int(float(val)) else f'{float(val):,.2f}'
                except (ValueError, OverflowError):
                    pass
                style += "text-align:right;font-variant-numeric:tabular-nums;"
            html += f'<td style="{style}">{cell}</td>'
        html += '</tr>'
    html += '</tbody></table>'
    if len(df) > 25:
        html += '</div>'
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
def process_generate(question: str, model_key: str, move_std_id: str, progress=gr.Progress()):
    """SQL만 생성 (실행하지 않음)"""
    if not question or not question.strip():
        return "", "질문을 입력해주세요.", ""
    if model_key not in MODEL_REGISTRY:
        model_key = DEFAULT_MODEL_KEY

    # 이동번호 조건을 질문에 추가
    enhanced_question = question.strip()
    if move_std_id and move_std_id != "0":
        if re.fullmatch(r'\d{1,10}', move_std_id):
            enhanced_question = f"[이동번호(FTR_MOVE_STD_ID)={move_std_id} 조건 필수] {enhanced_question}"

    progress(0.3, desc="SQL 생성 중...")
    result = generate_sql(enhanced_question, model_key=model_key)
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

            # 예시 질문 (at top of tab) — 30개, 15개 테이블 커버
            gr.Examples(
                examples=[
                    # 직원 통계
                    ["전체 직원 수는 몇 명이야?"],
                    ["남자, 여자 인원 수를 알려줘"],
                    ["직급별 인원 수를 보여줘"],
                    ["30대 직원 목록을 보여줘"],
                    ["근무 기간이 가장 긴 직원 TOP 10을 알려줘"],
                    # 조직 분석
                    ["권역별 직원 수를 보여줘"],
                    ["사업소별 정원(TO)과 현재 인원을 비교해줘"],
                    ["A권역(서울) 사업소 목록과 각 인원 수를 알려줘"],
                    ["팀별 평균 근무개월을 보여줘"],
                    ["조직 레벨별 사업소 수를 알려줘"],
                    # 배치 결과
                    ["이동이 확정된 직원의 이름과 새 부서를 보여줘"],
                    ["필수이동 대상 직원 목록을 알려줘"],
                    ["잔류 확정된 직원 수를 부서별로 보여줘"],
                    ["전출 인원이 가장 많은 사업소 TOP 5"],
                    ["전입 인원이 0인 사업소 목록을 보여줘"],
                    # 제약조건 & 감점
                    ["사용 중인 제약조건 목록을 보여줘"],
                    ["위반 건수가 가장 많은 제약조건 TOP 10"],
                    ["부부 동시배치 불가 직원 목록을 알려줘"],
                    ["총 감점이 높은 사업소 TOP 10을 보여줘"],
                    # 이동기준 & 케이스
                    ["전체 이동기준(이동번호) 목록을 보여줘"],
                    ["최근 이동번호의 케이스 목록을 알려줘"],
                    ["확정된 케이스의 리비전 목록을 보여줘"],
                    # 비교 분석
                    ["직무전환(job_type 변경) 직원 목록을 보여줘"],
                    ["기혼 여성 직원의 권역별 분포를 알려줘"],
                    ["자기신청이동 직원의 이동 결과를 보여줘"],
                    ["5년 이상 근무자의 직급별 분포를 알려줘"],
                    # 기타 (유보, 매핑, 변경)
                    ["필수유보 기준 목록과 유보 개월을 보여줘"],
                    ["직무 호환성 매트릭스를 보여줘"],
                    ["조직 변경(개편) 이력을 알려줘"],
                    ["ML 직무분류 매핑 사전을 보여줘"],
                    ["발령 메일이 발송된 직원 목록을 보여줘"],
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

            # Row 2: Move ID + Question input + Generate button (single line)
            _move_choices = _get_move_std_choices()
            with gr.Row(equal_height=True):
                move_std_dropdown = gr.Dropdown(
                    show_label=False,
                    choices=_move_choices,
                    value=_move_choices[0][1] if _move_choices else "0",
                    scale=1,
                    min_width=160,
                    container=False,
                )
                question_input.render()
                generate_btn = gr.Button(
                    "SQL 생성",
                    variant="primary",
                    scale=1,
                    min_width=120,
                    elem_classes=["primary-btn"],
                )

            # 이동번호 통계 (auto-update on dropdown change)
            move_std_stats = gr.HTML(value=_get_move_std_stats(_move_choices[0][1] if _move_choices else "0"))

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


        # ===== 탭 4: 제약조건 분석 =====
        with gr.Tab("제약조건 분석"):
            gr.HTML("""
            <div style="background:linear-gradient(135deg,#667eea10,#764ba220);
                        border-left:4px solid #667eea;border-radius:0 10px 10px 0;
                        padding:10px 16px;margin-bottom:16px;font-size:13px;color:#374151;">
                선택한 이동번호의 제약조건 설정 현황, 감점 순위, 사업소별 위반 현황을 분석합니다.
            </div>
            """)
            with gr.Row(equal_height=True):
                cnst_move_dropdown = gr.Dropdown(
                    show_label=False,
                    choices=_move_choices,
                    value=_move_choices[0][1] if _move_choices else "0",
                    scale=2, min_width=200, container=False,
                )
                cnst_analyze_btn = gr.Button("분석 실행", variant="primary", scale=0, min_width=120)
            gr.Markdown("**제약조건 요약**")
            cnst_summary_output = gr.HTML(value="")
            with gr.Row():
                with gr.Column(scale=1):
                    gr.Markdown("**감점 TOP 20**")
                    cnst_penalty_output = gr.HTML(value="")
                with gr.Column(scale=1):
                    gr.Markdown("**사업소별 위반 현황**")
                    cnst_org_output = gr.HTML(value="")


        # ===== 탭 5: 배치 결과 리포트 =====
        with gr.Tab("배치 결과 리포트"):
            gr.HTML("""
            <div style="background:linear-gradient(135deg,#10b98110,#3b82f620);
                        border-left:4px solid #10b981;border-radius:0 10px 10px 0;
                        padding:10px 16px;margin-bottom:16px;font-size:13px;color:#374151;">
                선택한 이동번호의 배치 최적화 결과를 종합적으로 분석합니다. 총 대상자, 권역별/직무별 이동현황, 감점 분석, LLM 요약을 제공합니다.
            </div>
            """)
            with gr.Row(equal_height=True):
                rpt_move_dropdown = gr.Dropdown(
                    show_label=False,
                    choices=_move_choices,
                    value=_move_choices[0][1] if _move_choices else "0",
                    scale=2, min_width=200, container=False,
                )
                rpt_generate_btn = gr.Button("리포트 생성", variant="primary", scale=0, min_width=120)
            gr.Markdown("**배치 요약**")
            rpt_summary_output = gr.HTML(value="")
            with gr.Row():
                with gr.Column(scale=1):
                    gr.Markdown("**권역별 이동현황**")
                    rpt_region_output = gr.HTML(value="")
                with gr.Column(scale=1):
                    gr.Markdown("**직무별 배치현황**")
                    rpt_job_output = gr.HTML(value="")
            with gr.Row():
                with gr.Column(scale=1):
                    gr.Markdown("**필수이동/유보 처리현황**")
                    rpt_must_output = gr.HTML(value="")
                with gr.Column(scale=1):
                    gr.Markdown("**감점 TOP 10**")
                    rpt_penalty_output = gr.HTML(value="")
            gr.Markdown("**LLM 자연어 요약**")
            rpt_llm_output = gr.Markdown(value="")


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

    # 이동번호 변경 시 통계 자동 업데이트
    move_std_dropdown.change(
        fn=_get_move_std_stats,
        inputs=[move_std_dropdown],
        outputs=[move_std_stats],
    )

    # SQL 생성 (버튼 클릭)
    generate_btn.click(
        fn=process_generate,
        inputs=[question_input, model_dropdown, move_std_dropdown],
        outputs=[sql_output, status_output, reasoning_state],
        concurrency_limit=3,
    )

    # SQL 생성 (Enter 키 제출)
    question_input.submit(
        fn=process_generate,
        inputs=[question_input, model_dropdown, move_std_dropdown],
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

    # 제약조건 분석 실행
    cnst_analyze_btn.click(
        fn=_run_cnst_analysis,
        inputs=[cnst_move_dropdown],
        outputs=[cnst_summary_output, cnst_penalty_output, cnst_org_output],
        concurrency_limit=3,
    )

    # 배치 결과 리포트 생성
    rpt_generate_btn.click(
        fn=_run_batch_report,
        inputs=[rpt_move_dropdown],
        outputs=[rpt_summary_output, rpt_region_output, rpt_job_output, rpt_must_output, rpt_penalty_output, rpt_llm_output],
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
        theme=gr.themes.Soft(),
        css=custom_css,
        js=custom_js,
        head=custom_head,
    )
