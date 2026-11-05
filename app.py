# app.py
"""
[5단계] Streamlit 기반 RBAC 권한 제어 UI 컨트롤러
"""
import streamlit as st
import pandas as pd
import datetime
import calendar
import traceback
import os
import io
from typing import Dict, Any, List, Tuple
# import local modules
import config
import db_manager
import calc_engine
import validator
import excel_io

# 다이얼로그 상태 및 라이프사이클 동기화 콜백
def set_dialog_rerun_callback():
    st.session_state.is_dialog_rerun = True

if "dialog_open" not in st.session_state:
    st.session_state.dialog_open = False

if st.session_state.dialog_open:
    # 다이얼로그 내부 조작 리런이 아닌 경우(외부 클릭 후 부모 위젯 작동 등) 닫기 상태로 동기화
    if not st.session_state.get("is_dialog_rerun", False):
        st.session_state.dialog_open = False
    else:
        st.session_state.is_dialog_rerun = False
# Page configuration
st.set_page_config(
    page_title="대선이엔씨 - 노무 관리 시스템",
    layout="wide",
    initial_sidebar_state="expanded"
)
# Custom premium styling CSS
st.markdown("""
    <style>
    .main {
        background-color: #121820;
        color: #ECF0F1;
    }
    div[data-testid="stSidebar"] {
        background-color: #1A252F;
    }
    .stButton>button {
        background-color: #3498DB;
        color: white;
        border-radius: 6px;
        border: none;
        font-weight: bold;
        transition: all 0.3s;
    }
    .stButton>button:hover {
        background-color: #2980B9;
        transform: translateY(-2px);
    }
    div.stAlert {
        border-radius: 8px;
    }
    h1, h2, h3 {
        color: #ECF0F1;
        font-family: '맑은 고딕', sans-serif;
    }
    </style>
""", unsafe_allow_html=True)
# Initialize Session States
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user_id" not in st.session_state:
    st.session_state.user_id = ""
if "user_role" not in st.session_state:
    st.session_state.user_role = "" # 관리자, 현장관리자, 조회전용
if "selected_ym" not in st.session_state:
    st.session_state.selected_ym = datetime.date.today().strftime("%Y-%m")
if "grid_unsaved" not in st.session_state:
    st.session_state.grid_unsaved = False
