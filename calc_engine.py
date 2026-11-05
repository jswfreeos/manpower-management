# calc_engine.py
"""
[2단계] 공휴일 연동 실제 출근일 기반 수당/일할계산 엔진
"""
import datetime
import calendar
import sqlite3
import traceback
from typing import List, Dict, Any
import config
import db_manager

# 개인 사정에 의해 공수가 0이어도 주월차 산정 시 인정해줄 출역 구분 목록
EXCUSED_STATUSES = {"공가", "병가", "인정", "대휴", "경조", "휴가"}

def get_days_in_month(year_month: str) -> List[str]:
    """YYYY-MM 형식의 연월에 대해 모든 일자(YYYYMMDD) 리스트를 반환합니다."""
    year, month = map(int, year_month.split("-"))
    num_days = calendar.monthrange(year, month)[1]
    return [f"{year}{month:02d}{day:02d}" for day in range(1, num_days + 1)]

def is_working_weekday(date_str: str, holiday_dates: List[str]) -> bool:
    """해당 일자가 공휴일이나 주말이 아닌 실제 출근 대상 평일(월~금)인지 판별합니다."""
    # 주말 여부 확인 (0: 월, 6: 일)
    year = int(date_str[:4])
    month = int(date_str[4:6])
    day = int(date_str[6:8])
    dt = datetime.date(year, month, day)
    
    if dt.weekday() >= 5: # 토, 일
        return False
        
    # 공휴일 여부 확인
    if date_str in holiday_dates:
        return False
        
    return True

