# tests/test_db_manager.py
import sqlite3
import os
import sys

# Add parent dir to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import db_manager

def setup_module(module):
    """테스트용 임시 DB 설정"""
    config.DB_PATH = "test_attendance_management.db"
    db_manager.init_db()

def teardown_module(module):
    """테스트용 임시 DB 삭제"""
    if os.path.exists("test_attendance_management.db"):
        os.remove("test_attendance_management.db")
    if os.path.exists("test_attendance_management.db-wal"):
        os.remove("test_attendance_management.db-wal")
    if os.path.exists("test_attendance_management.db-shm"):
        os.remove("test_attendance_management.db-shm")

def test_init_db():
    """DB 초기화 테이블 존재 여부 검증"""
    conn = db_manager.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [r[0] for r in cursor.fetchall()]
    conn.close()
    
    assert "workers" in tables
    assert "daily_attendance" in tables
    assert "holidays" in tables
    assert "audit_logs" in tables

def test_bulk_insert_workers():
    """근로자 대량 등록/수정(Upsert) 기능 테스트"""
    workers = [
        {
            "worker_id": "T001",
            "name": "테스터1",
            "has_lodging": 1,
            "has_health": 0,
            "is_team_leader": 0,
            "hire_date": "2026-01-01",
            "resignation_date": None,
            "team": "테스트팀",
            "trade": "테스터"
        },
        {
            "worker_id": "T002",
            "name": "테스터2",
            "has_lodging": 0,
            "has_health": 1,
            "is_team_leader": 1,
            "hire_date": "2026-01-10",
            "resignation_date": "2026-06-30",
            "team": "개발팀",
            "trade": "개발자"
        }
    ]
    
    added, updated = db_manager.bulk_insert_workers(workers, "TEST_USER")
    assert added == 2
    assert updated == 0
    
    # 수정 동작 검증
    workers[0]["name"] = "테스터1_수정"
    added2, updated2 = db_manager.bulk_insert_workers(workers, "TEST_USER")
    assert added2 == 0
    assert updated2 == 1
    
    worker = db_manager.get_worker("T001")
    assert worker["name"] == "테스터1_수정"

def test_check_constraints():
    """공수 값 범위 CHECK 제약 조건 동작 테스트 (0.0 ~ 2.0)"""
    # 2.5(초과 값)을 넣는 경우 SQLite Constraint Error가 발생해야 함
    record = {
        "date": "20260701",
        "worker_id": "T001",
        "normal_weight": 2.5, # 2.0 초과
        "overtime_weight": 0.0,
        "lodging_weight": 0.0,
        "health_weight": 0.0,
        "leader_weight": 0.0
    }
    
    try:
        db_manager.save_attendance_bulk([record], "TEST_USER")
        assert False, "Should have raised SQLite CHECK constraint exception"
    except Exception:
        pass

def test_delete_attendance_by_date():
    """특정 날짜 데이터 일괄 삭제(전체, 팀별, 특정 수당만 선택 삭제) 테스트"""
    records = [
        {"date": "20260715", "worker_id": "T001", "normal_weight": 1.0, "overtime_weight": 0.5, "lodging_weight": 1.0, "health_weight": 1.0},
        {"date": "20260715", "worker_id": "T002", "normal_weight": 1.0, "overtime_weight": 0.0, "lodging_weight": 1.0, "health_weight": 0.0},
        {"date": "20260716", "worker_id": "T001", "normal_weight": 1.0, "overtime_weight": 0.0},
    ]
    db_manager.save_attendance_bulk(records, "TEST_USER")
    db_manager.add_custom_weight_type("danger", "위험")
    db_manager.save_daily_custom_attendance("20260715", "T001", "danger", 1.0)

    summary_before = db_manager.get_date_attendance_summary("20260715")
    assert summary_before["attendance_count"] == 2
    assert summary_before["custom_count"] == 1

    # 1. 특정 수당(숙소수당 + 위험수당)만 선택 삭제 테스트 (일반공수 및 보건수당은 보존되어야 함)
    res_sel = db_manager.delete_attendance_by_date(
        "20260715", "TEST_USER", team="전체", target_fields=["lodging_weight", "custom_danger"]
    )
    assert res_sel["deleted_attendance"] == 2
    assert res_sel["deleted_custom"] == 1
    summary_after_sel = db_manager.get_date_attendance_summary("20260715")
    assert summary_after_sel["custom_count"] == 0
    rec_t001 = [r for r in summary_after_sel["records"] if r["worker_id"] == "T001"][0]
    assert rec_t001["lodging_weight"] == 0.0
    assert rec_t001["normal_weight"] == 1.0
    assert rec_t001["health_weight"] == 1.0

    # 2. 특정 팀('개발팀' -> T002)만 전체 삭제 테스트
    res_team = db_manager.delete_attendance_by_date("20260715", "TEST_USER", team="개발팀")
    assert res_team["deleted_attendance"] == 1
    summary_after_team = db_manager.get_date_attendance_summary("20260715")
    assert summary_after_team["attendance_count"] == 1

    # 3. 해당 날짜 전체 삭제 테스트
    res_all = db_manager.delete_attendance_by_date("2026-07-15", "TEST_USER", team="전체")
    assert res_all["deleted_attendance"] == 1
    summary_after_all = db_manager.get_date_attendance_summary("20260715")
    assert summary_after_all["attendance_count"] == 0

    # 4. 다른 날짜(20260716) 데이터는 그대로 보존되었는지 확인
    summary_other_date = db_manager.get_date_attendance_summary("20260716")
    assert summary_other_date["attendance_count"] == 1

def test_lock_unlock_and_holidays():
    """월 마감/해제 및 공휴일/결근면제일 추가/삭제 기능 검증"""
    assert db_manager.is_month_locked("2026-07") is False
    db_manager.lock_month("2026-07", "TEST_USER")
    assert db_manager.is_month_locked("2026-07") is True
    db_manager.unlock_month("2026-07", "TEST_USER")
    assert db_manager.is_month_locked("2026-07") is False

    db_manager.add_holiday("20260717", "제헌절")
    holidays = db_manager.get_holidays("2026-07")
    assert any(h["date"] == "20260717" for h in holidays)
    db_manager.remove_holiday("20260717")

    db_manager.add_excused_date("20260718", "우천셧다운")
    excused = db_manager.get_excused_dates("2026-07")
    assert any(e["date"] == "20260718" for e in excused)
    db_manager.remove_excused_date("20260718")
