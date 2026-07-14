# db_manager.py
"""
[1단계] SQLite 연결, 인덱싱, 트랜잭션, 백업 전담 모듈
"""
import os
import sqlite3
import datetime
import shutil
import traceback
from typing import List, Dict, Any, Tuple
import config

def get_db_connection() -> sqlite3.Connection:
    """SQLite 데이터베이스 연결을 생성하고 WAL 모드 및 외래 키 설정을 활성화합니다."""
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn

# --- 일별 입력 완료 체크리스트 관리 API ---

def get_daily_checks(year_month_dash: str) -> dict:
    """선택한 월(YYYY-MM)의 일별 입력 완료 체크 정보를 딕셔너리로 반환합니다."""
    conn = get_db_connection()
    ym = year_month_dash.replace("-", "")
    rows = conn.execute("SELECT date, is_completed FROM daily_input_checks WHERE substr(date, 1, 6) = ?;", (ym,)).fetchall()
    conn.close()
    return {r["date"]: bool(r["is_completed"]) for r in rows}

def save_daily_checks(checks: dict):
    """딕셔너리 형태의 일별 입력 완료 상태({date: is_completed})를 DB에 저장합니다."""
    conn = get_db_connection()
    cursor = conn.cursor()
    for date_str, is_completed in checks.items():
        val = 1 if is_completed else 0
        cursor.execute("INSERT OR REPLACE INTO daily_input_checks (date, is_completed) VALUES (?, ?);", (date_str, val))
    conn.commit()
    conn.close()

