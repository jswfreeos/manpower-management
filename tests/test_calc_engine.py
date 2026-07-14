# tests/test_calc_engine.py
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import db_manager
import calc_engine

def setup_module(module):
    config.DB_PATH = "test_attendance_management_calc.db"
    try:
        if os.path.exists(config.DB_PATH):
            os.remove(config.DB_PATH)
    except:
        pass
    db_manager.init_db()

def teardown_module(module):
    # Ensure SQLite closes connections
    import gc
    gc.collect()
    
    for suffix in ["", "-wal", "-shm"]:
        path = "test_attendance_management_calc.db" + suffix
        if os.path.exists(path):
            try:
                os.remove(path)
            except:
                pass

def test_working_weekday():
    """평일 판단 및 공휴일 판별 검증"""
    # 2026-05-01 (금요일, 근로자의 날 가정)
    holiday_dates = ["20260501"]
    
    # 20260501은 공휴일 리스트에 있으므로 평일 근무 아님
    assert calc_engine.is_working_weekday("20260501", holiday_dates) is False
    # 20260502 (토요일)은 평일 아님
    assert calc_engine.is_working_weekday("20260502", holiday_dates) is False
    # 20260504 (월요일)은 평일
    assert calc_engine.is_working_weekday("20260504", holiday_dates) is True

def test_recalculate_month():
    """주차/월차 자동 계산 검증 (신규 주월차 규칙 반영)"""
    # 1. 근로자 W001 추가 (입사일: 2026-07-10, 퇴사일: 2026-07-20)
    # 2026-07-10: 금요일 (신규 입사 주)
    # 2026-07-20: 월요일 (중도 퇴사 주)
    worker = [{
        "worker_id": "W001",
        "name": "입퇴사자",
        "has_lodging": 0,
        "has_health": 0,
        "is_team_leader": 0,
        "hire_date": "2026-07-10",
        "resignation_date": "2026-07-20",
        "team": "현장팀",
        "trade": "잡무"
    }]
    db_manager.bulk_insert_workers(worker, "SYSTEM")
    
    # 2. 계약 유효기간 내 출역 데이터 및 입사 전 오류 데이터 기입
    # 입사한 주의 평일 금요일(20260710) 출근
    # 다음 주 평일 월요일(20260713) 출근
    # 퇴사 주 평일 월요일(20260720) 출근
    attendance = [
        {"date": "20260710", "worker_id": "W001", "normal_weight": 1.0, "status": "출근", "is_weekly_manual": 0, "is_monthly_manual": 0, "version": 1},
        {"date": "20260713", "worker_id": "W001", "normal_weight": 1.0, "status": "출근", "is_weekly_manual": 0, "is_monthly_manual": 0, "version": 1},
        {"date": "20260720", "worker_id": "W001", "normal_weight": 1.0, "status": "출근", "is_weekly_manual": 0, "is_monthly_manual": 0, "version": 1},
        {"date": "20260705", "worker_id": "W001", "normal_weight": 1.0, "status": "출근", "is_weekly_manual": 0, "is_monthly_manual": 0, "version": 1}, # 입사 전 오류
        {"date": "20260712", "worker_id": "W001", "normal_weight": 0.0, "status": "휴무", "is_weekly_manual": 0, "is_monthly_manual": 0, "version": 1}, # 일요일
        {"date": "20260719", "worker_id": "W001", "normal_weight": 0.0, "status": "휴무", "is_weekly_manual": 0, "is_monthly_manual": 0, "version": 1}  # 일요일
    ]
    db_manager.save_attendance_bulk(attendance, "SYSTEM")
    
    calc_engine.recalculate_month("2026-07", "TEST_USER")
    
    conn = db_manager.get_db_connection()
    
    # 입사일 이전 데이터 초기화 검증
    row_invalid = conn.execute("SELECT * FROM daily_attendance WHERE date='20260705' AND worker_id='W001';").fetchone()
    assert row_invalid["normal_weight"] == 0.0
    
    # 신규 입사 주 (7/10 금요일 입사, 평일 중 금요일 1일 근무)
    # 7/12 일요일 주차는 0.2 * 1 = 0.2
    row_sun1 = conn.execute("SELECT * FROM daily_attendance WHERE date='20260712' AND worker_id='W001';").fetchone()
    assert row_sun1["weekly_holiday"] == 0.2
    
    # 중도 퇴사 주 (7/20 월요일 퇴사, 평일 중 월요일 1일 근무)
    # 퇴사일(7/20) 주차는 0.2 * 1 = 0.2
    row_resign = conn.execute("SELECT * FROM daily_attendance WHERE date='20260720' AND worker_id='W001';").fetchone()
    assert row_resign["weekly_holiday"] == 0.2
    
    # 퇴사 달 (7월 중 평일 총 3일 출근: 7/10, 7/13, 7/20)
    # 퇴사일(7/20) 월차는 0.05 * 3 = 0.15
    assert row_resign["monthly_holiday"] == 0.15
    
    conn.close()
