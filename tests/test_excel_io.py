# tests/test_excel_io.py
import os
import sys
import pandas as pd
import io

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import db_manager
import excel_io

def setup_module(module):
    config.DB_PATH = "test_attendance_management_excel.db"
    db_manager.init_db()

def teardown_module(module):
    if os.path.exists("test_attendance_management_excel.db"):
        os.remove("test_attendance_management_excel.db")
    if os.path.exists("test_attendance_management_excel.db-wal"):
        os.remove("test_attendance_management_excel.db-wal")
    if os.path.exists("test_attendance_management_excel.db-shm"):
        os.remove("test_attendance_management_excel.db-shm")

def test_generate_worker_template():
    """근로자 일괄등록 서식 파일 생성 검증"""
    content = excel_io.generate_worker_template()
    assert len(content) > 1000 # 유효 바이트 생성 확인
    
    # pandas로 역파싱 가능 여부 검증
    df = pd.read_excel(io.BytesIO(content), sheet_name=0)
    assert "주민번호*" in df.columns
    assert "성명*" in df.columns

def test_generate_daily_attendance_template():
    """일일 출역일보 업로드 서식 파일 생성 검증"""
    content = excel_io.generate_daily_attendance_template()
    assert len(content) > 1000
    df = pd.read_excel(io.BytesIO(content), sheet_name=0)
    assert "주민번호*" in df.columns
    assert "성명*" in df.columns
    assert "일반공수" in df.columns
    assert "연장공수" in df.columns

def test_parse_and_import_workers_invalid():
    """근로자 일괄등록 유효성 검사 에러 리스트 수집 기능 검증"""
    # 1. 주민번호 누락 데이터 프레임 생성
    invalid_data = pd.DataFrame([
        {
            "주민번호*": "",
            "성명*": "누락테스트",
            "소속팀": "개발팀",
            "직종/공종": "개발자",
            "입사일(YYYY-MM-DD)*": "2026-01-01",
            "퇴사일(YYYY-MM-DD)": ""
        },
        {
            "주민번호*": "10202",
            "성명*": "날짜오류테스트",
            "소속팀": "개발팀",
            "직종/공종": "개발자",
            "입사일(YYYY-MM-DD)*": "2026/13/40", # 잘못된 날짜
            "퇴사일(YYYY-MM-DD)": ""
        }
    ])
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        invalid_data.to_excel(writer, index=False)
        
    added, updated, errors = excel_io.parse_and_import_workers(output.getvalue(), "TEST_USER")
    assert added == 0
    assert len(errors) == 2
    assert "주민번호가 비어있습니다" in errors[0]
    assert "형식이 올바르지 않습니다" in errors[1]

def test_bulk_attendance_import_and_template():
    """선택적 공수 일괄 등록 템플릿 생성 및 파싱 검증"""
    customs = ["risk_allowance", "special_allowance"]
    content = excel_io.generate_bulk_attendance_template(customs)
    assert len(content) > 1000
    
    # pandas로 역파싱 가능 여부 검증
    df = pd.read_excel(io.BytesIO(content), sheet_name=0)
    assert "주민번호*" in df.columns
    assert "성명*" in df.columns
    assert "날짜(YYYY-MM-DD)*" in df.columns
    assert "일반공수" in df.columns
    assert "risk_allowance수당" in df.columns
    assert "special_allowance수당" in df.columns