def init_db():
    """데이터베이스 테이블 및 대용량 검색 인덱스를 초기화합니다."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. 근로자 테이블
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS workers (
        worker_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        has_lodging INTEGER NOT NULL DEFAULT 0,
        has_health INTEGER NOT NULL DEFAULT 0,
        is_team_leader INTEGER NOT NULL DEFAULT 0,
        hire_date TEXT NOT NULL,
        resignation_date TEXT,
        team TEXT,
        trade TEXT,
        remarks TEXT
    );
    """)
    
    # 2. 일일 출역 테이블
    cursor.execute(f"""
    CREATE TABLE IF NOT EXISTS daily_attendance (
        date TEXT,
        worker_id TEXT,
        normal_weight REAL NOT NULL CHECK (normal_weight BETWEEN {config.ALLOWED_MIN_WEIGHT} AND {config.ALLOWED_MAX_WEIGHT}),
        overtime_weight REAL NOT NULL CHECK (overtime_weight BETWEEN {config.ALLOWED_MIN_WEIGHT} AND {config.ALLOWED_MAX_WEIGHT}),
        lodging_weight REAL NOT NULL CHECK (lodging_weight BETWEEN {config.ALLOWED_MIN_WEIGHT} AND {config.ALLOWED_MAX_WEIGHT}),
        health_weight REAL NOT NULL CHECK (health_weight BETWEEN {config.ALLOWED_MIN_WEIGHT} AND {config.ALLOWED_MAX_WEIGHT}),
        leader_weight REAL NOT NULL CHECK (leader_weight BETWEEN {config.ALLOWED_MIN_WEIGHT} AND {config.ALLOWED_MAX_WEIGHT}),
        weekly_holiday REAL NOT NULL DEFAULT 0.0 CHECK (weekly_holiday BETWEEN {config.ALLOWED_MIN_WEIGHT} AND {config.ALLOWED_MAX_WEIGHT}),
        monthly_holiday REAL NOT NULL DEFAULT 0.0 CHECK (monthly_holiday BETWEEN {config.ALLOWED_MIN_WEIGHT} AND {config.ALLOWED_MAX_WEIGHT}),
        status TEXT NOT NULL DEFAULT '출근',
        is_weekly_manual INTEGER NOT NULL DEFAULT 0,
        is_monthly_manual INTEGER NOT NULL DEFAULT 0,
        prev_month_missing REAL NOT NULL DEFAULT 0.0,
        deduction REAL NOT NULL DEFAULT 0.0,
        version INTEGER NOT NULL DEFAULT 1,
        PRIMARY KEY (date, worker_id),
        FOREIGN KEY (worker_id) REFERENCES workers(worker_id) ON DELETE CASCADE
    );
    """)
    
    # 마이그레이션: prev_month_missing 컬럼이 기존 DB에 없으면 동적으로 추가
    try:
        cursor.execute("SELECT prev_month_missing FROM daily_attendance LIMIT 1;")
    except sqlite3.OperationalError:
        cursor.execute("ALTER TABLE daily_attendance ADD COLUMN prev_month_missing REAL NOT NULL DEFAULT 0.0;")

    # 마이그레이션: deduction 컬럼이 기존 DB에 없으면 동적으로 추가
    try:
        cursor.execute("SELECT deduction FROM daily_attendance LIMIT 1;")
    except sqlite3.OperationalError:
        cursor.execute("ALTER TABLE daily_attendance ADD COLUMN deduction REAL NOT NULL DEFAULT 0.0;")
    
    # 3. 월별 공수 요약 테이블
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS monthly_status (
        year_month TEXT,
        worker_id TEXT,
        worked_days REAL NOT NULL DEFAULT 0.0,
        weekly_holidays REAL NOT NULL DEFAULT 0.0,
        monthly_holidays REAL NOT NULL DEFAULT 0.0,
        version INTEGER NOT NULL DEFAULT 1,
        PRIMARY KEY (year_month, worker_id),
        FOREIGN KEY (worker_id) REFERENCES workers(worker_id) ON DELETE CASCADE
    );
    """)
    
    # 4. 공휴일/셧다운일 테이블
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS holidays (
        date TEXT PRIMARY KEY,
        description TEXT
    );
    """)
    
    # 4-1. 주월차 인정일(결근 면제일) 테이블
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS excused_absence_dates (
        date TEXT PRIMARY KEY,
        description TEXT
    );
    """)
    
    # 5. 감사 로그 테이블
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        user_id TEXT NOT NULL,
        worker_id TEXT,
        action TEXT NOT NULL,
        before_value TEXT,
        after_value TEXT
    );
    """)
    
    # 6. 시스템 오류 로그 테이블
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS system_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        log_level TEXT NOT NULL,
        message TEXT NOT NULL,
        traceback TEXT
    );
    """)
    
    # 7. 로그인 기록 테이블
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS login_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        user_id TEXT NOT NULL,
        ip_address TEXT,
        status TEXT NOT NULL
    );
    """)
    
    # 8. 엑셀 업로드 이력 테이블
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS import_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        file_name TEXT NOT NULL,
        uploaded_by TEXT NOT NULL,
        row_count INTEGER,
        status TEXT NOT NULL,
        error_message TEXT
    );
    """)
    
    # 9. 마감 상태 테이블
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS monthly_closures (
        year_month TEXT PRIMARY KEY,
        is_closed INTEGER NOT NULL DEFAULT 0,
        closed_by TEXT,
        closed_at TEXT
    );
    """)
    
    # 10. 일별 입력 완료 체크 테이블
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS daily_input_checks (
        date TEXT PRIMARY KEY,
        is_completed INTEGER NOT NULL DEFAULT 0
    );
    """)
    
    # 11. 엑셀 매칭 실패 로그 테이블
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS excel_match_failures (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        file_path TEXT NOT NULL,
        date TEXT NOT NULL,
        row_index INTEGER,
        raw_worker_id TEXT,
        raw_name TEXT,
        raw_normal_weight REAL,
        raw_overtime_weight REAL,
        failure_reason TEXT
    );
    """)
    
    # 12. 커스텀 공수 가중치 정의 테이블 (확장 대비)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS custom_weight_types (
        type_id TEXT PRIMARY KEY,
        display_name TEXT NOT NULL
    );
    """)
    
    # 12. 커스텀 일일 공수 테이블 (확장 대비)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS daily_custom_attendance (
        date TEXT,
        worker_id TEXT,
        type_id TEXT,
        weight REAL NOT NULL CHECK (weight >= 0.0),
        PRIMARY KEY (date, worker_id, type_id),
        FOREIGN KEY (worker_id) REFERENCES workers(worker_id) ON DELETE CASCADE,
        FOREIGN KEY (type_id) REFERENCES custom_weight_types(type_id) ON DELETE CASCADE
    );
    """)
    
    # 13. 일일 작업 보고 테이블 (확정 서식 출력용)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS daily_reports (
        date TEXT PRIMARY KEY,
        site_name TEXT,
        weather_am TEXT,
        weather_pm TEXT,
        work_desc TEXT,
        remarks TEXT,
        created_at TEXT,
        updated_at TEXT
    );
    """)
    
    # 인덱스 고속 검색 활성화
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_attendance_date ON daily_attendance(date);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_attendance_worker ON daily_attendance(worker_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_attendance_worker_date ON daily_attendance(worker_id, date);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_logs(timestamp);")
    
    # 마이그레이션: workers 테이블에 remarks 컬럼 추가 (존재하지 않는 경우)
    try:
        cursor.execute("ALTER TABLE workers ADD COLUMN remarks TEXT;")
    except sqlite3.OperationalError:
        pass
        
    # 14. 시스템 설정 테이블
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS system_settings (
        setting_key TEXT PRIMARY KEY,
        setting_value TEXT
    );
    """)
        
    conn.commit()
    conn.close()

