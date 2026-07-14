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
