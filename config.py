# config.py
"""
[0단계] 전역 환경설정 및 상수 관리 모듈
"""
import os
import sys

# 실행 파일 혹은 스크립트가 위치한 물리적 디렉토리 파악 (자료 유실 방지 가드)
if getattr(sys, 'frozen', False):
    # PyInstaller로 패키징된 실행 파일 상태
    APP_DIR = os.path.dirname(sys.executable)
else:
    # 일반 파이썬 스크립트 실행 상태
    APP_DIR = os.path.dirname(os.path.abspath(__file__))

DB_PATH = os.path.join(APP_DIR, "attendance_management.db")
BACKUP_DIR = os.path.join(APP_DIR, "backups")

MAX_DAILY_TOTAL_HOURS = 2.5
ALLOWED_MIN_WEIGHT = 0.0
ALLOWED_MAX_WEIGHT = 2.0
WEEKLY_HOLIDAY_RATE = 0.2
MONTHLY_HOLIDAY_RATE = 0.05