def auto_backup_database():
    """오늘 날짜의 백업 파일을 생성하고 30일이 경과한 백업본을 자동 만료/삭제합니다."""
    if not os.path.exists(config.BACKUP_DIR):
        os.makedirs(config.BACKUP_DIR)
        
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    backup_file = os.path.join(config.BACKUP_DIR, f"database_{today_str}.db")
    
    # 오늘자 백업이 없으면 복사
    if os.path.exists(config.DB_PATH) and not os.path.exists(backup_file):
        try:
            shutil.copy2(config.DB_PATH, backup_file)
            log_system_info("System", f"데이터베이스 자동 백업 완료: {backup_file}")
        except Exception as e:
            log_system_error("System", f"데이터베이스 자동 백업 실패: {e}", traceback.format_exc())
            
    # 30일이 지난 백업 파일 삭제
    try:
        now = datetime.datetime.now()
        for filename in os.listdir(config.BACKUP_DIR):
            if filename.startswith("database_") and filename.endswith(".db"):
                filepath = os.path.join(config.BACKUP_DIR, filename)
                file_time = datetime.datetime.fromtimestamp(os.path.getmtime(filepath))
                if (now - file_time).days > 30:
                    os.remove(filepath)
                    log_system_info("System", f"30일 만료 백업 파일 자동 삭제 완료: {filename}")
    except Exception as e:
        log_system_error("System", f"오래된 백업 삭제 중 에러: {e}", traceback.format_exc())

# 로그 기록 함수군
def log_system_info(user_id: str, message: str, conn: sqlite3.Connection = None):
    """시스템 일반 정보를 기록합니다."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    should_close = False
    if conn is None:
        conn = get_db_connection()
        should_close = True
    conn.execute("INSERT INTO system_logs (timestamp, log_level, message) VALUES (?, ?, ?);",
                 (timestamp, "INFO", message))
    if should_close:
        conn.commit()
        conn.close()

def log_system_error(user_id: str, message: str, tb: str = None, conn: sqlite3.Connection = None):
    """시스템 에러 및 예외 상세를 기록합니다."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    should_close = False
    if conn is None:
        conn = get_db_connection()
        should_close = True
    conn.execute("INSERT INTO system_logs (timestamp, log_level, message, traceback) VALUES (?, ?, ?, ?);",
                 (timestamp, "ERROR", message, tb))
    if should_close:
        conn.commit()
        conn.close()

