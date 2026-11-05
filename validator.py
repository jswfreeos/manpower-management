# validator.py
"""
[3단계] 현장 휴먼에러 및 예외 검증 엔진
"""
from typing import List, Dict, Any
import config
import db_manager

def audit_monthly_data(year_month: str) -> Dict[str, List[Dict[str, Any]]]:
    """
    월말 정산 전, 시스템과 입력 데이터의 이상 상태(휴먼에러 등)를 모니터링하여 검출합니다.
    """
    ym_db = year_month.replace("-", "")
    
    conn = db_manager.get_db_connection()
    cursor = conn.cursor()
    
    anomalies = {
        "omitted_attendance": [], # 유형 A: 출역 누락 (공수 0인데 수당 발생)
        "excessive_hours": [],    # 유형 B: 공수 초과 (일반+연장 > 최대시간)
        "resigned_attendance": [], # 유형 C: 퇴사자 입력 오류 (퇴사일 이후 공수 발생)
        "excel_match_failures": [] # 유형 D: 엑셀 매칭 실패 이력
    }
    
    # 1. 유형 A (연장공수 단독 입력 오류) 검출
    cursor.execute("""
        SELECT a.date, a.worker_id, w.name, a.normal_weight, a.overtime_weight
        FROM daily_attendance a
        JOIN workers w ON a.worker_id = w.worker_id
        WHERE substr(a.date, 1, 6) = ? 
          AND a.normal_weight = 0.0 
          AND a.overtime_weight > 0.0
          AND (a.prev_month_missing IS NULL OR a.prev_month_missing = 0.0);
    """, (ym_db,))
    anomalies["omitted_attendance"] = [dict(r) for r in cursor.fetchall()]
    
    # 2. 유형 B (공수 초과) 검출
    cursor.execute("""
        SELECT a.date, a.worker_id, w.name, a.normal_weight, a.overtime_weight
        FROM daily_attendance a
        JOIN workers w ON a.worker_id = w.worker_id
        WHERE substr(a.date, 1, 6) = ? 
          AND (a.normal_weight + a.overtime_weight) > ?;
    """, (ym_db, config.MAX_DAILY_TOTAL_HOURS))
    anomalies["excessive_hours"] = [dict(r) for r in cursor.fetchall()]
    
    # 3. 유형 C (퇴사자 입력 오류) 검출
    cursor.execute("""
        SELECT a.date, a.worker_id, w.name, w.resignation_date, a.normal_weight, a.overtime_weight
        FROM daily_attendance a
        JOIN workers w ON a.worker_id = w.worker_id
        WHERE substr(a.date, 1, 6) = ? 
          AND w.resignation_date IS NOT NULL 
          AND w.resignation_date != '' 
          AND replace(replace(a.date, '-', ''), '/', '') > replace(replace(w.resignation_date, '-', ''), '/', '')
          AND (a.normal_weight > 0.0 OR a.overtime_weight > 0.0 OR a.lodging_weight > 0.0 OR a.health_weight > 0.0 OR a.leader_weight > 0.0);
    """, (ym_db,))
    anomalies["resigned_attendance"] = [dict(r) for r in cursor.fetchall()]
    
    # 4. 유형 D (영구 저장된 엑셀 매칭 실패자 조회)
    cursor.execute("""
        SELECT id, timestamp, file_path, date, row_index, raw_worker_id, raw_name, raw_normal_weight, raw_overtime_weight, failure_reason
        FROM excel_match_failures
        WHERE substr(date, 1, 6) = ?
        ORDER BY date ASC, row_index ASC;
    """, (ym_db,))
    anomalies["excel_match_failures"] = [dict(r) for r in cursor.fetchall()]
    
    conn.close()
    return anomalies