def recalculate_month(year_month: str, user_id: str):
    """
    해당 월의 모든 근로자 출역 데이터에 대해 주차/월차 비례 계산 및 입퇴사자 초기화 연산을 일괄 수행합니다.
    """
    # 1. 마감 상태 검사
    if db_manager.is_month_locked(year_month):
        raise PermissionError(f"{year_month} 월은 이미 마감되어 공수를 재계산할 수 없습니다.")
        
    conn = db_manager.get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 해당 월의 공휴일 및 주월차 인정일 목록 조회 (결근 계산 예외 처리용)
        holidays_list = db_manager.get_holidays(year_month)
        excused_list = db_manager.get_excused_dates(year_month)
        holiday_dates = [h["date"] for h in holidays_list] + [e["date"] for e in excused_list]
        
        # 이전 월 YYYYMM 계산 및 데이터 존재 여부 확인 (최초 기동/데이터 누락 시의 첫 주차 연산 가드)
        ym_dt = datetime.datetime.strptime(year_month, "%Y-%m")
        prev_ym_dt = ym_dt - datetime.timedelta(days=15)
        prev_ym_str = prev_ym_dt.strftime("%Y%m")
        cursor.execute("SELECT COUNT(*) as count FROM daily_attendance WHERE substr(date, 1, 6) = ?;", (prev_ym_str,))
        prev_month_has_data = cursor.fetchone()["count"] > 0
        
        # 모든 근로자 조회
        cursor.execute("SELECT * FROM workers;")
        workers = [dict(w) for w in cursor.fetchall()]
        
        # 해당 월의 일자 리스트
        date_list = get_days_in_month(year_month)
        
        for worker in workers:
            worker_id = worker["worker_id"]
            hire_date = worker["hire_date"].replace("-", "").replace("/", "")
            resignation_date = worker["resignation_date"].replace("-", "").replace("/", "") if worker["resignation_date"] else None
            exclude_holiday = worker.get("exclude_holiday", 0) == 1
            
            # 만약 주월차 제외 근로자라면 이번 달의 기입된 모든 주차/월차 수치를 원천 클린업(0.0) 처리
            if exclude_holiday:
                cursor.execute("""
                    UPDATE daily_attendance
                    SET weekly_holiday = 0.0, monthly_holiday = 0.0,
                        is_weekly_manual = 0, is_monthly_manual = 0,
                        version = version + 1
                    WHERE worker_id = ? AND substr(date, 1, 6) = ?
                      AND (weekly_holiday != 0.0 OR monthly_holiday != 0.0 OR is_weekly_manual != 0 OR is_monthly_manual != 0);
                """, (worker_id, year_month.replace("-", "")))
            
            # 해당 근로자의 이번 달 기존 일일 출역 데이터 로드
            cursor.execute("""
                SELECT * FROM daily_attendance 
                WHERE worker_id = ? AND substr(date, 1, 6) = ?;
            """, (worker_id, year_month.replace("-", "")))
            attendance_records = {r["date"]: dict(r) for r in cursor.fetchall()}
            
            for date_str in date_list:
                record = attendance_records.get(date_str)
                if not record:
                    # 기록이 아예 없는 경우는 계산에서 제외 (필요시 새로 생성하지 않고 기존 기록 대상으로만 연산)
                    continue
                    
                version = record["version"]
                
                # 사용자가 직접 입력한 출역 데이터 및 누락 공수는 시스템이 임의로 삭제/초기화하지 않습니다.
                pass
            
            # --- 2. 주차 계산 시작 ---
            # 해당 월의 모든 일요일 목록 추출
            sundays_to_process = set()
            for date_str in date_list:
                dt = datetime.date(int(date_str[:4]), int(date_str[4:6]), int(date_str[6:8]))
                if dt.weekday() == 6:  # Sunday
                    sundays_to_process.add(dt)
            
            # 신규 입사일 주 / 중도 퇴사일 주의 일요일 추가 수집
            for dt_str in [hire_date, resignation_date]:
                if dt_str and dt_str[:6] == year_month.replace("-", ""):
                    dt = datetime.date(int(dt_str[:4]), int(dt_str[4:6]), int(dt_str[6:8]))
                    days_to_sunday = 6 - dt.weekday()
                    sun_dt = dt + datetime.timedelta(days=days_to_sunday)
                    sundays_to_process.add(sun_dt)
                    
            # 헬퍼 함수 정의
            def get_db_record(w_id, d_str):
                cursor.execute("""
                    SELECT normal_weight, weekly_holiday, monthly_holiday, is_weekly_manual, is_monthly_manual, status, version 
                    FROM daily_attendance 
                    WHERE worker_id = ? AND date = ?;
                """, (w_id, d_str))
                r = cursor.fetchone()
                return dict(r) if r else None
            
            # 주차 값 계산 및 반영
            for sun_dt in sorted(list(sundays_to_process)):
                sun_str = sun_dt.strftime("%Y%m%d")
                
                # 해당 주의 평일 일자 (월~금)
                week_days = []
                for i in range(5):
                    wd_dt = sun_dt - datetime.timedelta(days=(6 - i))
                    week_days.append(wd_dt.strftime("%Y%m%d"))
                
                # 이번 주의 범위
                week_start_str = (sun_dt - datetime.timedelta(days=6)).strftime("%Y%m%d")
                week_end_str = sun_dt.strftime("%Y%m%d")
                
                # 주의 시작(월요일)이 퇴사일보다 늦거나, 주의 끝(일요일)이 입사일보다 빠른 경우 완전히 계약기간 외이므로 스킵
                if week_end_str < hire_date or (resignation_date and week_start_str > resignation_date):
                    if sun_str[:6] == year_month.replace("-", ""):
                        rec = attendance_records.get(sun_str)
                        if rec and rec["is_weekly_manual"] == 0 and rec["weekly_holiday"] != 0.0:
                            cursor.execute("UPDATE daily_attendance SET weekly_holiday = 0.0, version = version + 1 WHERE date = ? AND worker_id = ?;", (sun_str, worker_id))
                            rec["weekly_holiday"] = 0.0
                    continue
                
                is_new_hire_this_week = (week_start_str <= hire_date <= week_end_str)
                is_resigned_this_week = (resignation_date is not None and week_start_str <= resignation_date <= week_end_str)
                
                # 출근 평일 수 카운트 (실제 출근했거나, 구분 값이 인정 상태이거나, 공휴일/면제일인 경우 인정)
                worked_weekdays = 0
                for d_str in week_days:
                    rec = attendance_records.get(d_str)
                    if not rec and (d_str < date_list[0] or d_str > date_list[-1]):
                        rec = get_db_record(worker_id, d_str)
                    if (rec and ((rec["normal_weight"] or 0.0) > 0.0 or rec.get("status") in EXCUSED_STATUSES or (rec.get("monthly_holiday", 0.0) or 0.0) > 0.0)) or (d_str in holiday_dates):
                        worked_weekdays += 1
                
                if is_resigned_this_week:
                    # 중도 퇴사 주: 평일 출근일수 당 0.2씩 계산한 주차가 퇴사일에 달림
                    weekly_val = 0.0 if exclude_holiday else round(0.2 * worked_weekdays, 2)
                    if resignation_date[:6] == year_month.replace("-", ""):
                        res_rec = attendance_records.get(resignation_date)
                        if res_rec:
                            if res_rec["is_weekly_manual"] == 0 and res_rec["weekly_holiday"] != weekly_val:
                                before_val = f"주차:{res_rec['weekly_holiday']}"
                                cursor.execute("UPDATE daily_attendance SET weekly_holiday = ?, version = version + 1 WHERE date = ? AND worker_id = ?;", (weekly_val, resignation_date, worker_id))
                                res_rec["weekly_holiday"] = weekly_val
                                db_manager.log_audit("SYSTEM", worker_id, f"{resignation_date} 퇴사자 주차 반영", before_val, f"주차:{weekly_val}", conn=conn)
                        else:
                            if weekly_val > 0.0:
                                cursor.execute("""
                                    INSERT INTO daily_attendance (date, worker_id, normal_weight, overtime_weight, lodging_weight, health_weight, leader_weight, weekly_holiday, monthly_holiday, status, is_weekly_manual, is_monthly_manual, version)
                                    VALUES (?, ?, 0.0, 0.0, 0.0, 0.0, 0.0, ?, 0.0, '휴무', 0, 0, 1);
                                """, (resignation_date, worker_id, weekly_val))
                                db_manager.log_audit("SYSTEM", worker_id, f"{resignation_date} 퇴사자 주차 신규 삽입 반영", "주차:없음", f"주차:{weekly_val}", conn=conn)
                                attendance_records[resignation_date] = {
                                    "date": resignation_date, "worker_id": worker_id, "normal_weight": 0.0, "overtime_weight": 0.0,
                                    "lodging_weight": 0.0, "health_weight": 0.0, "leader_weight": 0.0, "weekly_holiday": weekly_val,
                                    "monthly_holiday": 0.0, "status": "휴무", "is_weekly_manual": 0, "is_monthly_manual": 0, "version": 1
                                }
                    
                    # 일요일 주차는 0.0 (단, 퇴사일이 일요일인 경우는 계산된 주차가 유지되어야 하므로 제외)
                    if sun_str[:6] == year_month.replace("-", "") and sun_str != resignation_date:
                        sun_rec = attendance_records.get(sun_str)
                        if sun_rec and sun_rec["is_weekly_manual"] == 0:
                            if sun_rec["weekly_holiday"] != 0.0:
                                cursor.execute("UPDATE daily_attendance SET weekly_holiday = 0.0, version = version + 1 WHERE date = ? AND worker_id = ?;", (sun_str, worker_id))
                                sun_rec["weekly_holiday"] = 0.0
                                
                elif is_new_hire_this_week:
                    # 신규 입사 주: 평일 출근일수 당 0.2씩 계산하여 일요일에 달림
                    weekly_val = 0.0 if exclude_holiday else round(0.2 * worked_weekdays, 2)
                    if sun_str[:6] == year_month.replace("-", ""):
                        sun_rec = attendance_records.get(sun_str)
                        if sun_rec:
                            if sun_rec["is_weekly_manual"] == 0 and sun_rec["weekly_holiday"] != weekly_val:
                                before_val = f"주차:{sun_rec['weekly_holiday']}"
                                cursor.execute("UPDATE daily_attendance SET weekly_holiday = ?, version = version + 1 WHERE date = ? AND worker_id = ?;", (weekly_val, sun_str, worker_id))
                                sun_rec["weekly_holiday"] = weekly_val
                                db_manager.log_audit("SYSTEM", worker_id, f"{sun_str} 신규입사자 주차 반영", before_val, f"주차:{weekly_val}", conn=conn)
                        else:
                            if weekly_val > 0.0:
                                cursor.execute("""
                                    INSERT INTO daily_attendance (date, worker_id, normal_weight, overtime_weight, lodging_weight, health_weight, leader_weight, weekly_holiday, monthly_holiday, status, is_weekly_manual, is_monthly_manual, version)
                                    VALUES (?, ?, 0.0, 0.0, 0.0, 0.0, 0.0, ?, 0.0, '휴무', 0, 0, 1);
                                """, (sun_str, worker_id, weekly_val))
                                db_manager.log_audit("SYSTEM", worker_id, f"{sun_str} 신규입사자 주차 신규 삽입 반영", "주차:없음", f"주차:{weekly_val}", conn=conn)
                                attendance_records[sun_str] = {
                                    "date": sun_str, "worker_id": worker_id, "normal_weight": 0.0, "overtime_weight": 0.0,
                                    "lodging_weight": 0.0, "health_weight": 0.0, "leader_weight": 0.0, "weekly_holiday": weekly_val,
                                    "monthly_holiday": 0.0, "status": "휴무", "is_weekly_manual": 0, "is_monthly_manual": 0, "version": 1
                                }
                                
                else:
                    # 그 외 모든 근로자: 평일 결근 시 0.0, 평일 만근 시 1.0
                    is_perfect = True
                    for d_str in week_days:
                        if is_working_weekday(d_str, holiday_dates):
                            # 계약 기간 내인 경우만 결근 체크 대상
                            if hire_date <= d_str and (not resignation_date or d_str <= resignation_date):
                                rec = attendance_records.get(d_str)
                                if not rec and (d_str < date_list[0] or d_str > date_list[-1]):
                                    if d_str < date_list[0] and not prev_month_has_data:
                                        # 이전 월 데이터가 아예 없는 경우, 결근으로 판단하지 않고 패스
                                        continue
                                    rec = get_db_record(worker_id, d_str)
                                normal_weight = rec["normal_weight"] if rec else 0.0
                                status = rec["status"] if rec else ""
                                monthly_h = rec.get("monthly_holiday", 0.0) if rec else 0.0
                                if normal_weight <= 0.0 and status not in EXCUSED_STATUSES and monthly_h <= 0.0:
                                    is_perfect = False
                                    break
                                    
                    weekly_val = 0.0 if exclude_holiday else (1.0 if is_perfect else 0.0)
                    if sun_str[:6] == year_month.replace("-", ""):
                        sun_rec = attendance_records.get(sun_str)
                        if sun_rec:
                            if sun_rec["is_weekly_manual"] == 0 and sun_rec["weekly_holiday"] != weekly_val:
                                before_val = f"주차:{sun_rec['weekly_holiday']}"
                                cursor.execute("UPDATE daily_attendance SET weekly_holiday = ?, version = version + 1 WHERE date = ? AND worker_id = ?;", (weekly_val, sun_str, worker_id))
                                sun_rec["weekly_holiday"] = weekly_val
                                db_manager.log_audit("SYSTEM", worker_id, f"{sun_str} 주차 자동 계산 반영", before_val, f"주차:{weekly_val}", conn=conn)
                        else:
                            if weekly_val > 0.0:
                                cursor.execute("""
                                    INSERT INTO daily_attendance (date, worker_id, normal_weight, overtime_weight, lodging_weight, health_weight, leader_weight, weekly_holiday, monthly_holiday, status, is_weekly_manual, is_monthly_manual, version)
                                    VALUES (?, ?, 0.0, 0.0, 0.0, 0.0, 0.0, ?, 0.0, '휴무', 0, 0, 1);
                                """, (sun_str, worker_id, weekly_val))
                                db_manager.log_audit("SYSTEM", worker_id, f"{sun_str} 주차 자동 계산 신규 삽입 반영", "주차:없음", f"주차:{weekly_val}", conn=conn)
                                attendance_records[sun_str] = {
                                    "date": sun_str, "worker_id": worker_id, "normal_weight": 0.0, "overtime_weight": 0.0,
                                    "lodging_weight": 0.0, "health_weight": 0.0, "leader_weight": 0.0, "weekly_holiday": weekly_val,
                                    "monthly_holiday": 0.0, "status": "휴무", "is_weekly_manual": 0, "is_monthly_manual": 0, "version": 1
                                }
            
            # 주차 클린업 (그 외 평일/토요일은 0.0)
            for date_str in date_list:
                dt = datetime.date(int(date_str[:4]), int(date_str[4:6]), int(date_str[6:8]))
                is_sunday = (dt.weekday() == 6)
                is_resignation = (resignation_date is not None and date_str == resignation_date)
                
                if not is_sunday and not is_resignation:
                    rec = attendance_records.get(date_str)
                    if rec and rec["is_weekly_manual"] == 0 and rec["weekly_holiday"] != 0.0:
                        cursor.execute("UPDATE daily_attendance SET weekly_holiday = 0.0, version = version + 1 WHERE date = ? AND worker_id = ?;", (date_str, worker_id))
                        rec["weekly_holiday"] = 0.0
                        
            # --- 3. 월차 계산 시작 ---
            is_new_hire_this_month = (hire_date[:6] == year_month.replace("-", ""))
            is_resigned_this_month = (resignation_date is not None and resignation_date[:6] == year_month.replace("-", ""))
            
            # 월 평일 출근일수 카운트 (실제 출근했거나, 구분 값이 인정 상태이거나, 공휴일/면제일인 경우 인정)
            worked_weekdays_month = 0
            for date_str in date_list:
                dt = datetime.date(int(date_str[:4]), int(date_str[4:6]), int(date_str[6:8]))
                if dt.weekday() < 5:  # Mon-Fri
                    rec = attendance_records.get(date_str)
                    if (rec and ((rec["normal_weight"] or 0.0) > 0.0 or rec.get("status") in EXCUSED_STATUSES)) or (date_str in holiday_dates):
                        worked_weekdays_month += 1
            
            is_before_hire = (year_month.replace("-", "") < hire_date[:6])

            # 월차 값 결정
            if is_before_hire:
                # 입사월 이전인 경우: 월차 발생 안함 (0.0)
                monthly_val = 0.0
                target_date_str = date_list[-1]
            elif is_resigned_this_month:
                # 중도 퇴사한 달: 평일 출근일수 당 0.05씩 퇴사일에 부여 (최대 1.0)
                monthly_val = 0.0 if exclude_holiday else min(1.0, round(0.05 * worked_weekdays_month, 2))
                target_date_str = resignation_date
            elif is_new_hire_this_month:
                # 신규 입사한 달: 평일 출근일수 당 0.05씩 월말일에 부여 (최대 1.0)
                monthly_val = 0.0 if exclude_holiday else min(1.0, round(0.05 * worked_weekdays_month, 2))
                target_date_str = date_list[-1]
            else:
                # 그 외 모든 근로자: 평일 결근 발생 시 0.0, 평일 만근 시 1.0
                is_perfect_month = True
                has_valid_working_day = False
                for date_str in date_list:
                    if is_working_weekday(date_str, holiday_dates):
                        if hire_date <= date_str and (not resignation_date or date_str <= resignation_date):
                            has_valid_working_day = True
                            rec = attendance_records.get(date_str)
                            normal_weight = rec["normal_weight"] if rec else 0.0
                            status = rec["status"] if rec else ""
                            monthly_h = rec.get("monthly_holiday", 0.0) if rec else 0.0
                            if normal_weight <= 0.0 and status not in EXCUSED_STATUSES and monthly_h <= 0.0:
                                is_perfect_month = False
                                break
                if not has_valid_working_day:
                    is_perfect_month = False
                monthly_val = 0.0 if exclude_holiday else (1.0 if is_perfect_month else 0.0)
                target_date_str = date_list[-1]
                
            # 월중 다른 날에 월차수당(monthly_holiday > 0)이 기입되어 있는지 체크
            has_other_monthly = False
            for date_str in date_list:
                if date_str != target_date_str:
                    rec = attendance_records.get(date_str)
                    if rec and (rec.get("monthly_holiday", 0.0) or 0.0) > 0.0:
                        has_other_monthly = True
                        break
            if has_other_monthly:
                monthly_val = 0.0

            # 월차 값 기입 및 다른 일자 클린업
            for date_str in date_list:
                is_target = (date_str == target_date_str)
                rec = attendance_records.get(date_str)
                if rec:
                    if rec["is_monthly_manual"] == 0:
                        if is_target:
                            if rec["monthly_holiday"] != monthly_val:
                                before_val = f"월차:{rec['monthly_holiday']}"
                                cursor.execute("UPDATE daily_attendance SET monthly_holiday = ?, version = version + 1 WHERE date = ? AND worker_id = ?;", (monthly_val, date_str, worker_id))
                                rec["monthly_holiday"] = monthly_val
                                db_manager.log_audit("SYSTEM", worker_id, f"{date_str} 월차 계산 반영", before_val, f"월차:{monthly_val}", conn=conn)
                        else:
                            if rec["monthly_holiday"] != 0.0:
                                cursor.execute("UPDATE daily_attendance SET monthly_holiday = 0.0, version = version + 1 WHERE date = ? AND worker_id = ?;", (date_str, worker_id))
                                rec["monthly_holiday"] = 0.0
                else:
                    if is_target and monthly_val > 0.0:
                        cursor.execute("""
                            INSERT INTO daily_attendance (date, worker_id, normal_weight, overtime_weight, lodging_weight, health_weight, leader_weight, weekly_holiday, monthly_holiday, status, is_weekly_manual, is_monthly_manual, version)
                            VALUES (?, ?, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, ?, '휴무', 0, 0, 1);
                        """, (date_str, worker_id, monthly_val))
                        db_manager.log_audit("SYSTEM", worker_id, f"{date_str} 월차 신규 삽입 반영", "월차:없음", f"월차:{monthly_val}", conn=conn)
                        attendance_records[date_str] = {
                            "date": date_str, "worker_id": worker_id, "normal_weight": 0.0, "overtime_weight": 0.0,
                            "lodging_weight": 0.0, "health_weight": 0.0, "leader_weight": 0.0, "weekly_holiday": 0.0,
                            "monthly_holiday": monthly_val, "status": "휴무", "is_weekly_manual": 0, "is_monthly_manual": 0, "version": 1
                        }
                        
            # --- 4. 보건수당 계산 시작 ---
            # 여성근로자(주민번호 7번째 자리 2 또는 4) 대상:
            # - 퇴사자: 퇴사일까지 평일 근로 15일 이상 시 퇴사날에 보건수당 1.0 부여, 15일 미만 시 0.0
            # - 재직자: 해당 월 전체 근로 15일 이상 시 마지막 토요일에 보건수당 1.0 부여, 15일 미만 시 0.0
            # 단, 보건수당이 월 중에 이미 입력된 경우(health_weight > 0.0) 자동계산으로 덮어쓰거나 수정하지 않습니다.
            has_existing_health = any((rec.get("health_weight", 0.0) or 0.0) > 0.0 for rec in attendance_records.values())

            if not has_existing_health:
                clean_id = worker_id.replace("-", "")
                is_female = (len(clean_id) >= 7 and clean_id[6] in ('2', '4'))
                is_resigned_this_month = (resignation_date is not None and resignation_date[:6] == year_month.replace("-", ""))
                
                health_target_date = None
                health_val = 0.0

                if is_female and not exclude_holiday:
                    if is_resigned_this_month:
                        resignation_clean = resignation_date.replace("-", "").replace("/", "").strip()
                        cursor.execute("""
                            SELECT SUM(normal_weight) as worked_days
                            FROM daily_attendance
                            WHERE worker_id = ? AND substr(date, 1, 6) = ? AND date <= ?;
                        """, (worker_id, year_month.replace("-", ""), resignation_clean))
                        w_days_row = cursor.fetchone()
                        worked_days_val = w_days_row["worked_days"] or 0.0
                        
                        if worked_days_val >= 15.0:
                            health_target_date = resignation_clean
                            health_val = 1.0
                    else:
                        cursor.execute("""
                            SELECT SUM(normal_weight) as worked_days
                            FROM daily_attendance
                            WHERE worker_id = ? AND substr(date, 1, 6) = ?;
                        """, (worker_id, year_month.replace("-", "")))
                        w_days_row = cursor.fetchone()
                        worked_days_val = w_days_row["worked_days"] or 0.0
                        
                        if worked_days_val >= 15.0:
                            for date_str in reversed(date_list):
                                dt_obj = datetime.date(int(date_str[:4]), int(date_str[4:6]), int(date_str[6:8]))
                                if dt_obj.weekday() == 5:
                                    health_target_date = date_str
                                    break
                            if not health_target_date:
                                health_target_date = date_list[-1]
                            health_val = 1.0

                for date_str in date_list:
                    is_h_target = (health_target_date is not None and date_str == health_target_date)
                    h_val = health_val if is_h_target else 0.0
                    rec = attendance_records.get(date_str)
                    if rec:
                        if rec["health_weight"] != h_val:
                            before_val = f"보건:{rec['health_weight']}"
                            cursor.execute("""
                                UPDATE daily_attendance 
                                SET health_weight = ?, version = version + 1 
                                WHERE date = ? AND worker_id = ?;
                            """, (h_val, date_str, worker_id))
                            rec["health_weight"] = h_val
                            db_manager.log_audit("SYSTEM", worker_id, f"{date_str} 보건수당 자동 계산 반영", before_val, f"보건:{h_val}", conn=conn)
                    else:
                        if h_val > 0.0:
                            cursor.execute("""
                                INSERT INTO daily_attendance (date, worker_id, normal_weight, overtime_weight, lodging_weight, health_weight, leader_weight, weekly_holiday, monthly_holiday, status, is_weekly_manual, is_monthly_manual, version)
                                VALUES (?, ?, 0.0, 0.0, 0.0, ?, 0.0, 0.0, 0.0, '휴무', 0, 0, 1);
                            """, (date_str, worker_id, h_val))
                            db_manager.log_audit("SYSTEM", worker_id, f"{date_str} 보건수당 신규 삽입 반영", "보건:없음", f"보건:{h_val}", conn=conn)
                            attendance_records[date_str] = {
                                "date": date_str, "worker_id": worker_id, "normal_weight": 0.0, "overtime_weight": 0.0,
                                "lodging_weight": 0.0, "health_weight": h_val, "leader_weight": 0.0, "weekly_holiday": 0.0,
                                "monthly_holiday": 0.0, "status": "휴무", "is_weekly_manual": 0, "is_monthly_manual": 0, "version": 1
                            }
                        
            # 5. 인물별 월별 집계(monthly_status) 갱신
            cursor.execute("""
                SELECT 
                    SUM(normal_weight) as worked_days,
                    SUM(weekly_holiday) as weekly_holidays,
                    SUM(monthly_holiday) as monthly_holidays
                FROM daily_attendance
                WHERE worker_id = ? AND substr(date, 1, 6) = ?;
            """, (worker_id, year_month.replace("-", "")))
            
            summary = cursor.fetchone()
            worked_days = summary["worked_days"] or 0.0
            weekly_holidays = summary["weekly_holidays"] or 0.0
            monthly_holidays = summary["monthly_holidays"] or 0.0
            
            # monthly_status 데이터 Upsert
            cursor.execute("""
                INSERT INTO monthly_status (year_month, worker_id, worked_days, weekly_holidays, monthly_holidays, version)
                VALUES (?, ?, ?, ?, ?, 1)
                ON CONFLICT(year_month, worker_id) DO UPDATE SET
                    worked_days = excluded.worked_days,
                    weekly_holidays = excluded.weekly_holidays,
                    monthly_holidays = excluded.monthly_holidays,
                    version = version + 1;
            """, (year_month, worker_id, worked_days, weekly_holidays, monthly_holidays))
            
        conn.commit()
    except Exception as e:
        conn.rollback()
        db_manager.log_system_error(user_id, f"{year_month} 공수 재계산 실패: {e}", traceback.format_exc(), conn=conn)
        raise e
    finally:
        conn.close()


def recalculate_monthly_holidays(year_month: str, user_id: str = "SYSTEM", conn=None):
    """주차/월차/보건 수당 호환용 래퍼 함수"""
    return recalculate_month(year_month, user_id)

def recalculate_health_allowances(year_month: str, user_id: str = "SYSTEM", conn=None):
    """보건 수당 호환용 래퍼 함수"""
    return recalculate_month(year_month, user_id)