def log_audit(user_id: str, worker_id: str, action: str, before_value: str = None, after_value: str = None, conn: sqlite3.Connection = None):
    """관리자/시스템의 수정 이력을 audit_logs 테이블에 명시적으로 기록합니다."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    should_close = False
    if conn is None:
        conn = get_db_connection()
        should_close = True
    conn.execute("""
        INSERT INTO audit_logs (timestamp, user_id, worker_id, action, before_value, after_value)
        VALUES (?, ?, ?, ?, ?, ?);
    """, (timestamp, user_id, worker_id, action, before_value, after_value))
    if should_close:
        conn.commit()
        conn.close()

def log_login(user_id: str, ip_address: str, status: str, conn: sqlite3.Connection = None):
    """접근 및 로그인 성공/실패 내역을 기록합니다."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    should_close = False
    if conn is None:
        conn = get_db_connection()
        should_close = True
    conn.execute("INSERT INTO login_logs (timestamp, user_id, ip_address, status) VALUES (?, ?, ?, ?);",
                 (timestamp, user_id, ip_address, status))
    if should_close:
        conn.commit()
        conn.close()

def log_import(file_name: str, uploaded_by: str, row_count: int, status: str, error_message: str = None, conn: sqlite3.Connection = None):
    """엑셀 파일 가져오기 시도 로그를 기록합니다."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    should_close = False
    if conn is None:
        conn = get_db_connection()
        should_close = True
    conn.execute("""
        INSERT INTO import_logs (timestamp, file_name, uploaded_by, row_count, status, error_message)
        VALUES (?, ?, ?, ?, ?, ?);
    """, (timestamp, file_name, uploaded_by, row_count, status, error_message))
    if should_close:
        conn.commit()
        conn.close()

# 근로자 관리 기능
def get_all_workers() -> List[Dict[str, Any]]:
    """모든 근로자 목록을 조회합니다."""
    conn = get_db_connection()
    rows = conn.execute("SELECT * FROM workers ORDER BY name ASC;").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_worker(worker_id: str) -> Dict[str, Any]:
    """특정 근로자 1명의 데이터를 조회합니다."""
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM workers WHERE worker_id = ?;", (worker_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def bulk_insert_workers(workers_list: List[Dict[str, Any]], user_id: str) -> Tuple[int, int]:
    """
    근로자 정보를 대량 일괄 등록/수정(Upsert)하며 변경사항을 감사 로그에 기록합니다.
    returns: (추가된 근로자 수, 수정된 근로자 수)
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    added_count = 0
    updated_count = 0
    
    try:
        for w in workers_list:
            worker_id = w["worker_id"]
            name = w["name"]
            has_lodging = w.get("has_lodging", 0)
            has_health = w.get("has_health", 0)
            is_team_leader = w.get("is_team_leader", 0)
            hire_date = w["hire_date"]
            resignation_date = w.get("resignation_date")
            team = w.get("team")
            trade = w.get("trade")
            remarks = w.get("remarks")
            
            # 기존 정보와 비교하기 위해 먼저 조회
            cursor.execute("SELECT * FROM workers WHERE worker_id = ?;", (worker_id,))
            existing = cursor.fetchone()
            
            if existing:
                existing = dict(existing)
                # 바뀐 정보가 있는지 비교
                changed = (
                    existing["name"] != name or
                    existing["has_lodging"] != has_lodging or
                    existing["has_health"] != has_health or
                    existing["is_team_leader"] != is_team_leader or
                    existing["hire_date"] != hire_date or
                    existing["resignation_date"] != resignation_date or
                    existing["team"] != team or
                    existing["trade"] != trade or
                    existing.get("remarks") != remarks
                )
                if changed:
                    cursor.execute("""
                        UPDATE workers
                        SET name = ?, has_lodging = ?, has_health = ?, is_team_leader = ?,
                            hire_date = ?, resignation_date = ?, team = ?, trade = ?, remarks = ?
                        WHERE worker_id = ?;
                    """, (name, has_lodging, has_health, is_team_leader, hire_date, resignation_date, team, trade, remarks, worker_id))
                    
                    before_str = str(existing)
                    after_str = str(w)
                    log_audit(user_id, worker_id, "근로자 일괄 수정", before_str, after_str, conn=conn)
                    updated_count += 1
            else:
                cursor.execute("""
                    INSERT INTO workers (worker_id, name, has_lodging, has_health, is_team_leader, hire_date, resignation_date, team, trade, remarks)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """, (worker_id, name, has_lodging, has_health, is_team_leader, hire_date, resignation_date, team, trade, remarks))
                
                log_audit(user_id, worker_id, "근로자 일괄 신규 등록", None, str(w), conn=conn)
                added_count += 1
                
        conn.commit()
    except Exception as e:
        conn.rollback()
        log_system_error(user_id, f"근로자 일괄 등록 에러: {e}", traceback.format_exc(), conn=conn)
        raise e
    finally:
        conn.close()
        
    return added_count, updated_count

