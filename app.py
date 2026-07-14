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
    cursor.execute("SELECT worker_id, name, team, trade FROM workers ORDER BY name ASC;")
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
    st.write("모든 근로자의 공수 및 수당을 페이지 분할 없이 한 화면에서 입력/수정할 수 있습니다.")
    # 1. 차원 선택
    choices = ["일반공수", "출역구분", "연장공수", "전월 누락공수", "차감공수", "주차수당", "월차수당", "숙소수당", "보건수당", "팀장수당"] + [f"{cat['display_name']}수당" for cat in custom_allowances]
    initial_idx = choices.index(default_edit_dim) if default_edit_dim in choices else 0
    edit_dim = st.radio(
        "📍 편집할 공수 차원 선택",
        choices,
        index=initial_idx,
        horizontal=True,
        key="dialog_edit_dim"
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
    # 2. 데이터 그리드 빌드 (전체 근로자 대상)
    grid_data = []
    for w in workers:
        row = {
            "주민번호": w["worker_id"],
            "성명": w["name"],
            "소속팀": w["team"] or "",
            "직종": w["trade"] or ""
        }
        tot_normal = 0.0
        tot_overtime = 0.0
        tot_prev_missing = 0.0
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
            tot_weekly += weekly_val
            tot_monthly += monthly_val
            tot_lodging += lodging_val
            tot_health += health_val
            tot_leader += leader_val
            tot_custom += custom_val
            if key in versions:
                val = versions[key].get(dim_key)
                if dim_key == "status":
                    row[day_col] = str(val) if (val and val != "휴무" and val != "None") else ""
                else:
                    row[day_col] = float(val) if val is not None else 0.0
            else:
                row[day_col] = "" if dim_key == "status" else 0.0
        # 우측 합계 열 기입 (편집할 때도 읽기 전용 참고용)
        row["출역"] = tot_normal
        row["연장"] = tot_overtime
        row["누락"] = tot_prev_missing
        row["주차"] = tot_weekly
        row["월차"] = tot_monthly
        if not hide_allowances:
            row["숙소"] = tot_lodging
            row["보건"] = tot_health
            row["팀장"] = tot_leader
            row["기타"] = tot_custom
            row["총공수"] = tot_normal + tot_overtime + tot_prev_missing + tot_weekly + tot_monthly + tot_lodging + tot_health + tot_leader + tot_custom
        else:
            row["총공수"] = tot_normal + tot_overtime + tot_prev_missing + tot_weekly + tot_monthly
        grid_data.append(row)
    # 일일 합계 행 계산 및 추가
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
    # 비활성화할 컬럼 리스트 정의
    disabled_cols = ["주민번호", "성명", "소속팀", "직종", "출역", "연장", "주차", "월차"]
    if not hide_allowances:
        disabled_cols += ["숙소", "보건", "팀장", "기타"]
    disabled_cols += ["총공수"]
    # 틀고정 및 소수점 포맷 지정 설정 컬럼 빌드
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
    editor_key = f"dialog_editor_{ym}_{edit_dim}"
    edited_df = st.data_editor(
        df_grid, # 편집 모드이므로 Styler 버그 방지를 위해 raw df 전달
        disabled=disabled_cols,
        column_config=col_config,
        key=editor_key,
        use_container_width=True,
        hide_index=True
    )
    st.markdown("---")
    col_db1, col_db2 = st.columns([1, 1])
    with col_db1:
        if st.button("💾 변경 사항 저장 및 닫기", use_container_width=True, type="primary"):
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
                        # DB 매칭을 위해 원본 근로자 정보 가져오기
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
                                    if new_weight < config.ALLOWED_MIN_WEIGHT or new_weight > config.ALLOWED_MAX_WEIGHT:
                                        raise ValueError(f"값 범위 제약(0.0 ~ 2.0)을 벗어났습니다. 입력값: {new_weight}")
                            except ValueError as val_err:
                                st.error(f"입력 오류: {col_name}의 값이 올바르지 않습니다. ({val_err})")
                                st.stop()
                            cursor.execute("""
                                SELECT normal_weight, overtime_weight, lodging_weight, health_weight, leader_weight, version
                                FROM daily_attendance
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
                                # 일반공수 수정 시에만 출역 구분 자동 전환
                                if dim_key == "normal_weight":
                                    if record["normal_weight"] > 0.0:
                                        record["status"] = "출근"
                                    else:
                                        # 수동으로 지정한 내역(병가, 휴가, 결근, 공가 등)이 지워지지 않도록
                                        # 기존 구분이 '출근'이었거나 비어있던 경우에만 '휴무'로 전환합니다.
                                        cur_status = record.get("status")
                                        if cur_status == "출근" or not cur_status or cur_status == "None":
                                            record["status"] = "휴무"
                                records_to_update.append(record)
                    if records_to_update:
                        db_manager.save_attendance_bulk(records_to_update, st.session_state.user_id)
                    st.success("성공적으로 변경 사항을 저장했습니다!")
                    get_attendance_grid.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"저장 중 오류 발생: {e}")
                finally:
                    conn.close()
            else:
                st.info("수정된 행이 없어 그냥 종료합니다.")
                st.rerun()
    with col_db2:
        if st.button("❌ 닫기 (저장하지 않음)", use_container_width=True):
            st.rerun()
# ----------------- Tab 1: 월간 공수 현황 및 편집 -----------------
with tab_grid:
    st.subheader("📅 월간 공수 판넬")
    # 1. 조회 정보 로드
    workers, attendance, dates, days, versions, custom_allowances = get_attendance_grid(st.session_state.selected_ym)
    if not workers:
        st.warning("등록된 근로자가 없습니다. '근로자 관리 및 일괄등록' 탭에서 근로자를 먼저 등록해 주세요.")
    else:
        # 필터링 및 편집 창 열기 설정
        col_f1, col_f2, col_f3 = st.columns([1, 1, 1])
        # 1-1. 팀 필터
        teams = sorted(list(set([w["team"] for w in workers if w["team"]])))
        with col_f1:
            sel_team = st.selectbox("팀 필터 (전체는 공란)", ["전체"] + teams)
        # 1-2. 직종 필터
        trades = sorted(list(set([w["trade"] for w in workers if w["trade"]])))
        with col_f2:
            sel_trade = st.selectbox("직종 필터 (전체는 공란)", ["전체"] + trades)
        # 1-3. 편집창 오픈 버튼 배치
        with col_f3:
            open_edit = st.button("✏️ 전체 근로자 공수 편집창 열기", type="primary", use_container_width=True, disabled=is_locked)
        # 필터링 적용
        filtered_workers = workers
        if sel_team != "전체":
            filtered_workers = [w for w in filtered_workers if w["team"] == sel_team]
        if sel_trade != "전체":
            filtered_workers = [w for w in filtered_workers if w["trade"] == sel_trade]
        # 2. 편집 차원 선택 및 숨김 체크박스 레이아웃
        choices = ["총 공수", "일반공수", "출역구분", "연장공수", "전월 누락공수", "차감공수", "주차수당", "월차수당", "숙소수당", "보건수당", "팀장수당"] + [f"{cat['display_name']}수당" for cat in custom_allowances]
        col_dim_radio, col_dim_chk = st.columns([4, 1])
        with col_dim_radio:
            edit_dim = st.radio(
                "📍 조회 및 편집할 공수 차원 선택",
                choices,
                horizontal=True
            )
        with col_dim_chk:
            hide_allowances = st.checkbox("숨김 설정: 숙소/보건/팀장/기타 열 제외", value=False)
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
        # 공휴일 목록 조회 (토/일/공휴일 표시용 헤더 빌드)
        holidays_list = db_manager.get_holidays(st.session_state.selected_ym)
        holiday_dates = [h["date"] for h in holidays_list]
        # 헤더 리스트 빌드 (이모지 기호는 제거하고 깔끔한 일자만 표시)
        styled_days = []
        for d_str in dates:
            day_num = int(d_str[6:8])
            styled_days.append(f"{day_num}일")
        # 편집 모달 열기 요청 처리
        if open_edit:
            show_edit_dialog(
                ym=st.session_state.selected_ym,
                workers=filtered_workers,
                dates=dates,
                styled_days=styled_days,
                versions=versions,
                custom_allowances=custom_allowances,
                hide_allowances=hide_allowances,
                default_edit_dim=edit_dim
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
            # 일일 합계 행은 전체 볼드 및 다크 버전 배경색 처리
            for idx in df.index:
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
            "소속팀": st.column_config.TextColumn("소속팀", pinned=True),
            "직종": st.column_config.TextColumn("직종", pinned=True),
        }
        # 일자별 컬럼 소수점 2자리 지정
        for day_col in styled_days:
            col_config[day_col] = st.column_config.NumberColumn(day_col, format="%.2f")
        # 우측 합산 요약 컬럼 소수점 2자리 지정
        summary_num_cols = ["출역", "연장", "누락", "차감", "주차", "월차", "숙소", "보건", "팀장", "기타", "총공수"]
        for col in summary_num_cols:
            col_config[col] = st.column_config.NumberColumn(col, format="%.2f")
        # 메인 그리드는 모든 열 비활성화 (조회 전용)
        disabled_cols = list(df_grid.columns)
        edited_df = st.data_editor(
            styled_df,
            disabled=disabled_cols,
            column_config=col_config,
            key=editor_key,
            use_container_width=True,
            hide_index=True
        )
        st.markdown("---")
        # 5. 월말 집계 피벗 데이터 선계산
        pivot_rows = []
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
            row_sum = {
                "주민번호": w["worker_id"],
                "성명": w["name"],
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
                        custom_val += float(rec.get("custom_" + cat["type_id"], 0.0))
                # 셀 표시는 숨김 설정 체크 여부에 따라 총공수 연산 적용
                if not hide_allowances:
                    row_sum[day_col] = normal_val + over_val + prev_missing_val - deduction_val + weekly_val + monthly_val + lodging_val + health_val + leader_val + custom_val
                else:
                    row_sum[day_col] = normal_val + over_val + prev_missing_val - deduction_val + weekly_val + monthly_val
                tot_custom += custom_val
                tot_normal += normal_val
                tot_overtime += over_val
                tot_prev_missing += prev_missing_val
                tot_deduction += deduction_val
                tot_weekly += weekly_val
                tot_monthly += monthly_val
                tot_lodging += lodging_val
                tot_health += health_val
                tot_leader += leader_val
            # 합산 열 기입
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
                row_sum["기타"] = tot_custom
                row_sum["총공수"] = tot_normal + tot_overtime + tot_prev_missing - tot_deduction + tot_weekly + tot_monthly + tot_lodging + tot_health + tot_leader + tot_custom
            else:
                row_sum["총공수"] = tot_normal + tot_overtime + tot_prev_missing - tot_deduction + tot_weekly + tot_monthly
            pivot_rows.append(row_sum)
        # df_pivot_out에 합계 행 추가 및 반올림
        if pivot_rows:
            p_total = {
                "주민번호": "일일 합계",
                "성명": "",
                "팀": "",
                "직종": ""
            }
            p_total["출역"] = round(sum(r["출역"] for r in pivot_rows), 2)
            p_total["연장"] = round(sum(r["연장"] for r in pivot_rows), 2)
            p_total["누락"] = round(sum(r["누락"] for r in pivot_rows), 2)
            p_total["차감"] = round(sum(r["차감"] for r in pivot_rows), 2)
            p_total["주차"] = round(sum(r["주차"] for r in pivot_rows), 2)
            p_total["월차"] = round(sum(r["월차"] for r in pivot_rows), 2)
            if not hide_allowances:
                p_total["숙소"] = round(sum(r["숙소"] for r in pivot_rows), 2)
                p_total["보건"] = round(sum(r["보건"] for r in pivot_rows), 2)
                p_total["팀장"] = round(sum(r["팀장"] for r in pivot_rows), 2)
                p_total["기타"] = round(sum(r["기타"] for r in pivot_rows), 2)
            p_total["총공수"] = round(sum(r["총공수"] for r in pivot_rows), 2)
            # 일자별 컬럼이 있으면 일자별 합계도 채움
            for day_col in all_days:
                if day_col in pivot_rows[0]:
                    p_total[day_col] = round(sum(r[day_col] for r in pivot_rows), 2)
            import copy
            pivot_rows_with_total = copy.deepcopy(pivot_rows)
            pivot_rows_with_total.insert(0, copy.deepcopy(p_total))
            pivot_rows_with_total.append(copy.deepcopy(p_total))
            df_pivot_out = pd.DataFrame(pivot_rows_with_total)
        else:
            df_pivot_out = pd.DataFrame(pivot_rows)
        # 6. 재계산 / 다운로드 버튼 레이아웃
        col_btn1, col_btn2 = st.columns([1, 2])
        # 6-1. 주월차/보건 적용
        with col_btn1:
            calc_submit = st.button("🔄 주월차/보건 적용", disabled=is_locked, use_container_width=True)
            if calc_submit:
                with st.spinner("해당 월의 주휴(주차)/월차 및 보건 수당을 산출하여 적용하고 있습니다..."):
                    try:
                        calc_engine.recalculate_month(st.session_state.selected_ym, st.session_state.user_id)
                        st.success("주월차 및 보건 수당 적용이 성공적으로 완료되었습니다!")
                        get_attendance_grid.clear()
                        st.rerun()
                    except Exception as e:
                        st.error(f"주월차/보건 적용 중 오류 발생: {e}")
        # 6-2. 엑셀 리포트 출력 다운로드
        with col_btn2:
            if not df_pivot_out.empty:
                excel_bytes = excel_io.export_monthly_excel(df_pivot_out, st.session_state.selected_ym)
                st.download_button(
                     label="📤 월말 공수 집계표 다운로드 (Excel)",
                     data=excel_bytes,
                     file_name=f"대선이엔씨_공수정산표_{st.session_state.selected_ym}.xlsx",
                     mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                     use_container_width=True
                )
        # 7. 월말 집계 요약 미리보기 테이블 표시
        st.markdown("##### 📊 월말 집계 요약 미리보기")
        summary_cols = ["주민번호", "성명", "팀", "직종", "출역", "연장", "주차", "월차"]
        if not hide_allowances:
             summary_cols += ["숙소", "보건", "팀장", "기타"]
        summary_cols += ["총공수"]
        def style_summary(df):
            style_df = pd.DataFrame('', index=df.index, columns=df.columns)
            for idx in df.index:
                if df.loc[idx, "주민번호"] == "일일 합계":
                    for col in df.columns:
                        style_df.loc[idx, col] = 'color: #F8FAFC; font-weight: bold; background-color: #1E293B; font-size: 13px;'
            return style_df
        styled_summary_df = df_pivot_out[summary_cols].style.apply(style_summary, axis=None)
        st.dataframe(styled_summary_df, column_config=col_config, use_container_width=True, hide_index=True)
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
    sub_tab_daily, sub_tab_bulk, sub_tab_hyundai, sub_tab_check = st.tabs([
        "일일출역보 엑셀 업로드 (기본)",
        "선택적 공수 일괄 등록 (덮어쓰기)",
        "현대건설 샤힌현장 일일출역 연동",
        "✅ 일별 입력 체크리스트"
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
# ----------------- Tab 3: 근로자 관리 및 일괄등록 -----------------
with tab_workers:
    st.subheader("👤 근로자 관리 및 일괄등록")
    tab_w_list, tab_w_bulk, tab_w_add = st.tabs(["근로자 목록 조회", "📥 근로자 일괄등록", "➕ 개별 근로자 신규추가"])
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
            # 한글 이름으로 컬럼 매핑
            col_renames = {
                "worker_id": "주민번호",
                "name": "성명",
                "team": "소속팀",
                "trade": "직종/공종",
                "hire_date": "입사일",
                "resignation_date": "퇴사일",
                "remarks": "비고"
            }
            df_workers_renamed = df_workers.rename(columns=col_renames)
            # 컬럼 순서 및 구성 설정
            col_order = ["주민번호", "성명", "소속팀", "직종/공종", "입사일", "퇴사일", "비고"]
            df_workers_renamed = df_workers_renamed[col_order]
            col_config = {
                "주민번호": st.column_config.TextColumn("주민번호", disabled=False),
                "성명": st.column_config.TextColumn("성명"),
                "소속팀": st.column_config.TextColumn("소속팀"),
                "직종/공종": st.column_config.TextColumn("직종/공종"),
                "입사일": st.column_config.TextColumn("입사일 (YYYY-MM-DD)"),
                "퇴사일": st.column_config.TextColumn("퇴사일 (YYYY-MM-DD)"),
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
                                SET name = ?, team = ?, trade = ?, has_lodging = ?, has_health = ?, is_team_leader = ?, hire_date = ?, resignation_date = ?, remarks = ?
                                WHERE worker_id = ?;
                            """, (name, team, trade, has_lodging, has_health, is_team_leader, hire_date, resignation_date, remarks, new_worker_id))
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
                        st.success("근로자 정보 및 주민번호 변경사항이 성공적으로 저장되었습니다!")
                        get_attendance_grid.clear()
                        st.rerun()
                    except Exception as e:
                        conn.rollback()
                        st.error(f"저장 중 오류 발생: {e}")
                    finally:
                        conn.execute("PRAGMA foreign_keys = ON;")
                        conn.close()
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