# --- AUTHENTICATION ---
def show_login_screen():
    st.markdown("<h1 style='text-align: center;'>🏗️ 대선이엔씨 노무 관리 시스템</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #BDC3C7;'>대선이엔씨 노무 관리 시스템</p>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            st.subheader("🔑 마스터 로그인")
            admin_pwd = db_manager.get_system_setting("admin_password", "")
            if admin_pwd == "":
                st.info("💡 설정된 비밀번호가 없습니다. [로그인 실행]을 바로 클릭하십시오.")
            password = st.text_input("마스터 비밀번호", type="password")
            submit = st.form_submit_button("로그인 실행")
            if submit:
                if admin_pwd == "" or password == admin_pwd:
                    st.session_state.logged_in = True
                    st.session_state.user_id = "정성우 대리"
                    st.session_state.user_role = "정성우 대리"
                    db_manager.log_login("정성우 대리", "local_client", "로그인 성공 (정성우 대리)")
                    st.rerun()
                else:
                    db_manager.log_login("Unknown", "local_client", "로그인 실패")
                    st.error("비밀번호가 올바르지 않습니다.")
if not st.session_state.logged_in:
    show_login_screen()
    st.stop()
# --- SIDEBAR CONTROL PANEL ---
with st.sidebar:
    st.markdown(f"### 👤 {st.session_state.user_id} 님")
    st.info(f"권한: **{st.session_state.user_role}**")
    st.markdown("---")
    st.subheader("📅 조회 연월 선택")
    # 최근 12개월 연월 옵션 생성
    today = datetime.date.today()
    ym_options = []
    for i in range(12):
        d = today - datetime.timedelta(days=i*30)
        ym_str = d.strftime("%Y-%m")
        if ym_str not in ym_options:
            ym_options.append(ym_str)
    st.session_state.selected_ym = st.selectbox(
        "대상 연월",
        ym_options,
        index=ym_options.index(st.session_state.selected_ym) if st.session_state.selected_ym in ym_options else 0
    )
    # 마감 상태 표시
    is_locked = db_manager.is_month_locked(st.session_state.selected_ym)
    if is_locked:
        st.error("🔒 **해당 월 마감 잠금 상태**")
    else:
        st.success("🔓 **편집 가능 상태**")
    st.markdown("---")
    # 로그아웃
    if st.button("🚪 로그아웃", use_container_width=True):
        st.session_state.logged_in = False
        st.session_state.user_id = ""
        st.session_state.user_role = ""
        st.rerun()
# --- MAIN TABS ---
st.title(f"📊 노무 관리 시스템 ({st.session_state.selected_ym})")

# 실시간 이상 데이터 검증 알림판
try:
    anomalies = validator.audit_monthly_data(st.session_state.selected_ym)
    total_anomalies = sum(len(v) for v in anomalies.values())
    if total_anomalies > 0:
        st.warning(f"⚠️ **{st.session_state.selected_ym}월 입력 데이터에 {total_anomalies}건의 정합성 경고(이상 징후)가 감지되었습니다. 정산을 제출하기 전에 꼭 검토해 주세요.**")
        with st.expander("🔍 실시간 이상 데이터 검증 상세 리포트 보기"):
            col_a1, col_a2 = st.columns(2)
            with col_a1:
                st.markdown(f"**유형 A: 연장공수 단독 입력 오류 (일반공수 0인데 연장 발생) - {len(anomalies['omitted_attendance'])}건**")
                if anomalies["omitted_attendance"]:
                    df_omitted = pd.DataFrame(anomalies["omitted_attendance"])
                    st.dataframe(df_omitted.rename(columns={"date": "날짜", "worker_id": "주민번호", "name": "성명", "normal_weight": "일반공수", "overtime_weight": "연장공수"}), use_container_width=True, hide_index=True)
                
                st.markdown(f"**유형 B: 공수 초과 (일반+연장 > {config.MAX_DAILY_TOTAL_HOURS}시간) - {len(anomalies['excessive_hours'])}건**")
                if anomalies["excessive_hours"]:
                    df_excessive = pd.DataFrame(anomalies["excessive_hours"])
                    st.dataframe(df_excessive.rename(columns={"date": "날짜", "worker_id": "주민번호", "name": "성명", "normal_weight": "일반", "overtime_weight": "연장"}), use_container_width=True, hide_index=True)
            with col_a2:
                st.markdown(f"**유형 C: 퇴사자 입력 오류 (퇴사일 이후 공수 발생) - {len(anomalies['resigned_attendance'])}건**")
                if anomalies["resigned_attendance"]:
                    df_resigned = pd.DataFrame(anomalies["resigned_attendance"])
                    st.dataframe(df_resigned.rename(columns={"date": "날짜", "worker_id": "주민번호", "name": "성명", "resignation_date": "퇴사일", "normal_weight": "일반", "overtime_weight": "연장"}), use_container_width=True, hide_index=True)
                
                st.markdown(f"**유형 D: 엑셀 파일 매칭 실패 이력 - {len(anomalies['excel_match_failures'])}건**")
                if anomalies["excel_match_failures"]:
                    df_failures = pd.DataFrame(anomalies["excel_match_failures"])
                    st.dataframe(df_failures.rename(columns={"date": "날짜", "raw_worker_id": "입력주민번호", "raw_name": "입력성명", "failure_reason": "실패사유"}), use_container_width=True, hide_index=True)
except Exception as val_err:
    pass

tab_grid, tab_upload, tab_workers, tab_history, tab_backups, tab_settings, tab_help = st.tabs([
    "📅 월간 공수 현황 및 편집", 
    "📥 일일 출역일보 업로드", 
    "👤 근로자 관리 및 일괄등록", 
    "🔍 변경 이력 (감사 로그)",
    "🗄️ 데이터 백업 및 복원",
    "⚙️ 마감 및 시스템 설정",
    "❓ 도움말 및 시스템 구조"
])
# 1. 캐시화된 월간 공수 그리드 로드 함수
@st.cache_data
def get_attendance_grid(year_month: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[str], List[str], Dict[str, Any], List[Dict[str, str]]]:
    """특정 연월의 공수 피벗 테이블과 버전 딕셔너리, 커스텀 수당 리스트를 반환합니다."""
    ym_db = year_month.replace("-", "")
    conn = db_manager.get_db_connection()
    cursor = conn.cursor()
    # 근로자 목록
    cursor.execute("SELECT worker_id, name, team, trade, resignation_date FROM workers ORDER BY name ASC;")
    workers = [dict(r) for r in cursor.fetchall()]
    # 출역 정보 (한/일 일치화 하도록 한 번에 조회)
    cursor.execute("""
        SELECT date, worker_id, normal_weight, overtime_weight, prev_month_missing, deduction, lodging_weight, health_weight, leader_weight,
               weekly_holiday, monthly_holiday, status, version
        FROM daily_attendance
        WHERE substr(date, 1, 6) = ?;
    """, (ym_db,))
    attendance = [dict(r) for r in cursor.fetchall()]
    # 커스텀 수당 리스트 및 일일 기록 조회
    custom_allowances = db_manager.get_custom_weight_types(conn=conn)
    custom_attendance = db_manager.get_daily_custom_attendance(year_month, conn=conn)
    conn.close()
    # 연월의 날짜 목록
    dates = calc_engine.get_days_in_month(year_month)
    days = [f"{int(d[6:8])}일" for d in dates]
    # 출역 버전 캐싱
    versions = {}
    for r in attendance:
        key = f"{r['date']}_{r['worker_id']}"
        versions[key] = {
            "version": r["version"],
            "normal_weight": r["normal_weight"],
            "overtime_weight": r["overtime_weight"],
            "prev_month_missing": r["prev_month_missing"],
            "deduction": r["deduction"],
            "lodging_weight": r["lodging_weight"],
            "health_weight": r["health_weight"],
            "leader_weight": r["leader_weight"],
            "weekly_holiday": r["weekly_holiday"],
            "monthly_holiday": r["monthly_holiday"],
            "status": r["status"]
        }
        # 커스텀 수당 초기화
        for cat in custom_allowances:
            versions[key]["custom_" + cat["type_id"]] = 0.0
    # 커스텀 수당 실제값 덮어쓰기
    for r in custom_attendance:
        key = f"{r['date']}_{r['worker_id']}"
        if key in versions:
            versions[key]["custom_" + r["type_id"]] = r["weight"]
    return workers, attendance, dates, days, versions, custom_allowances
@st.dialog("공수 편집창 (전체 근로자)", width="large")
def show_edit_dialog(ym, workers, dates, styled_days, versions, custom_allowances, hide_allowances, default_edit_dim):
    st.subheader("📝 전체 근로자 공수 편집")
    st.write("모든 근로자의 공수 및 수당을 한 화면에서 빠르게 입력하고 수정할 수 있습니다.")
    
    # 1. 차원 선택
    choices = ["일반공수", "출역구분", "연장공수", "전월 누락공수", "차감공수", "주차수당", "월차수당", "숙소수당", "보건수당", "팀장수당"] + [f"{cat['display_name']}수당" for cat in custom_allowances]
    initial_idx = choices.index(default_edit_dim) if default_edit_dim in choices else 0
    edit_dim = st.radio(
        "📍 편집할 공수 차원 선택",
        choices,
        index=initial_idx,
        horizontal=True,
        key="dialog_edit_dim",
        on_change=set_dialog_rerun_callback
    )
    dim_key_map = {
        "일반공수": "normal_weight",
        "출역구분": "status",
        "연장공수": "overtime_weight",
        "전월 누락공수": "prev_month_missing",
        "차감공수": "deduction",
        "주차수당": "weekly_holiday",
        "월차수당": "monthly_holiday",
        "숙소수당": "lodging_weight",
        "보건수당": "health_weight",
        "팀장수당": "leader_weight"
    }
    for cat in custom_allowances:
        dim_key_map[f"{cat['display_name']}수당"] = f"custom_{cat['type_id']}"
    dim_key = dim_key_map.get(edit_dim)
    
    # 에디터 상태 버전 관리를 통한 저장 후 세션 동기화
    editor_rev = st.session_state.get("editor_rev", 0)
    editor_key = f"dialog_editor_{ym}_{edit_dim}_{editor_rev}"

    # 2. 데이터 그리드 빌드 (전체 근로자 대상)
    grid_data = []
    for w in workers:
        r_date_raw = w.get("resignation_date")
        if r_date_raw:
            r_clean = str(r_date_raw).replace("-", "").replace("/", "").strip()
            if len(r_clean) >= 8:
                status_disp = f"🔴 퇴사 ({r_clean[4:6]}/{r_clean[6:8]})"
            else:
                status_disp = f"🔴 퇴사 ({r_date_raw})"
        else:
            status_disp = "재직"
        row = {
            "주민번호": w["worker_id"],
            "성명": w["name"],
            "상태": status_disp,
            "소속팀": w["team"] or "",
            "직종": w["trade"] or ""
        }
        tot_normal = 0.0
        tot_overtime = 0.0
        tot_prev_missing = 0.0
        tot_deduction = 0.0
        tot_weekly = 0.0
        tot_monthly = 0.0
        tot_lodging = 0.0
        tot_health = 0.0
        tot_leader = 0.0
        tot_custom = 0.0
        for d_idx, d_str in enumerate(dates):
            key = f"{d_str}_{w['worker_id']}"
            day_col = styled_days[d_idx]
            normal_val = 0.0
            over_val = 0.0
            prev_missing_val = 0.0
            deduction_val = 0.0
            weekly_val = 0.0
            monthly_val = 0.0
            lodging_val = 0.0
            health_val = 0.0
            leader_val = 0.0
            custom_val = 0.0
            if key in versions:
                rec = versions[key]
                normal_val = rec.get("normal_weight", 0.0) or 0.0
                over_val = rec.get("overtime_weight", 0.0) or 0.0
                prev_missing_val = rec.get("prev_month_missing", 0.0) or 0.0
                deduction_val = rec.get("deduction", 0.0) or 0.0
                weekly_val = rec.get("weekly_holiday", 0.0) or 0.0
                monthly_val = rec.get("monthly_holiday", 0.0) or 0.0
                lodging_val = rec.get("lodging_weight", 0.0) or 0.0
                health_val = rec.get("health_weight", 0.0) or 0.0
                leader_val = rec.get("leader_weight", 0.0) or 0.0
                for cat in custom_allowances:
                    custom_val += float(rec.get("custom_" + cat["type_id"], 0.0))
            tot_normal += normal_val
            tot_overtime += over_val
            tot_prev_missing += prev_missing_val
            tot_deduction += deduction_val
            tot_weekly += weekly_val
            tot_monthly += monthly_val
            tot_lodging += lodging_val
            tot_health += health_val
            tot_leader += leader_val
            tot_custom += custom_val
            if edit_dim == "적용 수당 요약":
                allowance_tags = []
                if weekly_val > 0: allowance_tags.append("주차")
                if monthly_val > 0: allowance_tags.append("월차")
                if lodging_val > 0: allowance_tags.append("숙소")
                if health_val > 0: allowance_tags.append("보건")
                if leader_val > 0: allowance_tags.append("팀장")
                for cat in custom_allowances:
                    c_val = float(versions.get(key, {}).get("custom_" + cat["type_id"], 0.0) or 0.0)
                    if c_val > 0: allowance_tags.append(cat["display_name"])
                row[day_col] = ", ".join(allowance_tags) if allowance_tags else ""
            elif key in versions:
                val = versions[key].get(dim_key)
                if dim_key == "status":
                    row[day_col] = str(val) if (val and val != "휴무" and val != "None") else ""
                else:
                    row[day_col] = float(val) if val is not None else 0.0
            else:
                row[day_col] = "" if dim_key == "status" else 0.0
        row["출역"] = tot_normal
        row["연장"] = tot_overtime
        row["누락"] = tot_prev_missing
        row["차감"] = tot_deduction
        row["주차"] = tot_weekly
        row["월차"] = tot_monthly
        if not hide_allowances:
            row["숙소"] = tot_lodging
            row["보건"] = tot_health
            row["팀장"] = tot_leader
            row["기타"] = tot_custom
            row["총공수"] = tot_normal + tot_overtime + tot_prev_missing - tot_deduction + tot_weekly + tot_monthly + tot_lodging + tot_health + tot_leader + tot_custom
        else:
            row["총공수"] = tot_normal + tot_overtime + tot_prev_missing - tot_deduction + tot_weekly + tot_monthly
        grid_data.append(row)
    if grid_data:
        total_row = {
            "주민번호": "일일 합계",
            "성명": "",
            "소속팀": "",
            "직종": ""
        }
        for day_col in styled_days:
            if dim_key == "status":
                total_row[day_col] = ""
            else:
                total_row[day_col] = round(sum(float(r[day_col]) for r in grid_data if day_col in r and r[day_col] != ""), 2)
        total_row["출역"] = round(sum(float(r["출역"]) for r in grid_data if "출역" in r), 2)
        total_row["연장"] = round(sum(float(r["연장"]) for r in grid_data if "연장" in r), 2)
        total_row["누락"] = round(sum(float(r["누락"]) for r in grid_data if "누락" in r), 2)
        total_row["차감"] = round(sum(float(r["차감"]) for r in grid_data if "차감" in r), 2)
        total_row["주차"] = round(sum(float(r["주차"]) for r in grid_data if "주차" in r), 2)
        total_row["월차"] = round(sum(float(r["월차"]) for r in grid_data if "월차" in r), 2)
        if not hide_allowances:
            total_row["숙소"] = round(sum(float(r["숙소"]) for r in grid_data if "숙소" in r), 2)
            total_row["보건"] = round(sum(float(r["보건"]) for r in grid_data if "보건" in r), 2)
            total_row["팀장"] = round(sum(float(r["팀장"]) for r in grid_data if "팀장" in r), 2)
            total_row["기타"] = round(sum(float(r["기타"]) for r in grid_data if "기타" in r), 2)
        total_row["총공수"] = round(sum(float(r["총공수"]) for r in grid_data if "총공수" in r), 2)
        import copy
        grid_data.insert(0, copy.deepcopy(total_row))
        grid_data.append(copy.deepcopy(total_row))
    df_grid = pd.DataFrame(grid_data)

    # 3. 공수 대량 저장 공통 헬퍼 함수
    def save_changes():
        state = st.session_state.get(editor_key)
        if state and state.get("edited_rows"):
            edited_rows = state["edited_rows"]
            records_to_update = []
            conn = db_manager.get_db_connection()
            cursor = conn.cursor()
            try:
                for row_idx, changes in edited_rows.items():
                    row_orig = df_grid.iloc[int(row_idx)]
                    worker_id = row_orig["주민번호"]
                    if worker_id == "일일 합계":
                        continue
                    cursor.execute("SELECT has_lodging, has_health, is_team_leader FROM workers WHERE worker_id = ?;", (worker_id,))
                    worker_row = cursor.fetchone()
                    worker = dict(worker_row) if worker_row else {}
                    for col_name, new_val in changes.items():
                        if col_name not in styled_days:
                            continue
                        day_idx = styled_days.index(col_name)
                        date_str = dates[day_idx]
                        try:
                            if dim_key == "status":
                                new_weight = str(new_val)
                                if new_weight == "" or new_weight == "None":
                                    new_weight = "휴무"
                            else:
                                new_weight = float(new_val)
                                if dim_key in ["normal_weight", "overtime_weight"]:
                                    if new_weight < config.ALLOWED_MIN_WEIGHT or new_weight > config.ALLOWED_MAX_WEIGHT:
                                        raise ValueError(f"값 범위 제약(0.0 ~ 2.0)을 벗어났습니다. 입력값: {new_weight}")
                        except ValueError as val_err:
                            st.error(f"입력 오류: {col_name}의 값이 올바르지 않습니다. ({val_err})")
                            st.stop()
                        cursor.execute("""
                            SELECT * FROM daily_attendance
                            WHERE date = ? AND worker_id = ?;
                        """, (date_str, worker_id))
                        db_row = cursor.fetchone()
                        if dim_key.startswith("custom_"):
                            type_id = dim_key[7:]
                            if not db_row:
                                def_l = 1.0 if worker.get("has_lodging") == 1 else 0.0
                                def_h = 1.0 if worker.get("has_health") == 1 else 0.0
                                def_le = 1.0 if worker.get("is_team_leader") == 1 else 0.0
                                cursor.execute("""
                                    INSERT INTO daily_attendance (
                                        date, worker_id, normal_weight, overtime_weight, lodging_weight, 
                                        health_weight, leader_weight, weekly_holiday, monthly_holiday, status, version
                                    )
                                    VALUES (?, ?, 0.0, 0.0, ?, ?, ?, 0.0, 0.0, '출근', 1);
                                """, (date_str, worker_id, def_l, def_h, def_le))
                            db_manager.save_daily_custom_attendance(date_str, worker_id, type_id, new_weight, conn=conn)
                            db_manager.log_audit(
                                user_id=st.session_state.user_id,
                                worker_id=worker_id,
                                action=f"{date_str} 커스텀 수당({type_id}) 가중치 수정",
                                before_value="이전 상태",
                                after_value=f"가중치:{new_weight}",
                                conn=conn
                            )
                        else:
                            record = {
                                "date": date_str,
                                "worker_id": worker_id,
                                "normal_weight": 0.0,
                                "overtime_weight": 0.0,
                                "lodging_weight": 0.0,
                                "health_weight": 0.0,
                                "leader_weight": 0.0,
                                "weekly_holiday": 0.0,
                                "monthly_holiday": 0.0,
                                "is_weekly_manual": 0,
                                "is_monthly_manual": 0,
                                "prev_month_missing": 0.0,
                                "deduction": 0.0,
                                "status": "휴무",
                                "version": 1
                            }
                            if db_row:
                                record.update(dict(db_row))
                            record[dim_key] = new_weight
                            if dim_key == "weekly_holiday":
                                record["is_weekly_manual"] = 1
                            elif dim_key == "monthly_holiday":
                                record["is_monthly_manual"] = 1
                            if dim_key == "normal_weight":
                                if record["normal_weight"] > 0.0:
                                    record["status"] = "출근"
                                else:
                                    cur_status = record.get("status")
                                    if cur_status == "출근" or not cur_status or cur_status == "None":
                                        record["status"] = "휴무"
                            records_to_update.append(record)
                conn.commit()
                if records_to_update:
                    db_manager.save_attendance_bulk(records_to_update, st.session_state.user_id)
                get_attendance_grid.clear()
                # 세션 키 리셋 및 버전 업을 통한 중복 저장/동시성 에러 완전 방지
                if editor_key in st.session_state:
                    del st.session_state[editor_key]
                st.session_state["editor_rev"] = editor_rev + 1
                return True
            except Exception as e:
                st.error(f"저장 중 오류 발생: {e}")
                return False
            finally:
                conn.close()
        return None

    # 4. 다이얼로그 전용 제어 버튼 바 (상단 단일 배치 - 중복 버튼 제거)
    col_t1, col_t2, col_t3 = st.columns([1, 1, 1])
    with col_t1:
        if st.button("💾 변경사항 반영 (창 유지)", key="btn_apply_top", use_container_width=True):
            st.session_state.is_dialog_rerun = True
            st.session_state.dialog_open = True
            res = save_changes()
            if res is True:
                st.success("변경 사항이 성공적으로 저장되었습니다!")
                st.rerun()
            elif res is None:
                st.info("수정된 내역이 없습니다.")
    with col_t2:
        if st.button("💾 반영 후 닫기", key="btn_save_close_top", use_container_width=True, type="primary"):
            st.session_state.dialog_open = False
            st.session_state.is_dialog_rerun = False
            res = save_changes()
            if res is True or res is None:
                st.rerun()
    with col_t3:
        if st.button("❌ 반영하지 않고 닫기", key="btn_close_top", use_container_width=True):
            st.session_state.dialog_open = False
            st.session_state.is_dialog_rerun = False
            st.rerun()
            
    st.markdown("---")

    # 5. 그리드 데이터 에디터 바인딩
    disabled_cols = ["주민번호", "성명", "소속팀", "직종", "출역", "연장", "주차", "월차"]
    if not hide_allowances:
        disabled_cols += ["숙소", "보건", "팀장", "기타"]
    disabled_cols += ["총공수"]
    col_config = {
        "주민번호": st.column_config.TextColumn("주민번호", pinned=True),
        "성명": st.column_config.TextColumn("성명", pinned=True),
        "소속팀": st.column_config.TextColumn("소속팀", pinned=True),
        "직종": st.column_config.TextColumn("직종", pinned=True),
    }
    for day_col in styled_days:
        if dim_key == "status":
            col_config[day_col] = st.column_config.SelectboxColumn(
                day_col,
                options=["출근", "", "결근", "공가", "병가", "인정", "대휴", "경조", "휴가"]
            )
        else:
            col_config[day_col] = st.column_config.NumberColumn(day_col, format="%.2f")
    summary_num_cols = ["출역", "연장", "주차", "월차", "숙소", "보건", "팀장", "기타", "총공수"]
    for col in summary_num_cols:
        col_config[col] = st.column_config.NumberColumn(col, format="%.2f")

    edited_df = st.data_editor(
        df_grid,
        disabled=disabled_cols,
        column_config=col_config,
        key=editor_key,
        use_container_width=True,
        hide_index=True,
        on_change=set_dialog_rerun_callback
    )

def is_long_resigned_worker(resignation_date_str: str, active_ym: str) -> bool:
    """
    해당 월(active_ym, 예: '2026-08') 1일자 기준으로 
    퇴사일이 1달 이상(30일 이상) 지난 장기 퇴사자인지 판별합니다.
    """
    if not resignation_date_str:
        return False
    r_clean = str(resignation_date_str).replace("-", "").replace("/", "").strip()
    if len(r_clean) < 8:
        return False
    try:
        r_dt = datetime.date(int(r_clean[:4]), int(r_clean[4:6]), int(r_clean[6:8]))
        ym_clean = active_ym.replace("-", "")
        first_day_of_active_month = datetime.date(int(ym_clean[:4]), int(ym_clean[4:6]), 1)
        return (first_day_of_active_month - r_dt).days >= 30
    except Exception:
        return False


# ----------------- Tab 1: 월간 공수 현황 및 편집 -----------------
with tab_grid:
    st.subheader("📅 월간 공수 판넬")
    # 1. 조회 정보 로드
    workers, attendance, dates, days, versions, custom_allowances = get_attendance_grid(st.session_state.selected_ym)
    if not workers:
        st.warning("등록된 근로자가 없습니다. '근로자 관리 및 일괄등록' 탭에서 근로자를 먼저 등록해 주세요.")
    else:
        # 해당월 1일자 기준 1달 이상 지나 공수입력에서 제외할 장기 퇴사자 분리
        long_resigned_workers = [w for w in workers if is_long_resigned_worker(w.get("resignation_date"), st.session_state.selected_ym)]
        active_entry_workers = [w for w in workers if not is_long_resigned_worker(w.get("resignation_date"), st.session_state.selected_ym)]
        
        # 기본적으로 장기 퇴사자는 공수입력 표에서 제외
        display_workers = active_entry_workers
        
        # 필터링 및 편집 창 열기 설정
        col_f1, col_f2, col_f3, col_f4 = st.columns([1, 1, 1.2, 1])
        # 1-1. 팀 필터
        teams = sorted(list(set([w["team"] for w in display_workers if w["team"]])))
        with col_f1:
            sel_team = st.selectbox("팀 필터 (전체는 공란)", ["전체"] + teams)
        # 1-2. 직종 필터
        trades = sorted(list(set([w["trade"] for w in display_workers if w["trade"]])))
        with col_f2:
            sel_trade = st.selectbox("직종 필터 (전체는 공란)", ["전체"] + trades)
        # 1-3. 편집창 오픈 버튼 배치
        with col_f3:
            open_edit = st.button("✏️ 전체 근로자 공수 편집창 열기", type="primary", use_container_width=True, disabled=is_locked)
        # 1-4. 최신 데이터 동기화/새로고침 버튼 배치
        with col_f4:
            if st.button("🔄 최신 데이터 새로고침", use_container_width=True, help="데이터베이스의 최신 공수 내역을 다시 불러옵니다."):
                get_attendance_grid.clear()
                st.toast("🔄 최신 공수 데이터를 성공적으로 다시 불러왔습니다!")
                st.rerun()
        # 필터링 적용
        filtered_workers = display_workers
        if sel_team != "전체":
            filtered_workers = [w for w in filtered_workers if w["team"] == sel_team]
        if sel_trade != "전체":
            filtered_workers = [w for w in filtered_workers if w["trade"] == sel_trade]
        # 2. 편집 차원 선택 및 숨김 체크박스 레이아웃
        choices = ["총 공수", "일반공수", "출역구분", "적용 수당 요약", "연장공수", "전월 누락공수", "차감공수", "주차수당", "월차수당", "숙소수당", "보건수당", "팀장수당"] + [f"{cat['display_name']}수당" for cat in custom_allowances]
        col_c1, col_c2 = st.columns([3, 1])
        with col_c1:
            edit_dim = st.radio("📍 메인 공수 표 칼럼 표시 모드", choices, horizontal=True, key="main_grid_edit_dim")
        with col_c2:
            hide_allowances = st.checkbox("🙈 숙소/보건/팀장/기타 수당 숨기기", value=False)
        dim_key_map = {
            "일반공수": "normal_weight",
            "출역구분": "status",
            "연장공수": "overtime_weight",
            "전월 누락공수": "prev_month_missing",
            "차감공수": "deduction",
            "주차수당": "weekly_holiday",
            "월차수당": "monthly_holiday",
            "숙소수당": "lodging_weight",
            "보건수당": "health_weight",
            "팀장수당": "leader_weight"
        }
        for cat in custom_allowances:
            dim_key_map[f"{cat['display_name']}수당"] = f"custom_{cat['type_id']}"
        dim_key = dim_key_map.get(edit_dim, "normal_weight")
        korean_weekdays = ["월", "화", "수", "목", "금", "토", "일"]
        styled_days = []
        for d in dates:
            day_num = int(d[6:8])
            dt = datetime.date(int(d[:4]), int(d[4:6]), day_num)
            w_str = korean_weekdays[dt.weekday()]
            styled_days.append(f"{day_num}일({w_str})")
        holiday_dates = set(db_manager.get_holidays(st.session_state.selected_ym))

        # 편집 모달 열기 요청 처리
        if open_edit:
            st.session_state.dialog_open = True
            st.session_state.is_dialog_rerun = True
            
        if st.session_state.get("dialog_open", False):
            show_edit_dialog(
                ym=st.session_state.selected_ym,
                workers=filtered_workers,
                dates=dates,
                styled_days=styled_days,
                versions=versions,
                custom_allowances=custom_allowances,
                hide_allowances=hide_allowances,
                default_edit_dim=st.session_state.get("dialog_edit_dim", edit_dim)
            )

        # 3. 데이터 그리드 빌드 (전체 대상)
        grid_data = []
        for w in filtered_workers:
            row = {
                "주민번호": w["worker_id"],
                "성명": w["name"],
                "소속팀": w["team"] or "",
                "직종": w["trade"] or ""
            }
            tot_normal = 0.0
            tot_overtime = 0.0
            tot_prev_missing = 0.0
            tot_deduction = 0.0
            tot_weekly = 0.0
            tot_monthly = 0.0
            tot_lodging = 0.0
            tot_health = 0.0
            tot_leader = 0.0
            tot_custom = 0.0
            # 각 일자별 데이터 추가 및 합산
            for d_idx, d_str in enumerate(dates):
                key = f"{d_str}_{w['worker_id']}"
                day_col = styled_days[d_idx]
                normal_val = 0.0
                over_val = 0.0
                prev_missing_val = 0.0
                deduction_val = 0.0
                weekly_val = 0.0
                monthly_val = 0.0
                lodging_val = 0.0
                health_val = 0.0
                leader_val = 0.0
                custom_val = 0.0
                if key in versions:
                    rec = versions[key]
                    normal_val = rec.get("normal_weight", 0.0) or 0.0
                    over_val = rec.get("overtime_weight", 0.0) or 0.0
                    prev_missing_val = rec.get("prev_month_missing", 0.0) or 0.0
                    deduction_val = rec.get("deduction", 0.0) or 0.0
                    weekly_val = rec.get("weekly_holiday", 0.0) or 0.0
                    monthly_val = rec.get("monthly_holiday", 0.0) or 0.0
                    lodging_val = rec.get("lodging_weight", 0.0) or 0.0
                    health_val = rec.get("health_weight", 0.0) or 0.0
                    leader_val = rec.get("leader_weight", 0.0) or 0.0
                    for cat in custom_allowances:
                        custom_val += float(rec.get("custom_" + cat["type_id"], 0.0))
                tot_normal += normal_val
                tot_overtime += over_val
                tot_prev_missing += prev_missing_val
                tot_deduction += deduction_val
                tot_weekly += weekly_val
                tot_monthly += monthly_val
                tot_lodging += lodging_val
                tot_health += health_val
                tot_leader += leader_val
                tot_custom += custom_val
                if edit_dim == "총 공수":
                    if not hide_allowances:
                        row[day_col] = normal_val + over_val + prev_missing_val - deduction_val + weekly_val + monthly_val + lodging_val + health_val + leader_val + custom_val
                    else:
                        row[day_col] = normal_val + over_val + prev_missing_val - deduction_val + weekly_val + monthly_val
                elif edit_dim == "적용 수당 요약":
                    allowance_tags = []
                    if weekly_val > 0: allowance_tags.append("주차")
                    if monthly_val > 0: allowance_tags.append("월차")
                    if lodging_val > 0: allowance_tags.append("숙소")
                    if health_val > 0: allowance_tags.append("보건")
                    if leader_val > 0: allowance_tags.append("팀장")
                    for cat in custom_allowances:
                        c_val = float(versions.get(key, {}).get("custom_" + cat["type_id"], 0.0) or 0.0)
                        if c_val > 0: allowance_tags.append(cat["display_name"])
                    row[day_col] = ", ".join(allowance_tags) if allowance_tags else ""
                else:
                    if key in versions:
                        val = versions[key].get(dim_key)
                        if dim_key == "status":
                            row[day_col] = str(val) if (val and val != "휴무" and val != "None") else ""
                        else:
                            row[day_col] = float(val) if val is not None else 0.0
                    else:
                        row[day_col] = "" if dim_key == "status" else 0.0
            # 우측 합산 열 기입
            row["출역"] = tot_normal
            row["연장"] = tot_overtime
            row["누락"] = tot_prev_missing
            row["차감"] = tot_deduction
            row["주차"] = tot_weekly
            row["월차"] = tot_monthly
            if not hide_allowances:
                row["숙소"] = tot_lodging
                row["보건"] = tot_health
                row["팀장"] = tot_leader
                row["기타"] = tot_custom
                row["총공수"] = tot_normal + tot_overtime + tot_prev_missing - tot_deduction + tot_weekly + tot_monthly + tot_lodging + tot_health + tot_leader + tot_custom
            else:
                row["총공수"] = tot_normal + tot_overtime + tot_prev_missing - tot_deduction + tot_weekly + tot_monthly
            grid_data.append(row)
        # 일일 합계 행 계산 및 추가
        if grid_data:
            total_row = {
                "주민번호": "일일 합계",
                "성명": "",
                "상태": "",
                "소속팀": "",
                "직종": ""
            }
            for day_col in styled_days:
                if dim_key == "status":
                    total_row[day_col] = ""
                else:
                    total_row[day_col] = round(sum(float(r[day_col]) for r in grid_data if day_col in r and r[day_col] != ""), 2)
            total_row["출역"] = round(sum(float(r["출역"]) for r in grid_data if "출역" in r), 2)
            total_row["연장"] = round(sum(float(r["연장"]) for r in grid_data if "연장" in r), 2)
            total_row["누락"] = round(sum(float(r["누락"]) for r in grid_data if "누락" in r), 2)
            total_row["차감"] = round(sum(float(r["차감"]) for r in grid_data if "차감" in r), 2)
            total_row["주차"] = round(sum(float(r["주차"]) for r in grid_data if "주차" in r), 2)
            total_row["월차"] = round(sum(float(r["월차"]) for r in grid_data if "월차" in r), 2)
            if not hide_allowances:
                total_row["숙소"] = round(sum(float(r["숙소"]) for r in grid_data if "숙소" in r), 2)
                total_row["보건"] = round(sum(float(r["보건"]) for r in grid_data if "보건" in r), 2)
                total_row["팀장"] = round(sum(float(r["팀장"]) for r in grid_data if "팀장" in r), 2)
                total_row["기타"] = round(sum(float(r["기타"]) for r in grid_data if "기타" in r), 2)
            total_row["총공수"] = round(sum(float(r["총공수"]) for r in grid_data if "총공수" in r), 2)
            import copy
            grid_data.insert(0, copy.deepcopy(total_row))
            grid_data.append(copy.deepcopy(total_row))
        df_grid = pd.DataFrame(grid_data)
        # 4. Streamlit data_editor를 통한 고속 편집 렌더링 (메인은 항상 조회 전용)
        is_grid_disabled = True
        if edit_dim == "총 공수":
            st.write("✏️ 현재 표시 모드: **총 공수** (수정 불가능한 보기 전용 화면입니다)")
        else:
            st.write(f"✏️ 현재 표시 모드: **{edit_dim}** (조회 전용 화면이며 우측 상단 '편집창 열기'를 눌러 수정 가능합니다)")
        editor_key = f"view_{st.session_state.selected_ym}_{edit_dim}"
        # 토요일은 파란 글자, 일요일 및 공휴일은 빨간 글자로 표시하는 Pandas Styler 정의
        def style_weekend(df):
            style_df = pd.DataFrame('', index=df.index, columns=df.columns)
            for d_idx, d_str in enumerate(dates):
                day_col = styled_days[d_idx]
                day_num = int(d_str[6:8])
                dt = datetime.date(int(d_str[:4]), int(d_str[4:6]), day_num)
                weekday = dt.weekday()
                if d_str in holiday_dates or weekday == 6:
                    style_df[day_col] = 'color: #C00000; font-weight: bold;'
                elif weekday == 5:
                    style_df[day_col] = 'color: #1F497D; font-weight: bold;'
            # 퇴사자 행 붉은빛 전면 배경 강조 및 일일 합계 행 다크 배경 처리
            for idx in df.index:
                st_val = str(df.loc[idx, "상태"]) if "상태" in df.columns else ""
                if "퇴사" in st_val:
                    for col in df.columns:
                        style_df.loc[idx, col] = 'color: #FFD1D1; font-weight: bold; background-color: #5C1D1D;'
                if df.loc[idx, "주민번호"] == "일일 합계":
                    for col in df.columns:
                        existing_style = style_df.loc[idx, col]
                        if 'color: #C00000' in existing_style:
                            style_df.loc[idx, col] = 'color: #F87171; font-weight: bold; background-color: #1E293B; font-size: 13px;'
                        elif 'color: #1F497D' in existing_style:
                            style_df.loc[idx, col] = 'color: #60A5FA; font-weight: bold; background-color: #1E293B; font-size: 13px;'
                        else:
                            style_df.loc[idx, col] = 'color: #F8FAFC; font-weight: bold; background-color: #1E293B; font-size: 13px;'
            return style_df
        styled_df = df_grid.style.apply(style_weekend, axis=None)
        # 틀고정(pinned=True) 및 소수점 둘째자리(format="%.2f") 지정 설정 컬럼 빌드
        col_config = {
            "주민번호": st.column_config.TextColumn("주민번호", pinned=True),
            "성명": st.column_config.TextColumn("성명", pinned=True),
            "상태": st.column_config.TextColumn("재직상태", pinned=True),
            "소속팀": st.column_config.TextColumn("소속팀", pinned=True),
            "직종": st.column_config.TextColumn("직종", pinned=True),
        }
        # 일자별 컬럼 소수점 2자리 지정
        for day_col in styled_days:
            if edit_dim in ["출역구분", "적용 수당 요약"]:
                col_config[day_col] = st.column_config.TextColumn(day_col)
            else:
                col_config[day_col] = st.column_config.NumberColumn(day_col, format="%.2f")
        # 우측 합산 요약 컬럼 소수점 2자리 지정
        summary_num_cols = ["출역", "연장", "누락", "차감", "주차", "월차", "숙소", "보건", "팀장", "기타", "총공수"]
        for col in summary_num_cols:
            col_config[col] = st.column_config.NumberColumn(col, format="%.2f")
        # 메인 그리드는 모든 열 비활성화 (조회 전용)
        disabled_cols = list(df_grid.columns)
        st.dataframe(
            styled_df,
            column_config=col_config,
            use_container_width=True,
            hide_index=True
        )
        st.markdown("---")
        # 4-2. 특정 날짜 데이터 일괄 삭제 (초기화) 영역
        with st.expander("🗑️ 특정 날짜 출역/공수 및 특정 수당 선택 삭제 (초기화)", expanded=False):
            st.write("잘못 입력되거나 업로드된 **특정 날짜(하루)의 전체 데이터** 또는 **특정 수당/공수 항목만 골라서 삭제(0으로 초기화)**할 수 있습니다.")
            del_date_opt_map = {}
            for d_idx, d_str in enumerate(dates):
                day_label = f"{d_str[:4]}-{d_str[4:6]}-{d_str[6:8]} ({styled_days[d_idx]})"
                cnt_on_day = sum(1 for w in workers if f"{d_str}_{w['worker_id']}" in versions)
                label_with_cnt = f"{day_label} — [입력 데이터: {cnt_on_day}명]" if cnt_on_day > 0 else f"{day_label} — [데이터 없음]"
                del_date_opt_map[label_with_cnt] = d_str

            col_dd1, col_dd2 = st.columns([1.5, 1])
            with col_dd1:
                sel_del_date_label = st.selectbox(
                    "📅 삭제할 날짜 선택",
                    options=list(del_date_opt_map.keys()),
                    key=f"tab1_del_date_select_{st.session_state.selected_ym}"
                )
                target_del_date_str = del_date_opt_map[sel_del_date_label]
            with col_dd2:
                all_teams_for_del = sorted(list(set([w["team"] for w in workers if w.get("team")])))
                sel_del_date_team = st.selectbox(
                    "🎯 삭제 대상 팀 선택 (전체는 모든 근로자)",
                    options=["전체"] + all_teams_for_del,
                    key=f"tab1_del_date_team_{st.session_state.selected_ym}"
                )

            date_summary = db_manager.get_date_attendance_summary(target_del_date_str, team=sel_del_date_team)
            att_cnt = date_summary["attendance_count"]
            cust_cnt = date_summary["custom_count"]
            fmt_target_date = f"{target_del_date_str[:4]}-{target_del_date_str[4:6]}-{target_del_date_str[6:8]}"

            if att_cnt == 0 and cust_cnt == 0:
                st.info(f"💡 선택한 날짜(**{fmt_target_date}**, 대상: **{sel_del_date_team}**)에는 저장된 출역/공수 데이터가 없습니다.")
            else:
                del_mode_t1 = st.radio(
                    "🛠️ 삭제 방식 선택",
                    [
                        "1. 전체 삭제 (해당 날짜의 출역·공수·모든 수당 전체 초기화)",
                        "2. 특정 수당/공수 항목만 선택하여 삭제 (선택한 수당만 0으로 초기화)"
                    ],
                    horizontal=True,
                    key=f"tab1_del_mode_{target_del_date_str}_{sel_del_date_team}"
                )
                is_selective_t1 = del_mode_t1.startswith("2.")

                # 항목별 현재 입력된 건수 집계
                recs_t1 = date_summary["records"]
                field_defs_t1 = [
                    ("lodging_weight", "숙소수당"),
                    ("health_weight", "보건수당"),
                    ("leader_weight", "팀장수당"),
                    ("weekly_holiday", "주차수당"),
                    ("monthly_holiday", "월차수당"),
                ]
                for ct in date_summary.get("custom_types", []):
                    field_defs_t1.append((f"custom_{ct['type_id']}", f"[추가수당] {ct['display_name']}수당"))
                field_defs_t1.extend([
                    ("normal_weight", "일반공수"),
                    ("overtime_weight", "연장공수"),
                    ("prev_month_missing", "전월 누락공수"),
                    ("deduction", "차감공수"),
                ])

                field_label_map_t1 = {}
                for f_key, f_name in field_defs_t1:
                    f_cnt = sum(1 for r in recs_t1 if float(r.get(f_key, 0.0) or 0.0) != 0.0)
                    lbl = f"{f_name} (현재 {f_cnt}명 입력됨)" if f_cnt > 0 else f"{f_name} (0명)"
                    field_label_map_t1[lbl] = (f_key, f_name)

                selected_target_fields_t1 = None
                selected_field_names_t1 = []
                if is_selective_t1:
                    default_lbls_t1 = [lbl for lbl, (fk, _) in field_label_map_t1.items() if "현재 " in lbl and fk not in ("normal_weight", "overtime_weight")]
                    sel_lbls_t1 = st.multiselect(
                        "🧹 삭제(0으로 초기화)할 수당/공수 항목을 선택하세요 (여러 개 선택 가능)",
                        options=list(field_label_map_t1.keys()),
                        default=default_lbls_t1,
                        key=f"tab1_sel_fields_{target_del_date_str}_{sel_del_date_team}"
                    )
                    selected_target_fields_t1 = [field_label_map_t1[l][0] for l in sel_lbls_t1]
                    selected_field_names_t1 = [field_label_map_t1[l][1] for l in sel_lbls_t1]

                st.warning(
                    f"⚠️ **{fmt_target_date}** (대상: **{sel_del_date_team}**)에 저장된 출역 데이터 **{att_cnt}건**"
                    + (f", 추가수당 **{cust_cnt}건**" if cust_cnt > 0 else "")
                    + (" 중 선택하신 **[" + ", ".join(selected_field_names_t1) + "]** 항목만 0으로 삭제됩니다." if is_selective_t1 and selected_field_names_t1 else "이 존재합니다.")
                )
                if date_summary["records"]:
                    rename_map_t1 = {
                        "worker_id": "주민번호",
                        "name": "성명",
                        "team": "소속팀",
                        "normal_weight": "일반공수",
                        "overtime_weight": "연장공수",
                        "prev_month_missing": "누락",
                        "deduction": "차감",
                        "weekly_holiday": "주차",
                        "monthly_holiday": "월차",
                        "lodging_weight": "숙소",
                        "health_weight": "보건",
                        "leader_weight": "팀장"
                    }
                    for ct in date_summary.get("custom_types", []):
                        rename_map_t1[f"custom_{ct['type_id']}"] = f"{ct['display_name']}수당"
                    df_del_preview = pd.DataFrame(date_summary["records"]).rename(columns=rename_map_t1)
                    st.dataframe(df_del_preview, use_container_width=True, hide_index=True)

                can_proceed_t1 = (not is_selective_t1) or (len(selected_target_fields_t1) > 0)
                action_desc_t1 = (
                    f"선택한 수당/공수({', '.join(selected_field_names_t1)})"
                    if is_selective_t1 else "모든 출역/공수/수당 데이터"
                )
                confirm_date_del = st.checkbox(
                    f"위 내용을 확인하였으며, {fmt_target_date} ({sel_del_date_team})의 {action_desc_t1}를 삭제합니다.",
                    disabled=not can_proceed_t1,
                    key=f"tab1_confirm_del_date_{target_del_date_str}_{sel_del_date_team}_{is_selective_t1}"
                )
                if st.button(
                    f"🗑️ {fmt_target_date} ({sel_del_date_team}) {action_desc_t1} 삭제 실행",
                    type="primary",
                    use_container_width=True,
                    disabled=(is_locked or not confirm_date_del or not can_proceed_t1),
                    key=f"tab1_btn_del_date_{target_del_date_str}_{sel_del_date_team}_{is_selective_t1}"
                ):
                    try:
                        del_res = db_manager.delete_attendance_by_date(
                            target_del_date_str,
                            st.session_state.user_id,
                            team=sel_del_date_team,
                            target_fields=selected_target_fields_t1 if is_selective_t1 else None
                        )
                        st.toast(f"✅ {fmt_target_date} ({action_desc_t1}) 삭제가 완료되었습니다!")
                        get_attendance_grid.clear()
                        st.rerun()
                    except Exception as e:
                        st.error(f"날짜 데이터 삭제 중 오류 발생: {e}")

        st.markdown("---")
        # 5. 월말 집계 피벗 데이터 선계산 옵션 선택
        st.markdown("##### ⚙️ 월말 집계표 다운로드 및 미리보기 옵션")
        export_mode = st.radio(
            "📅 일자별 칸(1일~31일) 공수 표시 방식",
            [
                "1. 일자별 총공수 표시 (일반+연장+누락-차감+수당 모두 합산)",
                "2. 일자별 일반/연장 공수만 표시 (그 외 주월차/수당은 우측 집계란에만 합산)"
            ],
            index=0,
            horizontal=True,
            key="excel_export_mode_radio"
        )
        show_only_normal_overtime = "2." in export_mode
        
        pivot_rows = []
        custom_rows = []
        all_w_list, all_a_list, all_dates, all_days, all_versions, all_custom_allowances = get_attendance_grid(st.session_state.selected_ym)
        for w in all_w_list:
            tot_normal = 0.0
            tot_overtime = 0.0
            tot_prev_missing = 0.0
            tot_deduction = 0.0
            tot_weekly = 0.0
            tot_monthly = 0.0
            tot_lodging = 0.0
            tot_health = 0.0
            tot_leader = 0.0
            tot_custom = 0.0
            custom_sums_for_w = {cat["type_id"]: 0.0 for cat in all_custom_allowances}

            r_date_raw = w.get("resignation_date")
            if r_date_raw:
                r_clean = str(r_date_raw).replace("-", "").replace("/", "").strip()
                if len(r_clean) >= 8:
                    status_disp = f"🔴 퇴사 ({r_clean[4:6]}/{r_clean[6:8]})"
                else:
                    status_disp = f"🔴 퇴사 ({r_date_raw})"
            else:
                status_disp = "재직"

            row_sum = {
                "주민번호": w["worker_id"],
                "성명": w["name"],
                "상태": status_disp,
                "팀": w["team"] or "",
                "직종": w["trade"] or ""
            }
            for d_idx, d_str in enumerate(all_dates):
                key = f"{d_str}_{w['worker_id']}"
                day_col = all_days[d_idx]
                normal_val = 0.0
                over_val = 0.0
                prev_missing_val = 0.0
                deduction_val = 0.0
                weekly_val = 0.0
                monthly_val = 0.0
                lodging_val = 0.0
                health_val = 0.0
                leader_val = 0.0
                custom_val = 0.0
                if key in all_versions:
                    rec = all_versions[key]
                    normal_val = rec.get("normal_weight", 0.0) or 0.0
                    over_val = rec.get("overtime_weight", 0.0) or 0.0
                    prev_missing_val = rec.get("prev_month_missing", 0.0) or 0.0
                    deduction_val = rec.get("deduction", 0.0) or 0.0
                    weekly_val = rec.get("weekly_holiday", 0.0) or 0.0
                    monthly_val = rec.get("monthly_holiday", 0.0) or 0.0
                    lodging_val = rec.get("lodging_weight", 0.0) or 0.0
                    health_val = rec.get("health_weight", 0.0) or 0.0
                    leader_val = rec.get("leader_weight", 0.0) or 0.0
                    for cat in all_custom_allowances:
                        c_val = float(rec.get("custom_" + cat["type_id"], 0.0) or 0.0)
                        custom_val += c_val
                        custom_sums_for_w[cat["type_id"]] += c_val
                tot_normal += normal_val
                tot_overtime += over_val
                tot_prev_missing += prev_missing_val
                tot_deduction += deduction_val
                tot_weekly += weekly_val
                tot_monthly += monthly_val
                tot_lodging += lodging_val
                tot_health += health_val
                tot_leader += leader_val
                tot_custom += custom_val
                
                if show_only_normal_overtime:
                    val_sum = normal_val + over_val
                else:
                    val_sum = normal_val + over_val + prev_missing_val - deduction_val + weekly_val + monthly_val + lodging_val + health_val + leader_val + custom_val
                row_sum[day_col] = val_sum
            row_sum["출역"] = tot_normal
            row_sum["연장"] = tot_overtime
            row_sum["누락"] = tot_prev_missing
            row_sum["차감"] = tot_deduction
            row_sum["주차"] = tot_weekly
            row_sum["월차"] = tot_monthly
            if not hide_allowances:
                row_sum["숙소"] = tot_lodging
                row_sum["보건"] = tot_health
                row_sum["팀장"] = tot_leader
                for cat in all_custom_allowances:
                    row_sum[f"{cat['display_name']}수당"] = custom_sums_for_w[cat["type_id"]]
                row_sum["기타"] = tot_custom
                row_sum["총공수"] = tot_normal + tot_overtime + tot_prev_missing - tot_deduction + tot_weekly + tot_monthly + tot_lodging + tot_health + tot_leader + tot_custom
            else:
                row_sum["총공수"] = tot_normal + tot_overtime + tot_prev_missing - tot_deduction + tot_weekly + tot_monthly
            pivot_rows.append(row_sum)

            if all_custom_allowances:
                c_row = {
                    "주민번호": w["worker_id"],
                    "성명": w["name"],
                    "상태": status_disp,
                    "팀": w["team"] or "",
                    "직종": w["trade"] or ""
                }
                tot_c_sum = 0.0
                for cat in all_custom_allowances:
                    c_amt = custom_sums_for_w[cat["type_id"]]
                    c_row[f"{cat['display_name']}수당"] = c_amt
                    tot_c_sum += c_amt
                c_row["추가수당 합계"] = tot_c_sum
                custom_rows.append(c_row)
            
        if pivot_rows:
            total_sum_row = {
                "주민번호": "일일 합계",
                "성명": "",
                "상태": "",
                "팀": "",
                "직종": ""
            }
            for d_idx, d_str in enumerate(all_dates):
                day_col = all_days[d_idx]
                total_sum_row[day_col] = round(sum(float(r[day_col]) for r in pivot_rows if day_col in r), 2)
            total_sum_row["출역"] = round(sum(float(r["출역"]) for r in pivot_rows if "출역" in r), 2)
            total_sum_row["연장"] = round(sum(float(r["연장"]) for r in pivot_rows if "연장" in r), 2)
            total_sum_row["누락"] = round(sum(float(r["누락"]) for r in pivot_rows if "누락" in r), 2)
            total_sum_row["차감"] = round(sum(float(r["차감"]) for r in pivot_rows if "차감" in r), 2)
            total_sum_row["주차"] = round(sum(float(r["주차"]) for r in pivot_rows if "주차" in r), 2)
            total_sum_row["월차"] = round(sum(float(r["월차"]) for r in pivot_rows if "월차" in r), 2)
            if not hide_allowances:
                total_sum_row["숙소"] = round(sum(float(r["숙소"]) for r in pivot_rows if "숙소" in r), 2)
                total_sum_row["보건"] = round(sum(float(r["보건"]) for r in pivot_rows if "보건" in r), 2)
                total_sum_row["팀장"] = round(sum(float(r["팀장"]) for r in pivot_rows if "팀장" in r), 2)
                for cat in all_custom_allowances:
                    c_col = f"{cat['display_name']}수당"
                    total_sum_row[c_col] = round(sum(float(r[c_col]) for r in pivot_rows if c_col in r), 2)
                total_sum_row["기타"] = round(sum(float(r["기타"]) for r in pivot_rows if "기타" in r), 2)
            total_sum_row["총공수"] = round(sum(float(r["총공수"]) for r in pivot_rows if "총공수" in r), 2)
            import copy
            pivot_rows.insert(0, copy.deepcopy(total_sum_row))
            pivot_rows.append(copy.deepcopy(total_sum_row))
            
        df_pivot_out = pd.DataFrame(pivot_rows)

        df_custom_out = pd.DataFrame()
        if custom_rows:
            total_c_row = {
                "주민번호": "일일 합계",
                "성명": "",
                "상태": "",
                "팀": "",
                "직종": ""
            }
            for cat in all_custom_allowances:
                c_col = f"{cat['display_name']}수당"
                total_c_row[c_col] = round(sum(float(r[c_col]) for r in custom_rows if c_col in r), 2)
            total_c_row["추가수당 합계"] = round(sum(float(r["추가수당 합계"]) for r in custom_rows if "추가수당 합계" in r), 2)
            import copy
            custom_rows.insert(0, copy.deepcopy(total_c_row))
            custom_rows.append(copy.deepcopy(total_c_row))
            df_custom_out = pd.DataFrame(custom_rows)

        # 6. 자동 수당 연산 버튼 영역
        st.markdown("---")
        st.markdown("##### ⚡ 주휴/월차/보건수당 자동 연산 시스템")
        col_btn1, col_btn2 = st.columns([1, 1])
        with col_btn1:
            if st.button("🔄 주차/월차/보건 수당 자동 재계산 및 반영", type="primary", use_container_width=True, disabled=is_locked):
                with st.spinner("주차/월차/보건 수당 규칙을 기반으로 전체 연산을 수행 중입니다..."):
                    try:
                        calc_engine.recalculate_month(st.session_state.selected_ym, st.session_state.user_id)
                        st.success("성공적으로 주차, 월차, 보건 수당을 자동 연산하여 반영했습니다!")
                        get_attendance_grid.clear()
                        st.rerun()
                    except Exception as e:
                        st.error(f"주월차/보건 적용 중 오류 발생: {e}")
        # 6-2. 엑셀 리포트 출력 다운로드 (메인 시트 + 추가수당 시트 세트 생성)
        with col_btn2:
            if not df_pivot_out.empty:
                excel_bytes = excel_io.export_monthly_excel(df_pivot_out, st.session_state.selected_ym, df_custom=df_custom_out)
                st.download_button(
                     label="📤 월말 공수 집계표 다운로드 (Excel)",
                     data=excel_bytes,
                     file_name=f"대선이엔씨_공수정산표_{st.session_state.selected_ym}.xlsx",
                     mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                     use_container_width=True
                )
        # 7. 월말 집계 요약 미리보기 테이블 표시 (메인 집계표 & 추가 수당 집계표)
        st.markdown("##### 📊 월말 집계 요약 미리보기 (전체)")
        summary_cols = ["주민번호", "성명", "상태", "팀", "직종", "출역", "연장", "주차", "월차"]
        if not hide_allowances:
             summary_cols += ["숙소", "보건", "팀장"]
             for cat in all_custom_allowances:
                 c_col = f"{cat['display_name']}수당"
                 if c_col not in summary_cols:
                     summary_cols.append(c_col)
             summary_cols += ["기타"]
        summary_cols += ["총공수"]

        # 추가 수당 요약 컬럼 소수점 2자리 지정 추가
        for cat in all_custom_allowances:
            c_col = f"{cat['display_name']}수당"
            col_config[c_col] = st.column_config.NumberColumn(c_col, format="%.2f")
        col_config["추가수당 합계"] = st.column_config.NumberColumn("추가수당 합계", format="%.2f")

        def style_summary(df):
            style_df = pd.DataFrame('', index=df.index, columns=df.columns)
            for idx in df.index:
                st_val = str(df.loc[idx, "상태"]) if "상태" in df.columns else ""
                if "퇴사" in st_val:
                    for col in df.columns:
                        style_df.loc[idx, col] = 'color: #FFD1D1; font-weight: bold; background-color: #5C1D1D;'
                if df.loc[idx, "주민번호"] == "일일 합계":
                    for col in df.columns:
                        style_df.loc[idx, col] = 'color: #F8FAFC; font-weight: bold; background-color: #1E293B; font-size: 13px;'
            return style_df
        valid_summary_cols = [c for c in summary_cols if c in df_pivot_out.columns]
        styled_summary_df = df_pivot_out[valid_summary_cols].style.apply(style_summary, axis=None)
        st.dataframe(styled_summary_df, column_config=col_config, use_container_width=True, hide_index=True)

        if not df_custom_out.empty and all_custom_allowances:
            st.markdown("##### 💰 추가 수당 상세 집계표 (개별 수당별 집계)")
            styled_custom_summary_df = df_custom_out.style.apply(style_summary, axis=None)
            st.dataframe(styled_custom_summary_df, column_config=col_config, use_container_width=True, hide_index=True)

        if long_resigned_workers:
            with st.expander(f"📁 해당 월 1일 기준 1달 이상 퇴사자 전용 목록 (공수입력 제외 대상: {len(long_resigned_workers)}명)", expanded=False):
                st.info("💡 아래 근로자들은 해당 월 1일 자 기준으로 퇴사한 지 1달 이상 경과하여 메인 공수 표 및 편집창에서 자동 제외되었습니다.")
                df_long_list = pd.DataFrame(long_resigned_workers)
                df_long_list_renamed = df_long_list.rename(columns={
                    "worker_id": "주민번호",
                    "name": "성명",
                    "team": "소속팀",
                    "trade": "직종/공종",
                    "hire_date": "입사일",
                    "resignation_date": "퇴사일",
                    "remarks": "비고"
                })
                col_show_long = ["주민번호", "성명", "소속팀", "직종/공종", "입사일", "퇴사일", "비고"]
                df_long_list_renamed = df_long_list_renamed[[c for c in col_show_long if c in df_long_list_renamed.columns]]
                st.dataframe(df_long_list_renamed, use_container_width=True, hide_index=True)

        # 8. 일자별 수당 적용 현황 요약표 (날짜별 적용 수당 및 지급 인원)
        st.markdown("---")
        st.markdown("##### 📅 일자별 수당 적용 현황 요약 (날짜별 적용 수당 종류 및 지급 인원)")
        daily_summary_list = []
        for d_idx, d_str in enumerate(all_dates):
            day_col = all_days[d_idx]
            cnt_w = 0
            cnt_m = 0
            cnt_l = 0
            cnt_h = 0
            cnt_le = 0
            c_cnts = {cat["type_id"]: 0 for cat in all_custom_allowances}
            for w in all_w_list:
                k = f"{d_str}_{w['worker_id']}"
                if k in all_versions:
                    r = all_versions[k]
                    if (r.get("weekly_holiday", 0.0) or 0.0) > 0: cnt_w += 1
                    if (r.get("monthly_holiday", 0.0) or 0.0) > 0: cnt_m += 1
                    if (r.get("lodging_weight", 0.0) or 0.0) > 0: cnt_l += 1
                    if (r.get("health_weight", 0.0) or 0.0) > 0: cnt_h += 1
                    if (r.get("leader_weight", 0.0) or 0.0) > 0: cnt_le += 1
                    for cat in all_custom_allowances:
                        if float(r.get("custom_" + cat["type_id"], 0.0) or 0.0) > 0:
                            c_cnts[cat["type_id"]] += 1
            act_tags = []
            if cnt_w > 0: act_tags.append(f"주차({cnt_w}명)")
            if cnt_m > 0: act_tags.append(f"월차({cnt_m}명)")
            if cnt_l > 0: act_tags.append(f"숙소({cnt_l}명)")
            if cnt_h > 0: act_tags.append(f"보건({cnt_h}명)")
            if cnt_le > 0: act_tags.append(f"팀장({cnt_le}명)")
            for cat in all_custom_allowances:
                c_num = c_cnts[cat["type_id"]]
                if c_num > 0:
                    act_tags.append(f"{cat['display_name']}({c_num}명)")
            d_row = {
                "날짜": styled_days[d_idx],
                "주차수당": f"{cnt_w}명" if cnt_w > 0 else "-",
                "월차수당": f"{cnt_m}명" if cnt_m > 0 else "-",
                "숙소수당": f"{cnt_l}명" if cnt_l > 0 else "-",
                "보건수당": f"{cnt_h}명" if cnt_h > 0 else "-",
                "팀장수당": f"{cnt_le}명" if cnt_le > 0 else "-",
            }
            for cat in all_custom_allowances:
                c_num = c_cnts[cat["type_id"]]
                d_row[f"{cat['display_name']}수당"] = f"{c_num}명" if c_num > 0 else "-"
            d_row["적용 수당 요약"] = ", ".join(act_tags) if act_tags else "-"
            daily_summary_list.append(d_row)
        df_daily_summary_out = pd.DataFrame(daily_summary_list)
        st.dataframe(df_daily_summary_out, use_container_width=True, hide_index=True)

# ----------------- Tab 2: 일일 출역일보 업로드 -----------------
with tab_upload:
    st.subheader("📥 출역 및 공수 데이터 업로드 센터")
    # 지속성 완료/오류 메시지 표시 (Tab 2)
    has_msg = False
    if "persistent_import_success" in st.session_state and st.session_state.persistent_import_success:
        st.success(st.session_state.persistent_import_success)
        has_msg = True
    if "persistent_import_error" in st.session_state and st.session_state.persistent_import_error:
        st.error(st.session_state.persistent_import_error)
        has_msg = True
    if "persistent_import_warnings" in st.session_state and st.session_state.persistent_import_warnings:
        warnings_data = st.session_state.persistent_import_warnings
        if isinstance(warnings_data, list):
            if warnings_data and isinstance(warnings_data[0], dict):
                st.warning("⚠️ 일부 행 매칭 또는 검증 실패가 발생하여 시스템 로그에 영구 격리 기록되었습니다.")
                st.dataframe(pd.DataFrame(warnings_data), use_container_width=True)
            else:
                st.warning("⚠️ 일부 행에 경고가 발생했습니다:")
                for warn in warnings_data:
                    st.write(f"- {warn}")
        else:
            st.warning(warnings_data)
        has_msg = True
    if has_msg:
        if st.button("❌ 메시지 확인 및 지우기", key="clear_tab2_import_msg", use_container_width=True):
            st.session_state.persistent_import_success = None
            st.session_state.persistent_import_error = None
            st.session_state.persistent_import_warnings = None
            st.rerun()
    st.write("단말기 집계 일일출역보, 선택적 일괄 입력 서식, 혹은 원청사(현대건설) 일일출역 엑셀을 연동하여 공수를 빠르게 채웁니다.")
    sub_tab_daily, sub_tab_bulk, sub_tab_hyundai, sub_tab_check, sub_tab_del_date = st.tabs([
        "일일출역보 엑셀 업로드 (기본)",
        "선택적 공수 일괄 등록 (덮어쓰기)",
        "현대건설 샤힌현장 일일출역 연동",
        "✅ 일별 입력 체크리스트",
        "🗑️ 특정 날짜 데이터 삭제"
    ])
    with sub_tab_daily:
        col_u1, col_u2 = st.columns([1, 1])
        with col_u1:
            target_date = st.date_input("출역을 반영할 날짜 선택", datetime.date.today(), key="daily_date")
            date_str_upload = target_date.strftime("%Y%m%d")
            # 일일출역일보 엑셀 템플릿 다운로드 추가
            daily_tpl_bytes = excel_io.generate_daily_attendance_template()
            st.download_button(
                label="📥 일일출역일보 업로드 엑셀 양식 다운로드",
                data=daily_tpl_bytes,
                file_name="일일출역일보_업로드_표준양식.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="download_daily_tpl_btn"
            )
            st.markdown("---")
            uploaded_file = st.file_uploader(
                "엑셀 파일 선택 (*.xlsx, *.xls)",
                type=["xlsx", "xls"],
                key="daily_file_uploader",
                disabled=is_locked
            )
            upload_submit = st.button("🚀 엑셀 데이터 가져오기 실행", disabled=(is_locked or not uploaded_file), use_container_width=True)
            if upload_submit and uploaded_file:
                with st.spinner("엑셀 파싱 및 근로자 매칭 검증을 수행하고 있습니다..."):
                    try:
                        file_bytes = uploaded_file.read()
                        success_cnt, failures = excel_io.import_daily_excel(
                            file_content=file_bytes,
                            file_name=uploaded_file.name,
                            date_str=date_str_upload,
                            user_id=st.session_state.user_id
                        )
                        st.session_state.persistent_import_success = f"가져오기 완료! 매칭 성공 및 등록 완료 건수: {success_cnt}건"
                        st.session_state.persistent_import_warnings = failures if failures else None
                        st.session_state.persistent_import_error = None
                        get_attendance_grid.clear()
                        st.rerun()
                    except Exception as e:
                        st.session_state.persistent_import_error = f"일일출역보 업로드 오류: {e}\n\n{traceback.format_exc()}"
                        st.session_state.persistent_import_success = None
                        st.session_state.persistent_import_warnings = None
                        st.rerun()
        with col_u2:
            st.markdown("""
            #### 💡 가져오기 매칭 가이드라인
            - 엑셀 파일은 첫 번째 시트에 데이터를 위치시켜야 합니다.
            - **필수 열**: `주민번호`, `이름(또는 성명)`, `일반공수(또는 공수)` 헤더가 명시되어 있어야 합니다.
            - **주민번호**를 기준으로 우선 매칭하며, 주민번호가 비어 있는 경우 **이름**으로 찾습니다.
            - 동명이인이 있거나 마스터에 없는 이름인 경우 매칭에 실패하며 실패 사유와 함께 데이터베이스에 격리 기록됩니다.
            - 하루 총합 공수는 `2.5`시간을 초과할 수 없습니다.
            """)
    with sub_tab_bulk:
        st.markdown("#### 📝 선택적 공수 일괄 등록 (덮어쓰기)")
        st.write("여러 근로자의 다수 일자 공수/수당 데이터를 엑셀로 기입하여 일괄 덮어쓰기 업데이트를 실행합니다. 빈 칸은 기존 데이터가 보존됩니다.")
        # 1. 템플릿 다운로드
        customs_definitions = db_manager.get_custom_weight_types()
        customs_names = [c["type_id"] for c in customs_definitions]
        bulk_tpl = excel_io.generate_bulk_attendance_template(customs_names)
        st.download_button(
            "📋 공수 일괄 입력 엑셀 양식 다운로드",
            data=bulk_tpl,
            file_name="공수_일괄입력_양식.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
        st.markdown("---")
        # 2. 파일 업로드 및 반영
        bulk_file = st.file_uploader(
            "일괄 입력 엑셀 파일 선택",
            type=["xlsx", "xls"],
            key="bulk_file_uploader",
            disabled=is_locked
        )
        bulk_submit = st.button("🚀 일괄 공수 반영 실행", disabled=(is_locked or not bulk_file), use_container_width=True)
        if bulk_submit and bulk_file:
            with st.spinner("엑셀 파싱 및 공수 선택적 반영을 수행 중입니다..."):
                import tempfile
                with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
                    tmp.write(bulk_file.read())
                    tmp_path = tmp.name
                try:
                    res = excel_io.parse_and_import_bulk_attendance(tmp_path, st.session_state.user_id)
                    if res["success"]:
                        st.session_state.persistent_import_success = f"일괄 등록 완료! 성공 건수: {res['success_count']}건"
                        st.session_state.persistent_import_warnings = res["error_rows"] if res["error_rows"] else None
                        st.session_state.persistent_import_error = None
                        get_attendance_grid.clear()
                        st.rerun()
                    else:
                        st.session_state.persistent_import_error = f"일괄 공수 등록 실패: {res['error']}"
                        st.session_state.persistent_import_success = None
                        st.session_state.persistent_import_warnings = None
                        st.rerun()
                except Exception as e:
                    st.session_state.persistent_import_error = f"일괄 공수 등록 오류: {e}\n\n{traceback.format_exc()}"
                    st.session_state.persistent_import_success = None
                    st.session_state.persistent_import_warnings = None
                    st.rerun()
                finally:
                    if os.path.exists(tmp_path):
                        try:
                            os.remove(tmp_path)
                        except:
                            pass
    with sub_tab_hyundai:
        st.markdown("#### 🏗️ 현대건설 샤힌현장 일일출역 연동")
        st.write("현대건설 샤힌 에틸렌시설 건설공사 현장의 일일출역현황(P_A) 엑셀 파일을 업로드하여 자동으로 매칭되는 근로자의 일반 및 연장 공수를 입력합니다.")
        col_h1, col_h2 = st.columns([1, 1])
        with col_h1:
            h_target_date = st.date_input("출역을 반영할 날짜 선택", datetime.date.today(), key="hyundai_date")
            h_date_str = h_target_date.strftime("%Y-%m-%d")
            hyundai_file = st.file_uploader(
                "현대건설 일일출역현황 엑셀 파일 선택",
                type=["xlsx", "xls"],
                key="hyundai_file_uploader",
                disabled=is_locked
            )
            hyundai_submit = st.button("🚀 현대건설 출역 데이터 가져오기 실행", disabled=(is_locked or not hyundai_file), use_container_width=True)
            if hyundai_submit and hyundai_file:
                with st.spinner("엑셀 복구 및 현대건설 출역 매칭을 수행하고 있습니다..."):
                    import tempfile
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
                        tmp.write(hyundai_file.read())
                        tmp_path = tmp.name
                    try:
                        res = excel_io.parse_hyundai_daily_attendance(tmp_path, h_date_str, st.session_state.user_id)
                        if res["success"]:
                            st.session_state.persistent_import_success = f"가져오기 완료! 매칭 성공: {res['success_count']}건, 비출역(제외) 건수: {res['skip_count']}건"
                            st.session_state.persistent_import_warnings = [
                                f"주민번호 매칭 실패 근로자: {w}" for w in res["unmatched_workers"]
                            ] if res["unmatched_workers"] else None
                            st.session_state.persistent_import_error = None
                            get_attendance_grid.clear()
                            st.rerun()
                        else:
                            st.session_state.persistent_import_error = f"현대건설 연동 실패: {res['error']}"
                            st.session_state.persistent_import_success = None
                            st.session_state.persistent_import_warnings = None
                            st.rerun()
                    except Exception as e:
                        st.session_state.persistent_import_error = f"현대건설 연동 오류: {e}\n\n{traceback.format_exc()}"
                        st.session_state.persistent_import_success = None
                        st.session_state.persistent_import_warnings = None
                        st.rerun()
                    finally:
                        if os.path.exists(tmp_path):
                            try:
                                os.remove(tmp_path)
                            except:
                                pass
        with col_h2:
            st.markdown("""
            ##### 💡 현대건설 연동 파싱 규칙
            - **매칭 기준**: 엑셀 첫 번째 열의 `이름(주민번호)`란에서 괄호 안의 주민등록번호와 데이터베이스의 **주민번호**를 일치시켜 매칭합니다.
            - **출역 판별**: `출역` 컬럼이 `1`인 인원만 유효 근로자로 필터링합니다. (출역이 0이거나 미지정인 인원은 자동으로 스킵)
            - **공수 매핑**: 
              - `기본` 컬럼의 가중치 -> **일반공수** 입력
              - `연장` 컬럼의 가중치 -> **연장공수** 입력
            - **기존 공수 처리**: 이미 해당 일자에 해당 근로자의 데이터가 존재하는 경우 일반/연장 공수만 덮어쓰고, 기존 숙소/보건/팀장 수당 및 사용자가 설정한 값은 보존됩니다.
            """)
    with sub_tab_check:
        st.markdown("#### ✅ 일별 입력 완료 체크리스트")
        st.write("해당 월의 일자별로 데이터 입력이 완료되었는지 체크하여 진행 상황을 파악합니다. (단순 확인용)")
        selected_ym = st.session_state.selected_ym
        # Get dates for selected month
        y, m = int(selected_ym[:4]), int(selected_ym[5:7])
        import calendar
        num_days = calendar.monthrange(y, m)[1]
        dates_in_month = [f"{y:04d}{m:02d}{d:02d}" for d in range(1, num_days + 1)]
        # Load existing checks from DB
        db_checks = db_manager.get_daily_checks(selected_ym)
        # Build dataframe
        import pandas as pd
        check_data = []
        weekday_map = {0: "월", 1: "화", 2: "수", 3: "목", 4: "금", 5: "토", 6: "일"}
        for d_str in dates_in_month:
            dt_obj = datetime.date(int(d_str[:4]), int(d_str[4:6]), int(d_str[6:8]))
            weekday = weekday_map[dt_obj.weekday()]
            check_data.append({
                "날짜": f"{d_str[:4]}-{d_str[4:6]}-{d_str[6:8]} ({weekday})",
                "완료여부": db_checks.get(d_str, False),
                "date_key": d_str
            })
        df_checks = pd.DataFrame(check_data)
        col_c1, col_c2 = st.columns([1, 1])
        with col_c1:
            st.info("아래 표에서 입력이 완료된 날짜에 체크하고 **[변경사항 저장]** 버튼을 누르세요.")
            edited_checks = st.data_editor(
                df_checks[["날짜", "완료여부"]],
                column_config={
                    "날짜": st.column_config.TextColumn("일자", disabled=True),
                    "완료여부": st.column_config.CheckboxColumn("입력 완료", default=False)
                },
                hide_index=True,
                use_container_width=True,
                key=f"editor_checks_{selected_ym}"
            )
            if st.button("💾 체크 변경사항 저장", key="btn_save_daily_checks"):
                # Update dict
                new_checks = {}
                for idx, row in edited_checks.iterrows():
                    d_key = df_checks.iloc[idx]["date_key"]
                    new_checks[d_key] = bool(row["완료여부"])
                db_manager.save_daily_checks(new_checks)
                st.success("✅ 일별 완료 체크 정보가 성공적으로 저장되었습니다.")
    with sub_tab_del_date:
        st.markdown("#### 🗑️ 특정 날짜 출역/공수 및 특정 수당 선택 삭제")
        st.write("날짜를 잘못 선택하여 업로드했거나 특정 일자의 **전체 데이터** 또는 **특정 수당(숙소·보건·팀장·주월차·추가수당 등)만 골라서 삭제(0으로 초기화)**할 수 있습니다.")
        col_del_d1, col_del_d2 = st.columns([1, 1])
        with col_del_d1:
            del_picker_date = st.date_input("📅 데이터를 삭제할 날짜 선택", datetime.date.today(), key="tab2_del_date_picker")
            del_picker_str = del_picker_date.strftime("%Y%m%d")
            del_picker_fmt = del_picker_date.strftime("%Y-%m-%d")
        with col_del_d2:
            all_w_for_del = db_manager.get_all_workers()
            teams_for_del_tab2 = sorted(list(set([w["team"] for w in all_w_for_del if w.get("team")])))
            sel_team_tab2 = st.selectbox(
                "🎯 삭제 대상 팀 선택 (전체 선택 시 해당 날짜의 모든 근로자 데이터 삭제)",
                options=["전체"] + teams_for_del_tab2,
                key="tab2_del_date_team"
            )

        t2_summary = db_manager.get_date_attendance_summary(del_picker_str, team=sel_team_tab2)
        t2_att_cnt = t2_summary["attendance_count"]
        t2_cust_cnt = t2_summary["custom_count"]

        if t2_att_cnt == 0 and t2_cust_cnt == 0:
            st.info(f"💡 선택한 날짜(**{del_picker_fmt}**, 대상: **{sel_team_tab2}**)에 저장된 출역/공수 데이터가 없습니다.")
        else:
            del_mode_t2 = st.radio(
                "🛠️ 삭제 방식 선택",
                [
                    "1. 전체 삭제 (해당 날짜의 출역·공수·모든 수당 전체 초기화)",
                    "2. 특정 수당/공수 항목만 선택하여 삭제 (선택한 수당만 0으로 초기화)"
                ],
                horizontal=True,
                key=f"tab2_del_mode_{del_picker_str}_{sel_team_tab2}"
            )
            is_selective_t2 = del_mode_t2.startswith("2.")

            recs_t2 = t2_summary["records"]
            field_defs_t2 = [
                ("lodging_weight", "숙소수당"),
                ("health_weight", "보건수당"),
                ("leader_weight", "팀장수당"),
                ("weekly_holiday", "주차수당"),
                ("monthly_holiday", "월차수당"),
            ]
            for ct in t2_summary.get("custom_types", []):
                field_defs_t2.append((f"custom_{ct['type_id']}", f"[추가수당] {ct['display_name']}수당"))
            field_defs_t2.extend([
                ("normal_weight", "일반공수"),
                ("overtime_weight", "연장공수"),
                ("prev_month_missing", "전월 누락공수"),
                ("deduction", "차감공수"),
            ])

            field_label_map_t2 = {}
            for f_key, f_name in field_defs_t2:
                f_cnt = sum(1 for r in recs_t2 if float(r.get(f_key, 0.0) or 0.0) != 0.0)
                lbl = f"{f_name} (현재 {f_cnt}명 입력됨)" if f_cnt > 0 else f"{f_name} (0명)"
                field_label_map_t2[lbl] = (f_key, f_name)

            selected_target_fields_t2 = None
            selected_field_names_t2 = []
            if is_selective_t2:
                default_lbls_t2 = [lbl for lbl, (fk, _) in field_label_map_t2.items() if "현재 " in lbl and fk not in ("normal_weight", "overtime_weight")]
                sel_lbls_t2 = st.multiselect(
                    "🧹 삭제(0으로 초기화)할 수당/공수 항목을 선택하세요 (여러 개 선택 가능)",
                    options=list(field_label_map_t2.keys()),
                    default=default_lbls_t2,
                    key=f"tab2_sel_fields_{del_picker_str}_{sel_team_tab2}"
                )
                selected_target_fields_t2 = [field_label_map_t2[l][0] for l in sel_lbls_t2]
                selected_field_names_t2 = [field_label_map_t2[l][1] for l in sel_lbls_t2]

            st.warning(
                f"⚠️ **{del_picker_fmt}** (대상: **{sel_team_tab2}**)에 저장된 출역 기록 **{t2_att_cnt}건**"
                + (f", 추가수당 **{t2_cust_cnt}건**" if t2_cust_cnt > 0 else "")
                + (" 중 선택하신 **[" + ", ".join(selected_field_names_t2) + "]** 항목만 0으로 삭제됩니다." if is_selective_t2 and selected_field_names_t2 else "이 조회되었습니다.")
            )
            if t2_summary["records"]:
                rename_map_t2 = {
                    "worker_id": "주민번호",
                    "name": "성명",
                    "team": "소속팀",
                    "normal_weight": "일반공수",
                    "overtime_weight": "연장공수",
                    "prev_month_missing": "누락",
                    "deduction": "차감",
                    "weekly_holiday": "주차",
                    "monthly_holiday": "월차",
                    "lodging_weight": "숙소",
                    "health_weight": "보건",
                    "leader_weight": "팀장"
                }
                for ct in t2_summary.get("custom_types", []):
                    rename_map_t2[f"custom_{ct['type_id']}"] = f"{ct['display_name']}수당"
                df_t2_preview = pd.DataFrame(t2_summary["records"]).rename(columns=rename_map_t2)
                st.dataframe(df_t2_preview, use_container_width=True, hide_index=True)

            can_proceed_t2 = (not is_selective_t2) or (len(selected_target_fields_t2) > 0)
            action_desc_t2 = (
                f"선택한 수당/공수({', '.join(selected_field_names_t2)})"
                if is_selective_t2 else "모든 출역/공수/수당 데이터"
            )
            t2_confirm = st.checkbox(
                f"위 내역을 확인하였으며, {del_picker_fmt} ({sel_team_tab2})의 {action_desc_t2}를 삭제합니다.",
                disabled=not can_proceed_t2,
                key=f"tab2_confirm_del_{del_picker_str}_{sel_team_tab2}_{is_selective_t2}"
            )
            if st.button(
                f"🗑️ {del_picker_fmt} ({sel_team_tab2}) {action_desc_t2} 삭제 실행",
                type="primary",
                use_container_width=True,
                disabled=(not t2_confirm or not can_proceed_t2),
                key=f"tab2_btn_del_{del_picker_str}_{sel_team_tab2}_{is_selective_t2}"
            ):
                try:
                    del_res2 = db_manager.delete_attendance_by_date(
                        del_picker_str,
                        st.session_state.user_id,
                        team=sel_team_tab2,
                        target_fields=selected_target_fields_t2 if is_selective_t2 else None
                    )
                    st.session_state.persistent_import_success = (
                        f"✅ {del_picker_fmt} ({sel_team_tab2}) [{action_desc_t2}] 삭제 완료! "
                        f"(반영된 출역 기록: {del_res2['deleted_attendance']}건, 추가수당: {del_res2['deleted_custom']}건)"
                    )
                    st.session_state.persistent_import_error = None
                    st.session_state.persistent_import_warnings = None
                    get_attendance_grid.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"삭제 중 오류 발생: {e}")

# ----------------- Tab 3: 근로자 관리 및 일괄등록 -----------------
with tab_workers:
    st.subheader("👤 근로자 관리 및 일괄등록")
    tab_w_list, tab_w_edit, tab_w_delete, tab_w_bulk, tab_w_add = st.tabs(["근로자 목록 조회", "✏️ 개별 근로자 상세 수정", "🗑️ 근로자 삭제", "📥 근로자 일괄등록", "➕ 개별 근로자 신규추가"])
    # 3-1. 근로자 목록 조회
    with tab_w_list:
        workers_list = db_manager.get_all_workers()
        if not workers_list:
            st.info("데이터베이스에 등록된 근로자가 없습니다.")
        else:
            df_workers = pd.DataFrame(workers_list)
            # 수당 수치 표현 직관성 향상 (편집 가능하도록 True/False boolean 컬럼으로 적용)
            df_workers["has_lodging"] = df_workers["has_lodging"] == 1
            df_workers["has_health"] = df_workers["has_health"] == 1
            df_workers["is_team_leader"] = df_workers["is_team_leader"] == 1
            df_workers["exclude_holiday"] = df_workers["exclude_holiday"] == 1
            # 한글 이름으로 컬럼 매핑
            col_renames = {
                "worker_id": "주민번호",
                "name": "성명",
                "team": "소속팀",
                "trade": "직종/공종",
                "hire_date": "입사일",
                "resignation_date": "퇴사일",
                "exclude_holiday": "주월차제외",
                "remarks": "비고"
            }
            df_workers_renamed = df_workers.rename(columns=col_renames)
            # 컬럼 순서 및 구성 설정
            col_order = ["주민번호", "성명", "소속팀", "직종/공종", "입사일", "퇴사일", "주월차제외", "비고"]
            df_workers_renamed = df_workers_renamed[col_order]
            col_config = {
                "주민번호": st.column_config.TextColumn("주민번호", disabled=False),
                "성명": st.column_config.TextColumn("성명"),
                "소속팀": st.column_config.TextColumn("소속팀"),
                "직종/공종": st.column_config.TextColumn("직종/공종"),
                "입사일": st.column_config.TextColumn("입사일 (YYYY-MM-DD)"),
                "퇴사일": st.column_config.TextColumn("퇴사일 (YYYY-MM-DD)"),
                "주월차제외": st.column_config.CheckboxColumn("주월차제외", default=False),
                "비고": st.column_config.TextColumn("비고")
            }
            # 근로자 목록 다운로드 기능 추가
            worker_excel_bytes = io.BytesIO()
            with pd.ExcelWriter(worker_excel_bytes, engine="openpyxl") as writer:
                df_workers_renamed.to_excel(writer, index=False, sheet_name="등록근로자목록")
            st.download_button(
                label="📥 현재 등록된 근로자 목록 다운로드 (Excel)",
                data=worker_excel_bytes.getvalue(),
                file_name="등록근로자목록.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
            st.markdown("---")
            worker_editor_key = "worker_info_editor"
            edited_df = st.data_editor(
                df_workers_renamed,
                column_config=col_config,
                key=worker_editor_key,
                use_container_width=True,
                hide_index=True
            )
            # 저장 단락
            state = st.session_state.get(worker_editor_key)
            if state and state.get("edited_rows"):
                st.warning("⚠️ 근로자 정보 변경사항이 감지되었습니다. 아래 저장 버튼을 눌러야 데이터베이스에 적용됩니다.")
                save_worker_changes = st.button("💾 근로자 정보 변경사항 저장", type="primary", use_container_width=True)
                if save_worker_changes:
                    edited_rows = state["edited_rows"]
                    conn = db_manager.get_db_connection()
                    conn.execute("PRAGMA foreign_keys = OFF;")
                    cursor = conn.cursor()
                    try:
                        for row_idx_str, changes in edited_rows.items():
                            row_idx = int(row_idx_str)
                            row_orig = df_workers_renamed.iloc[row_idx]
                            old_worker_id = row_orig["주민번호"]
                            # DB에서 기존 데이터 조회
                            cursor.execute("SELECT * FROM workers WHERE worker_id = ?;", (old_worker_id,))
                            db_row_fetch = cursor.fetchone()
                            if not db_row_fetch:
                                continue
                            db_row = dict(db_row_fetch)
                            new_worker_id = changes.get("주민번호", old_worker_id).strip()
                            name = changes.get("성명", db_row["name"]).strip()
                            team = changes.get("소속팀", db_row["team"])
                            trade = changes.get("직종/공종", db_row["trade"])
                            remarks = changes.get("비고", db_row["remarks"])
                            has_lodging = db_row["has_lodging"]
                            has_health = db_row["has_health"]
                            is_team_leader = db_row["is_team_leader"]
                            exclude_holiday = 1 if changes.get("주월차제외", db_row.get("exclude_holiday", 0) == 1) else 0
                            hire_date = changes.get("입사일", db_row["hire_date"])
                            resignation_date = changes.get("퇴사일", db_row["resignation_date"])
                            if resignation_date == "":
                                resignation_date = None
                            # 유효성 검사 (입사일 형식)
                            try:
                                datetime.datetime.strptime(hire_date, "%Y-%m-%d")
                            except ValueError:
                                st.error(f"오류: 주민번호 {old_worker_id}의 입사일 형식({hire_date})이 올바르지 않습니다. YYYY-MM-DD 형식이어야 합니다.")
                                st.stop()
                            if resignation_date:
                                try:
                                    datetime.datetime.strptime(resignation_date, "%Y-%m-%d")
                                except ValueError:
                                    st.error(f"오류: 주민번호 {old_worker_id}의 퇴사일 형식({resignation_date})이 올바르지 않습니다. YYYY-MM-DD 형식이어야 합니다.")
                                    st.stop()
                            # 만약 주민번호(ID)가 변경된 경우 관련 자식 테이블의 모든 행도 일괄 수동 업데이트 진행
                            if new_worker_id != old_worker_id:
                                # 새로운 주민번호가 이미 존재하면 중복 예외 발생시킴
                                cursor.execute("SELECT COUNT(*) as cnt FROM workers WHERE worker_id = ?;", (new_worker_id,))
                                if cursor.fetchone()["cnt"] > 0:
                                    st.error(f"오류: 변경하려는 주민번호({new_worker_id})가 이미 데이터베이스에 존재합니다.")
                                    st.stop()
                                cursor.execute("UPDATE workers SET worker_id = ? WHERE worker_id = ?;", (new_worker_id, old_worker_id))
                                cursor.execute("UPDATE daily_attendance SET worker_id = ? WHERE worker_id = ?;", (new_worker_id, old_worker_id))
                                cursor.execute("UPDATE daily_custom_attendance SET worker_id = ? WHERE worker_id = ?;", (new_worker_id, old_worker_id))
                                cursor.execute("UPDATE monthly_status SET worker_id = ? WHERE worker_id = ?;", (new_worker_id, old_worker_id))
                                cursor.execute("UPDATE audit_logs SET worker_id = ? WHERE worker_id = ?;", (new_worker_id, old_worker_id))
                            # 나머지 필드 업데이트
                            cursor.execute("""
                                UPDATE workers
                                SET name = ?, team = ?, trade = ?, has_lodging = ?, has_health = ?, is_team_leader = ?, exclude_holiday = ?, hire_date = ?, resignation_date = ?, remarks = ?
                                WHERE worker_id = ?;
                            """, (name, team, trade, has_lodging, has_health, is_team_leader, exclude_holiday, hire_date, resignation_date, remarks, new_worker_id))
                            # 감사 로그 남기기
                            db_manager.log_audit(
                                user_id=st.session_state.user_id,
                                worker_id=new_worker_id,
                                action="근로자 정보 및 주민번호 수정",
                                before_value=str(db_row),
                                after_value=f"주민번호:{new_worker_id}, 이름:{name}, 팀:{team}, 직종:{trade}, 입사:{hire_date}, 퇴사:{resignation_date}, 비고:{remarks}",
                                conn=conn
                            )
                        conn.commit()
                        if "selected_ym" in st.session_state:
                            try:
                                calc_engine.recalculate_month(st.session_state.selected_ym, st.session_state.user_id)
                            except Exception as re_err:
                                pass
                        st.success("근로자 정보 변경사항이 DB에 저장되었으며, 주월차 수당이 성공적으로 자동 재계산 및 반영되었습니다!")
                        get_attendance_grid.clear()
                        st.rerun()
                    except Exception as e:
                        conn.rollback()
                        st.error(f"저장 중 오류 발생: {e}")
                    finally:
                        conn.execute("PRAGMA foreign_keys = ON;")
                        conn.close()

    # 3-2. 개별 근로자 상세 수정
    with tab_w_edit:
        st.markdown("#### ✏️ 개별 근로자 상세 정보 수정")
        all_workers_edit = db_manager.get_all_workers()
        if not all_workers_edit:
            st.info("수정할 근로자가 존재하지 않습니다.")
        else:
            worker_opt_map = {f"[{w['worker_id']}] {w['name']} ({w['team'] or '팀없음'} / {w['trade'] or '직종없음'})": w for w in all_workers_edit}
            selected_w_opt = st.selectbox("수정할 근로자를 선택하세요", list(worker_opt_map.keys()), key="select_worker_to_edit")
            target_w = worker_opt_map[selected_w_opt]
            
            with st.form(key=f"form_edit_worker_{target_w['worker_id']}"):
                col_e1, col_e2 = st.columns(2)
                with col_e1:
                    e_name = st.text_input("성명", value=target_w["name"])
                    e_worker_id = st.text_input("주민번호 (변경 시 관련 출역 기록도 자동 갱신됩니다)", value=target_w["worker_id"])
                    e_team = st.text_input("소속팀", value=target_w["team"] or "")
                    e_trade = st.text_input("직종/공종", value=target_w["trade"] or "")
                    e_hire_date = st.text_input("입사일 (YYYY-MM-DD)", value=target_w["hire_date"])
                with col_e2:
                    e_resignation_date = st.text_input("퇴사일 (YYYY-MM-DD, 미퇴사 시 공란)", value=target_w["resignation_date"] or "")
                    e_exclude_holiday = st.checkbox("주월차 수당 계산 제외", value=(target_w.get("exclude_holiday", 0) == 1))
                    e_remarks = st.text_input("비고", value=target_w["remarks"] or "")
                    st.info(f"💡 주민번호: {target_w['worker_id']} | 등록일: {target_w['hire_date']}")
                
                btn_save_single_worker = st.form_submit_button("💾 근로자 정보 수정 저장", type="primary", use_container_width=True)
                if btn_save_single_worker:
                    e_name = e_name.strip()
                    e_worker_id = e_worker_id.strip()
                    e_team = e_team.strip() or None
                    e_trade = e_trade.strip() or None
                    e_hire_date = e_hire_date.strip()
                    e_resignation_date = e_resignation_date.strip() or None
                    e_remarks = e_remarks.strip() or None
                    
                    if not e_name:
                        st.error("성명을 입력해야 합니다.")
                        st.stop()
                    if not e_worker_id:
                        st.error("주민번호를 입력해야 합니다.")
                        st.stop()
                    try:
                        datetime.datetime.strptime(e_hire_date, "%Y-%m-%d")
                    except ValueError:
                        st.error("입사일 형식이 올바르지 않습니다. YYYY-MM-DD 형식이어야 합니다.")
                        st.stop()
                    if e_resignation_date:
                        try:
                            datetime.datetime.strptime(e_resignation_date, "%Y-%m-%d")
                        except ValueError:
                            st.error("퇴사일 형식이 올바르지 않습니다. YYYY-MM-DD 형식이어야 합니다.")
                            st.stop()
                            
                    conn = db_manager.get_db_connection()
                    conn.execute("PRAGMA foreign_keys = OFF;")
                    cursor = conn.cursor()
                    try:
                        old_w_id = target_w["worker_id"]
                        if e_worker_id != old_w_id:
                            cursor.execute("SELECT COUNT(*) as cnt FROM workers WHERE worker_id = ?;", (e_worker_id,))
                            if cursor.fetchone()["cnt"] > 0:
                                st.error(f"오류: 변경하려는 주민번호({e_worker_id})가 이미 데이터베이스에 존재합니다.")
                                st.stop()
                            cursor.execute("UPDATE workers SET worker_id = ? WHERE worker_id = ?;", (e_worker_id, old_w_id))
                            cursor.execute("UPDATE daily_attendance SET worker_id = ? WHERE worker_id = ?;", (e_worker_id, old_w_id))
                            cursor.execute("UPDATE daily_custom_attendance SET worker_id = ? WHERE worker_id = ?;", (e_worker_id, old_w_id))
                            cursor.execute("UPDATE monthly_status SET worker_id = ? WHERE worker_id = ?;", (e_worker_id, old_w_id))
                            cursor.execute("UPDATE audit_logs SET worker_id = ? WHERE worker_id = ?;", (e_worker_id, old_w_id))
                        
                        ex_val = 1 if e_exclude_holiday else 0
                        cursor.execute("""
                            UPDATE workers
                            SET name = ?, team = ?, trade = ?, exclude_holiday = ?, hire_date = ?, resignation_date = ?, remarks = ?
                            WHERE worker_id = ?;
                        """, (e_name, e_team, e_trade, ex_val, e_hire_date, e_resignation_date, e_remarks, e_worker_id))
                        
                        db_manager.log_audit(
                            user_id=st.session_state.user_id,
                            worker_id=e_worker_id,
                            action="개별 근로자 상세 정보 수정",
                            before_value=str(target_w),
                            after_value=f"주민번호:{e_worker_id}, 성명:{e_name}, 팀:{e_team}, 직종:{e_trade}, 입사:{e_hire_date}, 퇴사:{e_resignation_date}, 주월차제외:{ex_val}",
                            conn=conn
                        )
                        conn.commit()
                        if "selected_ym" in st.session_state:
                            try:
                                calc_engine.recalculate_month(st.session_state.selected_ym, st.session_state.user_id)
                            except Exception:
                                pass
                        st.success(f"✅ [{e_name}] 근로자 정보가 성공적으로 수정 반영되었습니다.")
                        get_attendance_grid.clear()
                        st.rerun()
                    except Exception as ex_err:
                        conn.rollback()
                        st.error(f"저장 중 오류 발생: {ex_err}")
                    finally:
                        conn.execute("PRAGMA foreign_keys = ON;")
                        conn.close()

    # 3-3. 근로자 삭제 (팀별 필터링 및 단일/다중 일괄 삭제)
    with tab_w_delete:
        st.markdown("#### 🗑️ 근로자 삭제 (팀별 필터 및 편리한 일괄 선택 기능)")
        
        all_workers_del = db_manager.get_all_workers()
        if not all_workers_del:
            st.info("삭제할 근로자가 존재하지 않습니다.")
        else:
            # 팀 목록 추출
            teams_del = sorted(list(set([w["team"] for w in all_workers_del if w["team"]])))
            col_dt1, col_dt2 = st.columns([1, 2])
            with col_dt1:
                sel_del_team = st.selectbox("🎯 팀 필터 선택 (원하는 팀 근로자만 선택 가능)", ["전체 (모든 팀)"] + teams_del, key="select_del_team_filter")
            
            # 선택한 팀에 따라 근로자 목록 필터링
            if sel_del_team != "전체 (모든 팀)":
                filtered_del_workers = [w for w in all_workers_del if w["team"] == sel_del_team]
            else:
                filtered_del_workers = all_workers_del
                
            with col_dt2:
                cnt_res = len([w for w in filtered_del_workers if w.get('resignation_date')])
                st.info(f"💡 현재 선택된 **[{sel_del_team}]** 대상 근로자: 총 **{len(filtered_del_workers)}명** (재직 {len(filtered_del_workers) - cnt_res}명 / 퇴사 {cnt_res}명)")
                
            # 옵션 맵 생성 (팀명 / 성명 / 주민번호 / 퇴사 여부 명확 표기)
            del_opt_map = {}
            for w in filtered_del_workers:
                r_tag = f"🔴 퇴사 ({w['resignation_date']})" if w.get('resignation_date') else "재직"
                key_str = f"[{w['team'] or '팀없음'}] {w['name']} (주민번호: {w['worker_id']} / 직종: {w['trade'] or '직종없음'} / {r_tag})"
                del_opt_map[key_str] = w['worker_id']

            # 세션 상태 안전 초기화 및 유지
            if "selected_del_keys_state" not in st.session_state:
                st.session_state["selected_del_keys_state"] = []

            # 콜백 함수 정의 (위젯 상태 변경 예외 차단)
            def cb_sel_all_team(all_keys):
                st.session_state["selected_del_keys_state"] = all_keys

            def cb_sel_resigned_team(res_keys):
                st.session_state["selected_del_keys_state"] = res_keys

            def cb_clear_sel_team():
                st.session_state["selected_del_keys_state"] = []

            # 편리한 버튼식 일괄 선택 조작
            col_b1, col_b2, col_b3 = st.columns([1, 1, 1])
            with col_b1:
                st.button(f"☑️ [{sel_del_team}] 전체 선택", use_container_width=True, key=f"btn_sel_all_{sel_del_team}", on_click=cb_sel_all_team, args=(list(del_opt_map.keys()),))
            with col_b2:
                st.button(f"🔴 [{sel_del_team}] 퇴사자만 선택", use_container_width=True, key=f"btn_sel_resigned_{sel_del_team}", on_click=cb_sel_resigned_team, args=([k for k in del_opt_map.keys() if "🔴 퇴사" in k],))
            with col_b3:
                st.button("🧹 선택 해제", use_container_width=True, key=f"btn_clear_sel_{sel_del_team}", on_click=cb_clear_sel_team)

            # 유효한 기본 선택값 계산
            valid_defaults = [k for k in st.session_state["selected_del_keys_state"] if k in del_opt_map]

            selected_del_keys = st.multiselect(
                "🗑️ 삭제할 근로자를 선택하세요 (여러 명 동시 선택 가능)",
                options=list(del_opt_map.keys()),
                default=valid_defaults,
                key=f"ms_del_workers_{sel_del_team}"
            )
            if selected_del_keys:
                selected_del_ids = [del_opt_map[k] for k in selected_del_keys if k in del_opt_map]
                if selected_del_ids:
                    st.warning(f"⚠️ **경고**: 선택하신 **{len(selected_del_ids)}명**의 근로자를 삭제하시면 대상자의 일별 공수, 수당, 마감 기록 등 관련 데이터가 **영구적으로 함께 삭제**됩니다.")
                    confirm_del_check = st.checkbox(f"위 내용을 확인하였으며, 선택한 {len(selected_del_ids)}명의 근로자를 완전히 삭제합니다.", key=f"checkbox_confirm_del_{sel_del_team}")
                    if confirm_del_check:
                        if st.button(f"🗑️ 선택한 {len(selected_del_ids)}명의 근로자 영구 삭제 실행", type="primary", use_container_width=True, key=f"btn_confirm_del_{sel_del_team}"):
                            try:
                                deleted_cnt = db_manager.delete_multiple_workers(selected_del_ids, st.session_state.user_id)
                                if "selected_ym" in st.session_state:
                                    try:
                                        calc_engine.recalculate_month(st.session_state.selected_ym, st.session_state.user_id)
                                    except Exception:
                                        pass
                                st.session_state["selected_del_keys_state"] = []
                                st.success(f"✅ {deleted_cnt}명의 근로자 및 관련 출역 기록이 성공적으로 영구 삭제되었습니다.")
                                get_attendance_grid.clear()
                                st.rerun()
                            except Exception as del_err:
                                st.error(f"삭제 작업 중 오류 발생: {del_err}")

    # 3-2. 근로자 일괄등록 (요청받은 핵심 신규 기능)
    with tab_w_bulk:
        st.markdown("#### 📥 엑셀 일괄 등록 및 업데이트")
        # 지속성 완료/오류 메시지 표시 (Tab 3-2)
        has_w_msg = False
        if "persistent_worker_success" in st.session_state and st.session_state.persistent_worker_success:
            st.success(st.session_state.persistent_worker_success)
            has_w_msg = True
        if "persistent_worker_error" in st.session_state and st.session_state.persistent_worker_error:
            st.error(st.session_state.persistent_worker_error)
            has_w_msg = True
        if "persistent_worker_warnings" in st.session_state and st.session_state.persistent_worker_warnings:
            st.warning("❌ **엑셀 유효성 검증 오류 발생 (데이터가 반영되지 않았습니다):**")
            for err in st.session_state.persistent_worker_warnings:
                st.write(f"- {err}")
            has_w_msg = True
        if has_w_msg:
            if st.button("❌ 메시지 확인 및 지우기", key="clear_tab3_worker_msg", use_container_width=True):
                st.session_state.persistent_worker_success = None
                st.session_state.persistent_worker_error = None
                st.session_state.persistent_worker_warnings = None
                st.rerun()
        st.write("표준 엑셀 서식을 다운로드하여 다수의 근로자 정보를 한 번에 신규 추가하거나 일괄 수정할 수 있습니다.")
        # 일괄등록 템플릿 파일 생성 및 다운로드 버튼
        template_bytes = excel_io.generate_worker_template()
        st.download_button(
            label="📥 근로자 일괄등록 엑셀 양식 다운로드",
            data=template_bytes,
            file_name="근로자_일괄등록_표준양식.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        st.markdown("---")
        st.write("✍️ **작성한 일괄등록 엑셀 파일 업로드**")
        uploaded_workers_file = st.file_uploader(
            "근로자 엑셀 파일 업로드 (*.xlsx)",
            type=["xlsx"],
            key="workers_bulk_uploader"
        )
        if uploaded_workers_file:
            worker_upload_submit = st.button("🚀 근로자 일괄등록 실행", use_container_width=True)
            if worker_upload_submit:
                with st.spinner("엑셀 양식을 정밀 검증하고 있습니다..."):
                    try:
                        file_bytes = uploaded_workers_file.read()
                        added, updated, errors = excel_io.parse_and_import_workers(
                            file_content=file_bytes,
                            user_id=st.session_state.user_id
                        )
                        if errors:
                            st.session_state.persistent_worker_warnings = errors
                            st.session_state.persistent_worker_success = None
                            st.session_state.persistent_worker_error = None
                            st.rerun()
                        else:
                            st.session_state.persistent_worker_success = f"🎉 **일괄 등록 작업 성공!**\n- 신규 등록 근로자: **{added}명**\n- 정보 수정 근로자: **{updated}명**"
                            st.session_state.persistent_worker_warnings = None
                            st.session_state.persistent_worker_error = None
                            get_attendance_grid.clear()
                            st.rerun()
                    except Exception as e:
                        st.session_state.persistent_worker_error = f"근로자 등록 중 오류 발생: {e}\n\n{traceback.format_exc()}"
                        st.session_state.persistent_worker_success = None
                        st.session_state.persistent_worker_warnings = None
                        st.rerun()
    # 3-3. 개별 근로자 신규추가
    with tab_w_add:
        st.markdown("#### ➕ 단일 근로자 신규 등록")
        is_w_disabled = (st.session_state.user_role == "조회전용")
        with st.form("single_worker_form"):
            col_w1, col_w2 = st.columns(2)
            with col_w1:
                new_w_id = st.text_input("주민번호 (필수)").strip()
                new_w_name = st.text_input("성명 (필수)").strip()
                new_w_team = st.text_input("소속팀 (예: 배관1팀)").strip()
                new_w_trade = st.text_input("직종/공종 (예: 배관공)").strip()
            with col_w2:
                new_w_hire = st.date_input("입사일", datetime.date.today())
                new_w_resign = st.text_input("퇴사일 (YYYY-MM-DD 형식, 현재 재직중인 경우 빈칸)", value="")
                new_w_remarks = st.text_input("비고 (특이사항)").strip()
                new_w_exclude = st.checkbox("주휴/월차 지급 대상에서 제외", value=False)
            w_submit = st.form_submit_button("근로자 등록", disabled=is_w_disabled)
            if w_submit:
                if not new_w_id or not new_w_name:
                    st.error("주민번호와 성명은 필수 입력 항목입니다.")
                else:
                    try:
                        res_date = new_w_resign.strip() if new_w_resign.strip() else None
                        if res_date:
                            # 형식 검증
                            datetime.datetime.strptime(res_date, "%Y-%m-%d")
                        # 단일 근로자 리스트 가공 후 벌크 함수 호출
                        w_data = [{
                            "worker_id": new_w_id,
                            "name": new_w_name,
                            "has_lodging": 0,
                            "has_health": 0,
                            "is_team_leader": 0,
                            "exclude_holiday": 1 if new_w_exclude else 0,
                            "hire_date": new_w_hire.strftime("%Y-%m-%d"),
                            "resignation_date": res_date,
                            "team": new_w_team if new_w_team else None,
                            "trade": new_w_trade if new_w_trade else None,
                            "remarks": new_w_remarks if new_w_remarks else None
                        }]
                        added, updated = db_manager.bulk_insert_workers(w_data, st.session_state.user_id)
                        if added > 0:
                            st.success(f"근로자 {new_w_name} 님이 성공적으로 등록되었습니다.")
                        elif updated > 0:
                            st.success(f"근로자 {new_w_name} 님의 정보가 수정되었습니다.")
                        get_attendance_grid.clear()
                    except Exception as e:
                        st.error(f"등록 실패: {e}")
    # ----------------- Tab 3.5: 변경 이력 조회 -----------------
    with tab_history:
        st.subheader("🔍 공수 변경 및 감사 이력 조회")
        st.write("누가, 언제, 어떤 근로자의 출역/공수/수당 데이터를 변경했는지 모든 감사 이력을 역순으로 추적합니다.")
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            filter_name = st.text_input("성명으로 검색", "").strip()
        with col_f2:
            filter_action = st.text_input("수행 작업으로 검색 (예: 공수 수정, 엑셀)", "").strip()
        logs = db_manager.get_audit_logs(limit=2000)
        if not logs:
            st.info("기록된 감사 로그가 없습니다.")
        else:
            filtered_logs = []
            for log in logs:
                w_name = log.get("worker_name") or ""
                action = log.get("action") or ""
                if filter_name and filter_name not in w_name:
                    continue
                if filter_action and filter_action not in action:
                    continue
                filtered_logs.append({
                    "일시": log["timestamp"],
                    "작업자": log["user_id"],
                    "주민번호": log["worker_id"] or "",
                    "대상 근로자": w_name,
                    "작업내용": action,
                    "변경전 값": log["before_value"] or "",
                    "변경후 값": log["after_value"] or ""
                })
            if not filtered_logs:
                st.warning("검색 조건에 일치하는 변경 이력이 없습니다.")
            else:
                df_logs = pd.DataFrame(filtered_logs)
                st.dataframe(df_logs, use_container_width=True, hide_index=True)

    # ----------------- Tab 3.6: 데이터 백업 및 복원 -----------------
    with tab_backups:
        st.subheader("🗄️ 데이터베이스 자동/수동 백업 및 시점 복원")
        st.write("안전한 데이터 보존을 위해 현재 상태를 즉시 백업하거나, 이전 백업 시점으로 원클릭 복원할 수 있습니다.")
        col_b1, col_b2 = st.columns([1, 2])
        with col_b1:
            st.markdown("##### ➕ 수동 백업 생성")
            st.write("작업 직전에 현재 데이터베이스 상태를 수동으로 백업해두면 안전합니다.")
            if st.button("💾 현재 상태 즉시 백업 생성", use_container_width=True, type="primary"):
                try:
                    new_backup = db_manager.create_manual_backup()
                    st.success(f"수동 백업 파일이 성공적으로 생성되었습니다!\n파일명: {new_backup}")
                    st.rerun()
                except Exception as e:
                    st.error(f"백업 생성 실패: {e}")
        with col_b2:
            st.markdown("##### 📋 저장된 백업 목록 및 복원 실행")
            st.write("복원할 시점의 백업본을 선택하십시오. 복원 실행 시 **현재 상태는 스냅샷 백업(pre_restore)으로 자동 보존**됩니다.")
            backups = db_manager.list_backups()
            if not backups:
                st.info("생성된 백업본이 없습니다.")
            else:
                backup_options = []
                for b in backups:
                    b_type = "수동" if "manual" in b["filename"] else ("복원전" if "pre_restore" in b["filename"] else "자동")
                    backup_options.append(f"{b['datetime']} ({b_type}) - {b['filename']} [{b['size_kb']} KB]")
                selected_opt = st.selectbox("복원 대상 백업 선택", backup_options)
                selected_idx = backup_options.index(selected_opt)
                target_backup = backups[selected_idx]["filename"]
                st.warning("⚠️ **주의**: 복원을 진행하면 현재 데이터베이스가 선택한 백업 시점으로 덮어쓰기 복구됩니다.")
                confirm_restore = st.checkbox("해당 시점으로 데이터베이스 복원을 진행하는 것에 동의합니다.")
                if st.button("🚀 선택한 시점으로 복원 실행", disabled=not confirm_restore, use_container_width=True, type="secondary"):
                    try:
                        db_manager.restore_database(target_backup)
                        st.success("🎉 데이터베이스 복원이 성공적으로 완료되었습니다! 화면을 새로고침합니다.")
                        get_attendance_grid.clear()
                        st.rerun()
                    except Exception as e:
                        st.error(f"복원 실패: {e}")

# ----------------- Tab 4: 마감 및 시스템 설정 -----------------
with tab_settings:
    st.subheader("⚙️ 마감 및 시스템 설정")
    st.markdown("#### 🔒 월말 정산 마감 제어")
    st.write("해당 연월의 마감이 실행되면 더 이상 일지 업로드, 수동 수정 및 공수 재계산 작업이 제한됩니다.")
    is_admin = (st.session_state.user_role == "정성우 대리")
    col_c1, col_c2 = st.columns(2)
    with col_c1:
        if st.button("🔒 해당 월 마감 완료 실행", disabled=(not is_admin or is_locked), use_container_width=True):
            db_manager.lock_month(st.session_state.selected_ym, st.session_state.user_id)
            st.success(f"{st.session_state.selected_ym} 월 마감이 완료되었습니다.")
            st.rerun()
    with col_c2:
        if st.button("🔓 해당 월 마감 해제(락 풀기) 실행", disabled=(not is_admin or not is_locked), use_container_width=True):
            db_manager.unlock_month(st.session_state.selected_ym, st.session_state.user_id)
            st.success(f"{st.session_state.selected_ym} 월 마감이 해제되었습니다.")
            st.rerun()
    st.markdown("---")
    st.markdown("#### 🔑 정성우 대리 로그인 비밀번호 설정")
    st.write("시스템 로그인 시 사용할 비밀번호를 변경합니다. 공란으로 비워둘 시 비밀번호 없이 로그인할 수 있습니다.")
    current_pwd = db_manager.get_system_setting("admin_password", "")
    with st.form("pwd_setting_form"):
        new_pwd_input = st.text_input("새 비밀번호", value=current_pwd, type="password", help="공란 시 비밀번호 없음")
        confirm_pwd_input = st.text_input("비밀번호 확인", value=current_pwd, type="password")
        pwd_submit = st.form_submit_button("비밀번호 설정 저장", disabled=not is_admin)
        if pwd_submit:
            if new_pwd_input != confirm_pwd_input:
                st.error("새 비밀번호와 비밀번호 확인이 일치하지 않습니다.")
            else:
                db_manager.set_system_setting("admin_password", new_pwd_input)
                st.success("비밀번호 설정이 정상적으로 변경 및 저장되었습니다!")
                st.rerun()
    st.markdown("---")
    st.markdown("#### 🗓️ 공휴일 및 셧다운일 등록")
    st.write("주차 및 월차 비례 계산 시 평일 일수에서 제외할 날짜를 직접 등록 및 편집합니다.")
    tab_h_list, tab_h_add = st.tabs(["공휴일 목록 조회", "➕ 공휴일 추가/삭제"])
    with tab_h_list:
        holidays = db_manager.get_holidays()
        if not holidays:
            st.info("등록된 공휴일이 없습니다.")
        else:
            df_holidays = pd.DataFrame(holidays)
            st.dataframe(df_holidays.rename(columns={"date": "날짜 (YYYYMMDD)", "description": "공휴일명"}), use_container_width=True, hide_index=True)
    with tab_h_add:
        with st.form("holiday_form"):
            h_date = st.date_input("공휴일 날짜 선택", datetime.date.today())
            h_desc = st.text_input("공휴일/셧다운 사유 입력").strip()
            h_action = st.selectbox("수행할 작업", ["추가", "삭제"])
            h_submit = st.form_submit_button("공휴일 설정 반영", disabled=not is_admin)
            if h_submit:
                h_date_str = h_date.strftime("%Y%m%d")
                try:
                    if h_action == "추가":
                        if not h_desc:
                            st.error("추가 시 사유를 입력하십시오.")
                        else:
                            db_manager.add_holiday(h_date_str, h_desc)
                            st.success(f"공휴일 {h_date_str} ({h_desc}) 추가 완료!")
                    else:
                        db_manager.remove_holiday(h_date_str)
                        st.success(f"공휴일 {h_date_str} 삭제 완료!")
                except Exception as e:
                    st.error(f"오류: {e}")
    st.markdown("---")
    st.markdown("#### ✨ 주월차 결근 면제일(인정일) 관리")
    st.write("공수가 비어있어도 주차 및 월차 만근 계산 시 결근으로 간주하지 않고 출근한 것처럼(만근 조건에 부합하게) 예외 처리할 특별한 날짜를 지정합니다.")
    tab_e_list, tab_e_add = st.tabs(["결근 면제일 목록 조회", "➕ 면제일 추가/삭제"])
    with tab_e_list:
        excused = db_manager.get_excused_dates()
        if not excused:
            st.info("등록된 주월차 결근 면제일이 없습니다.")
        else:
            df_excused = pd.DataFrame(excused)
            st.dataframe(df_excused.rename(columns={"date": "날짜 (YYYYMMDD)", "description": "면제 사유"}), use_container_width=True, hide_index=True)
    with tab_e_add:
        with st.form("excused_form"):
            e_date = st.date_input("결근 면제일 날짜 선택", datetime.date.today())
            e_desc = st.text_input("결근 면제 사유 입력").strip()
            e_action = st.selectbox("수행할 작업", ["추가", "삭제"], key="excused_action")
            e_submit = st.form_submit_button("면제일 설정 반영", disabled=not is_admin)
            if e_submit:
                e_date_str = e_date.strftime("%Y%m%d")
                try:
                    if e_action == "추가":
                        if not e_desc:
                            st.error("추가 시 사유를 입력하십시오.")
                        else:
                            db_manager.add_excused_date(e_date_str, e_desc)
                            st.success(f"결근 면제일 {e_date_str} ({e_desc}) 추가 완료!")
                            st.rerun()
                    else:
                        db_manager.remove_excused_date(e_date_str)
                        st.success(f"결근 면제일 {e_date_str} 삭제 완료!")
                        st.rerun()
                except Exception as e:
                    st.error(f"오류: {e}")
    st.markdown("---")
    st.markdown("#### 💰 사용자 정의 수당 항목 개설 및 관리")
    st.write("기본 수당(일반, 연장, 숙소, 보건, 팀장) 외에 현장에서 필요로 하는 추가적인 수당 항목(예: 위험수당, 기공수당 등)을 등록하거나 삭제합니다.")
    col_callow1, col_callow2 = st.columns(2)
    with col_callow1:
        st.markdown("##### 📋 개설된 수당 목록")
        cur_customs = db_manager.get_custom_weight_types()
        if not cur_customs:
            st.info("현재 개설된 추가 수당이 없습니다.")
        else:
            df_customs = pd.DataFrame(cur_customs)
            st.dataframe(df_customs.rename(columns={"type_id": "수당코드", "display_name": "수당명"}), use_container_width=True, hide_index=True)
    with col_callow2:
        st.markdown("##### ➕ 수당 개설 / 삭제")
        with st.form("custom_allowance_form"):
            c_allow_id = st.text_input("수당코드 (영문/숫자 권장, 예: risk)", max_chars=20).strip()
            c_allow_name = st.text_input("수당 표기명 (한글 권장, 예: 위험수당)").strip()
            c_allow_action = st.selectbox("수행할 작업", ["추가", "삭제"])
            c_allow_submit = st.form_submit_button("수당 설정 반영", disabled=not is_admin)
            if c_allow_submit:
                if not c_allow_id:
                    st.error("수당코드를 입력하십시오.")
                elif c_allow_action == "추가" and not c_allow_name:
                    st.error("추가 시 수당 표기명을 입력하십시오.")
                else:
                    try:
                        if c_allow_action == "추가":
                            # Validate type_id doesn't match default weight type ids
                            if c_allow_id in ["normal", "overtime", "lodging", "health", "leader", "weekly", "monthly"]:
                                st.error("해당 코드는 시스템 기본 예약어와 겹쳐 사용할 수 없습니다.")
                            else:
                                db_manager.add_custom_weight_type(c_allow_id, c_allow_name)
                                st.success(f"수당 '{c_allow_name}' ({c_allow_id}) 추가 완료!")
                                get_attendance_grid.clear()
                                st.rerun()
                        else:
                            db_manager.delete_custom_weight_type(c_allow_id)
                            st.success(f"수당 코드 '{c_allow_id}' 삭제 완료!")
                            get_attendance_grid.clear()
                            st.rerun()
                    except Exception as e:
                        st.error(f"오류: {e}")
    st.markdown("---")
    st.markdown("#### 🔍 정산 데이터 유효성 검사 (정합성 리포트)")
    st.write("현재 연월 정산 데이터에 존재하는 입력 오류(누락 수당, 초과 공수, 퇴사자 입력 오류 등)를 일괄 감사 검출합니다.")
    audit_submit = st.button("🔍 실시간 감사 감사 실행", use_container_width=True)
    if audit_submit:
        with st.spinner("데이터 무결성을 확인하고 있습니다..."):
            anomalies = validator.audit_monthly_data(st.session_state.selected_ym)
            # A. 출역 누락
            st.markdown("##### ⚠️ 유형 A: 연장공수 단독 입력 오류 (일반공수 0인데 연장공수 발생)")
            if anomalies["omitted_attendance"]:
                st.dataframe(pd.DataFrame(anomalies["omitted_attendance"]), use_container_width=True, hide_index=True)
            else:
                st.success("해당 건이 없습니다.")
            # B. 공수 초과
            st.markdown(f"##### ⚠️ 유형 B: 공수 초과 (일반+연장 > {config.MAX_DAILY_TOTAL_HOURS}시간)")
            if anomalies["excessive_hours"]:
                st.dataframe(pd.DataFrame(anomalies["excessive_hours"]), use_container_width=True, hide_index=True)
            else:
                st.success("해당 건이 없습니다.")
            # C. 퇴사자 입력 오류
            st.markdown("##### ⚠️ 유형 C: 퇴사자 입력 오류 (퇴사일 이후 공수 기록 존재)")
            if anomalies["resigned_attendance"]:
                st.dataframe(pd.DataFrame(anomalies["resigned_attendance"]), use_container_width=True, hide_index=True)
            else:
                st.success("해당 건이 없습니다.")
            # D. 매칭 실패
            st.markdown("##### ⚠️ 유형 D: 엑셀 파일 매칭 실패 이력")
            if anomalies["excel_match_failures"]:
                st.dataframe(pd.DataFrame(anomalies["excel_match_failures"]), use_container_width=True, hide_index=True)
            else:
                st.success("해당 건이 없습니다.")
# ----------------- Tab 5: 도움말 및 시스템 구조 -----------------
with tab_help:
    st.subheader("❓ 도움말 및 시스템 구조")
    help_sub1, help_sub2, help_sub3 = st.tabs([
        "📖 프로그램 사용방법",
        "🏗️ 시스템 모듈 및 파일 구조",
        "🗄️ 데이터베이스 테이블 스키마"
    ])
    with help_sub1:
        st.markdown("""
        ### 📖 노무 관리 시스템 사용 안내
        #### 1. 📅 월간 공수 현황 및 편집
        * **공수 조회**: 대시보드 표에서 전체 인원의 일자별 일반공수 및 각종 수당을 한눈에 조회합니다.
        * **수동 공수 편집**: 편집창 열기 버튼을 클릭하여 특정 인원의 상세 공수나 수당 데이터를 수동으로 편집 및 저장할 수 있습니다.
        * **주월차/보건 적용**: 근로기준법 및 내부 정산 규칙에 따라 주차, 월차, 보건수당을 자동으로 계산하여 데이터베이스에 반영합니다.
        #### 2. 📥 일일 출역일보 업로드
        * **일일출역보 업로드**: 단말기 등에서 추출된 일일 엑셀 파일을 통해 공수를 일괄 등록합니다. 주민번호 또는 이름 매칭을 수행합니다.
        * **선택적 공수 일괄 등록 (덮어쓰기)**: 다수의 인원/날짜 데이터를 일괄 덮어씁니다. 파일에 명시된 열(일반, 연장, 숙소 등)만 덮어쓰고 빈 열은 기존 수치를 유지합니다.
        #### 3. 👤 근로자 관리 및 일괄등록
        * **근로자 목록**: 등록된 모든 노무 인력 정보(주민번호, 성명, 소속팀, 직종, 입퇴사일, 비고 등)를 직접 편집하고 저장합니다.
        * **엑셀 일괄 등록**: 근로자 일괄등록 서식을 다운로드하여 다수의 근로자를 빠르게 신규 추가 또는 수정할 수 있습니다.
        * **단일 등록**: 개별 신규 입사 근로자를 직접 폼으로 타이핑하여 등록합니다.
        #### 4. ⚙️ 마감 및 시스템 설정
        * **월말 정산 마감**: 해당 월의 정산이 완료되면 마감을 실행하여 데이터가 임의로 수정되거나 재계산되는 것을 차단합니다.
        * **비밀번호 변경**: 로그인 비밀번호를 설정할 수 있습니다. (공란인 경우 암호 없이 즉시 로그인 가능)
        * **공휴일/수당 항목 개설**: 주차/월차 비례 계산에서 제외할 공휴일을 지정하거나, 기본 수당 외의 추가 수당(예: 위험수당 등)을 개설/관리합니다.
        * **정합성 리포트**: 공수 누락, 한도 초과(2.5시간 초과), 퇴사자 입력 오류 등을 실시간 검출합니다.
        """)
    with help_sub2:
        st.markdown("""
        ### 🏗️ 시스템 아키텍처 및 모듈 구성
        본 시스템은 **계층형 아키텍처 (Layered Architecture)**로 설계되어 화면 제어, 비즈니스 연산, 데이터 액세스가 깔끔하게 분리되어 있습니다.
        #### 📁 핵심 모듈 및 파일 목록
        * **`app.py`** : Streamlit 기반의 사용자 인터페이스 및 권한 제어를 담당하는 메인 파일입니다.
        * **`db_manager.py`** : SQLite 연결, 트랜잭션, 감사 로그(Audit Logs), 비밀번호 설정 관리 및 자동 백업(30일 만료)을 전담합니다.
        * **`calc_engine.py`** : 주차(평일 근무 비례), 월차(22일 이상 만근 시 1일 부여), 보건수당(여성 근로자 중 월 15일 이상 근로 시 월말에 1일 자동 부여) 연산 엔진입니다.
        * **`excel_io.py`** : 엑셀 파일 복구(XML 손상 우회), 템플릿(근로자, 일일출역, 일괄공수) 생성 및 다중 별칭 지원 선택적 덮어쓰기 파서입니다.
        * **`validator.py`** : 정산 전 데이터 무결성을 검사하는 백엔드 감사(Audit) 모듈입니다.
        * **`config.py`** : 정산에 활용되는 각종 고정 상수 및 데이터베이스 경로 설정을 관리합니다.
        * **`build.py`** : PyInstaller 기반의 원클릭 빌드 패키징 스크립트입니다.
        """)
    with help_sub3:
        st.markdown("""
        ### 🗄️ 데이터베이스 테이블 스키마 구성 (SQLite)
        #### 1. `workers` (근로자 마스터 테이블)
        * `worker_id` (TEXT, PK): 주민등록번호 (고유식별자)
        * `name` (TEXT): 성명
        * `hire_date` (TEXT): 입사일 (YYYY-MM-DD)
        * `resignation_date` (TEXT): 퇴사일 (YYYY-MM-DD, 선택)
        * `team` (TEXT): 소속팀
        * `trade` (TEXT): 직종/공종
        * `remarks` (TEXT): 비고 및 특이사항
        #### 2. `daily_attendance` (일자별 공수 및 수당 상세 테이블)
        * `date` (TEXT, PK): 날짜 (YYYYMMDD)
        * `worker_id` (TEXT, PK, FK): 주민등록번호
        * `normal_weight` (REAL): 일반공수 (0.0 ~ 2.5)
        * `overtime_weight` (REAL): 연장공수
        * `lodging_weight` (REAL): 숙소수당
        * `health_weight` (REAL): 보건수당
        * `leader_weight` (REAL): 팀장수당
        * `weekly_holiday` (REAL): 주차 가중치
        * `monthly_holiday` (REAL): 월차 가중치
        * `status` (TEXT): 출퇴근 상태 ('출근', '휴무' 등)
        * `version` (INTEGER): 버전 카운트 (낙관적 락 제어용)
        #### 3. `monthly_status` (월별 공수 요약 테이블)
        * `year_month` (TEXT, PK): 연월 (YYYYMM)
        * `worker_id` (TEXT, PK, FK): 주민등록번호
        * `worked_days` (REAL): 누적 근로일수
        * `weekly_holidays` (REAL): 누적 주차일수
        * `monthly_holidays` (REAL): 누적 월차일수
        #### 4. `system_settings` (시스템 전역 설정 테이블)
        * `setting_key` (TEXT, PK): 설정 키 (예: `admin_password`)
        * `setting_value` (TEXT): 설정 값
        """)