# 마감 관리 기능
def is_month_locked(year_month: str) -> bool:
    """특정 연월의 공수 마감 잠금 여부를 확인합니다."""
    conn = get_db_connection()
    row = conn.execute("SELECT is_closed FROM monthly_closures WHERE year_month = ?;", (year_month,)).fetchone()
    conn.close()
    return bool(row["is_closed"]) if row else False

def lock_month(year_month: str, user_id: str):
    """특정 연월의 공수를 마감 처리합니다."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db_connection()
    conn.execute("""
        INSERT INTO monthly_closures (year_month, is_closed, closed_by, closed_at)
        VALUES (?, 1, ?, ?)
        ON CONFLICT(year_month) DO UPDATE SET is_closed=1, closed_by=excluded.closed_by, closed_at=excluded.closed_at;
    """, (year_month, user_id, timestamp))
    conn.commit()
    conn.close()
    log_audit(user_id, None, f"{year_month} 마감 처리")

def unlock_month(year_month: str, user_id: str):
    """특정 연월의 공수 마감을 해제합니다."""
    conn = get_db_connection()
    conn.execute("UPDATE monthly_closures SET is_closed = 0 WHERE year_month = ?;", (year_month,))
    conn.commit()
    conn.close()
    log_audit(user_id, None, f"{year_month} 마감 해제")

# 일일 공수 관리 및 낙관적 락(Optimistic Lock)
def save_attendance_bulk(data_list: List[Dict[str, Any]], user_id: str):
    """
    일일 출역 데이터를 낙관적 동시성 제어(Optimistic Lock)를 활용해 대량 저장합니다.
    동시성 충돌 감지 시 Exception을 발생시킵니다.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        for record in data_list:
            date = record["date"]
            worker_id = record["worker_id"]
            normal_weight = record.get("normal_weight", 0.0)
            overtime_weight = record.get("overtime_weight", 0.0)
            lodging_weight = record.get("lodging_weight", 0.0)
            health_weight = record.get("health_weight", 0.0)
            leader_weight = record.get("leader_weight", 0.0)
            status = record.get("status", "출근")
            is_weekly_manual = record.get("is_weekly_manual", 0)
            is_monthly_manual = record.get("is_monthly_manual", 0)
            weekly_holiday = record.get("weekly_holiday", 0.0)
            monthly_holiday = record.get("monthly_holiday", 0.0)
            prev_month_missing = record.get("prev_month_missing", 0.0)
            deduction = record.get("deduction", 0.0)
            version = record.get("version", 1)
            
            # 마감 월 체크
            year_month = date[:4] + "-" + date[4:6]
            if is_month_locked(year_month):
                raise PermissionError(f"{year_month} 월은 이미 마감되어 수정할 수 없습니다.")
            
            # 기존 출역 데이터 존재 여부 확인
            cursor.execute("SELECT version FROM daily_attendance WHERE date = ? AND worker_id = ?;", (date, worker_id))
            row = cursor.fetchone()
            
            if row:
                db_version = row["version"]
                if db_version != version:
                    # 충돌 감지
                    raise sqlite3.OperationalError(
                        f"동시성 편집 충돌 감지! [근로자 사번: {worker_id}, 날짜: {date}] "
                        f"다른 사용자가 이미 데이터를 변경했습니다. 새로고침 후 다시 입력해 주세요."
                    )
                
                # 업데이트 및 버전 증분
                cursor.execute("""
                    UPDATE daily_attendance
                    SET normal_weight = ?, overtime_weight = ?, lodging_weight = ?,
                        health_weight = ?, leader_weight = ?, weekly_holiday = ?, monthly_holiday = ?, status = ?,
                        is_weekly_manual = ?, is_monthly_manual = ?, prev_month_missing = ?, deduction = ?, version = version + 1
                    WHERE date = ? AND worker_id = ? AND version = ?;
                """, (normal_weight, overtime_weight, lodging_weight, health_weight, leader_weight,
                      weekly_holiday, monthly_holiday, status, is_weekly_manual, is_monthly_manual, prev_month_missing, deduction, date, worker_id, version))
                
                if cursor.rowcount == 0:
                    raise sqlite3.OperationalError(
                        f"업데이트 충돌! [근로자 사번: {worker_id}, 날짜: {date}] "
                        f"실제 업데이트가 이루어지지 않았습니다."
                    )
                log_audit(user_id, worker_id, f"{date} 공수 수정", before_value=f"Ver:{version}", after_value=f"Ver:{version+1}", conn=conn)
            else:
                # 신규 등록
                cursor.execute("""
                    INSERT INTO daily_attendance (
                        date, worker_id, normal_weight, overtime_weight, lodging_weight,
                        health_weight, leader_weight, weekly_holiday, monthly_holiday, status, 
                        is_weekly_manual, is_monthly_manual, prev_month_missing, deduction, version
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1);
                """, (date, worker_id, normal_weight, overtime_weight, lodging_weight,
                      health_weight, leader_weight, weekly_holiday, monthly_holiday, status, 
                      is_weekly_manual, is_monthly_manual, prev_month_missing, deduction))
                log_audit(user_id, worker_id, f"{date} 신규 출역 등록", before_value=None, after_value="Ver:1", conn=conn)
                
        conn.commit()
    except Exception as e:
        conn.rollback()
        log_system_error(user_id, f"출역 일괄 저장 실패: {e}", traceback.format_exc(), conn=conn)
        raise e
    finally:
        conn.close()

# 공휴일 관리 기능
def add_holiday(date_str: str, description: str):
    """공휴일을 추가합니다."""
    conn = get_db_connection()
    conn.execute("INSERT OR REPLACE INTO holidays (date, description) VALUES (?, ?);", (date_str, description))
    conn.commit()
    conn.close()
    log_audit("SYSTEM", None, f"공휴일 추가: {date_str} ({description})")

def remove_holiday(date_str: str):
    """공휴일을 삭제합니다."""
    conn = get_db_connection()
    conn.execute("DELETE FROM holidays WHERE date = ?;", (date_str,))
    conn.commit()
    conn.close()
    log_audit("SYSTEM", None, f"공휴일 삭제: {date_str}")

def get_holidays(year_month_dash: str = None) -> List[Dict[str, str]]:
    """모든 또는 특정 연월(YYYY-MM)의 공휴일을 리스트로 가져옵니다."""
    conn = get_db_connection()
    if year_month_dash:
        # YYYY-MM 형식에서 하이픈 제거하여 YYYYMM 형식으로 DB에서 LIKE 연산
        ym = year_month_dash.replace("-", "")
        rows = conn.execute("SELECT * FROM holidays WHERE substr(date, 1, 6) = ? ORDER BY date ASC;", (ym,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM holidays ORDER BY date ASC;").fetchall()
    conn.close()
    return [dict(r) for r in rows]

# 주월차 인정일(결근 면제일) 관리 기능
def add_excused_date(date_str: str, description: str):
    """주월차 결근 면제일을 추가합니다."""
    conn = get_db_connection()
    conn.execute("INSERT OR REPLACE INTO excused_absence_dates (date, description) VALUES (?, ?);", (date_str, description))
    conn.commit()
    conn.close()
    log_audit("SYSTEM", None, f"주월차 인정일 추가: {date_str} ({description})")

def remove_excused_date(date_str: str):
    """주월차 결근 면제일을 삭제합니다."""
    conn = get_db_connection()
    conn.execute("DELETE FROM excused_absence_dates WHERE date = ?;", (date_str,))
    conn.commit()
    conn.close()
    log_audit("SYSTEM", None, f"주월차 인정일 삭제: {date_str}")

def get_excused_dates(year_month_dash: str = None) -> List[Dict[str, str]]:
    """모든 또는 특정 연월(YYYY-MM)의 주월차 결근 면제일을 리스트로 가져옵니다."""
    conn = get_db_connection()
    if year_month_dash:
        ym = year_month_dash.replace("-", "")
        rows = conn.execute("SELECT * FROM excused_absence_dates WHERE substr(date, 1, 6) = ? ORDER BY date ASC;", (ym,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM excused_absence_dates ORDER BY date ASC;").fetchall()
    conn.close()
    return [dict(r) for r in rows]

# --- 커스텀 수당(공수 종류) 설정 API ---

def get_custom_weight_types(conn=None) -> List[Dict[str, str]]:
    """모든 커스텀 공수/수당 종류를 조회합니다."""
    close_conn = False
    if not conn:
        conn = get_db_connection()
        close_conn = True
    try:
        rows = conn.execute("SELECT * FROM custom_weight_types ORDER BY type_id ASC;").fetchall()
        return [dict(r) for r in rows]
    finally:
        if close_conn:
            conn.close()

def add_custom_weight_type(type_id: str, display_name: str, conn=None):
    """커스텀 공수/수당 종류를 추가합니다."""
    close_conn = False
    if not conn:
        conn = get_db_connection()
        close_conn = True
    try:
        conn.execute("INSERT OR REPLACE INTO custom_weight_types (type_id, display_name) VALUES (?, ?);", (type_id, display_name))
        if close_conn:
            conn.commit()
        log_audit("SYSTEM", None, f"커스텀 수당 종류 추가: {type_id} ({display_name})", conn=conn)
    finally:
        if close_conn:
            conn.close()

def delete_custom_weight_type(type_id: str, conn=None):
    """커스텀 공수/수당 종류를 삭제합니다 (연결된 일일 공수도 ON DELETE CASCADE로 자동 삭제됨)."""
    close_conn = False
    if not conn:
        conn = get_db_connection()
        close_conn = True
    try:
        conn.execute("DELETE FROM custom_weight_types WHERE type_id = ?;", (type_id,))
        if close_conn:
            conn.commit()
        log_audit("SYSTEM", None, f"커스텀 수당 종류 삭제: {type_id}", conn=conn)
    finally:
        if close_conn:
            conn.close()

def get_daily_custom_attendance(year_month_dash: str, conn=None) -> List[Dict[str, Any]]:
    """특정 연월의 모든 커스텀 일일 공수 기록을 조회합니다."""
    close_conn = False
    if not conn:
        conn = get_db_connection()
        close_conn = True
    try:
        ym = year_month_dash.replace("-", "")
        rows = conn.execute("""
            SELECT date, worker_id, type_id, weight 
            FROM daily_custom_attendance 
            WHERE substr(date, 1, 6) = ?;
        """, (ym,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        if close_conn:
            conn.close()

def save_daily_custom_attendance(date: str, worker_id: str, type_id: str, weight: float, conn=None):
    """특정 일자, 근로자, 수당 종류의 가중치를 저장합니다. 0.0일 경우 삭제하여 디스크를 절약합니다."""
    close_conn = False
    if not conn:
        conn = get_db_connection()
        close_conn = True
    cursor = conn.cursor()
    try:
        if weight == 0.0:
            cursor.execute("""
                DELETE FROM daily_custom_attendance
                WHERE date = ? AND worker_id = ? AND type_id = ?;
            """, (date, worker_id, type_id))
        else:
            cursor.execute("""
                INSERT INTO daily_custom_attendance (date, worker_id, type_id, weight)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(date, worker_id, type_id) DO UPDATE SET
                    weight = excluded.weight;
            """, (date, worker_id, type_id, weight))
        if close_conn:
            conn.commit()
    finally:
        if close_conn:
            conn.close()

def get_system_setting(key: str, default: str = "") -> str:
    """시스템 설정을 조회합니다."""
    conn = get_db_connection()
    row = conn.execute("SELECT setting_value FROM system_settings WHERE setting_key = ?;", (key,)).fetchone()
    conn.close()
    return row["setting_value"] if row else default

def set_system_setting(key: str, value: str):
    """시스템 설정을 등록하거나 업데이트합니다."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO system_settings (setting_key, setting_value)
        VALUES (?, ?)
        ON CONFLICT(setting_key) DO UPDATE SET setting_value = excluded.setting_value;
    """, (key, value))
    conn.commit()
    conn.close()

def list_backups() -> List[Dict[str, Any]]:
    """백업 폴더에 존재하는 백업 파일 목록을 반환합니다."""
    if not os.path.exists(config.BACKUP_DIR):
        return []
    backups = []
    for filename in os.listdir(config.BACKUP_DIR):
        if filename.startswith("database_") and filename.endswith(".db"):
            filepath = os.path.join(config.BACKUP_DIR, filename)
            try:
                mtime = os.path.getmtime(filepath)
                size = os.path.getsize(filepath)
                formatted_time = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
                backups.append({
                    "filename": filename,
                    "datetime": formatted_time,
                    "mtime": mtime,
                    "size_kb": round(size / 1024, 2)
                })
            except Exception:
                pass
    backups.sort(key=lambda x: x["mtime"], reverse=True)
    return backups

def create_manual_backup() -> str:
    """사용자가 직접 누르는 시점의 데이터베이스 백업을 즉시 생성합니다."""
    if not os.path.exists(config.BACKUP_DIR):
        os.makedirs(config.BACKUP_DIR)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(config.BACKUP_DIR, f"database_manual_{timestamp}.db")
    shutil.copy2(config.DB_PATH, backup_file)
    log_audit("정성우 대리", None, "수동 데이터베이스 백업 생성", after_value=f"파일: database_manual_{timestamp}.db")
    return f"database_manual_{timestamp}.db"

def restore_database(backup_filename: str) -> bool:
    """선택한 백업 파일로 현재 데이터베이스를 복원합니다. 복원 직전 현재 DB 스냅샷을 자동 백업합니다."""
    backup_file = os.path.join(config.BACKUP_DIR, backup_filename)
    if not os.path.exists(backup_file):
        raise FileNotFoundError(f"백업 파일을 찾을 수 없습니다: {backup_filename}")
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    pre_restore_backup = os.path.join(config.BACKUP_DIR, f"database_pre_restore_{timestamp}.db")
    if os.path.exists(config.DB_PATH):
        shutil.copy2(config.DB_PATH, pre_restore_backup)
    shutil.copy2(backup_file, config.DB_PATH)
    log_audit("정성우 대리", None, "데이터베이스 복원 실행", 
              before_value=f"복원 전 백업: database_pre_restore_{timestamp}.db", 
              after_value=f"복원한 파일: {backup_filename}")
    return True

def get_audit_logs(limit=1000) -> List[Dict[str, Any]]:
    """모든 감사 로그(변경 이력)를 역순으로 조회합니다."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT a.timestamp, a.user_id, a.worker_id, w.name as worker_name, a.action, a.before_value, a.after_value
        FROM audit_logs a
        LEFT JOIN workers w ON a.worker_id = w.worker_id
        ORDER BY a.timestamp DESC
        LIMIT ?;
    """, (limit,))
    records = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return records

# 데이터베이스 점검 및 초기 실행
init_db()
auto_backup_database()
