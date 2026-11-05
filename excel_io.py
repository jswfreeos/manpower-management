# excel_io.py
"""
[4단계] 데이터 정제 적용 엑셀 입출력 파서 모듈
"""
import os
import io
import datetime
import pandas as pd
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from typing import List, Dict, Any, Tuple
import db_manager
import config
import time

def safe_remove(file_path: str, retries: int = 7, delay: float = 0.15):
    """백신/보안 솔루션 선점 잠금(WinError 32)을 우회하기 위해 재시도 루프를 도는 안전 삭제 함수"""
    if not file_path or not os.path.exists(file_path):
        return
    for i in range(retries):
        try:
            os.remove(file_path)
            return
        except PermissionError:
            time.sleep(delay)
        except Exception:
            break
    # 최종 실패 시 에러 무시하여 프로그램 중단 예방
    try:
        if os.path.exists(file_path):
            # 조용히 백그라운드 삭제 시도 또는 방치
            pass
    except Exception:
        pass

def get_friendly_error_message(raw_error_str: str) -> str:
    """개발용 예외 에러 문구를 분석하여 사용자가 쉽게 조치할 수 있는 친절한 가이드라인을 반환합니다."""
    err_lower = raw_error_str.lower()
    
    if "stylesheet" in err_lower or "xml" in err_lower or "zip" in err_lower:
        return (
            "⚠️ [엑셀 파일 스타일 구조 손상 오류]\n\n"
            "ERP 시스템에서 내려받은 현대건설 엑셀 파일의 내부 XML 서식이 깨져 있어 분석할 수 없습니다.\n\n"
            "💡 해결 방법:\n"
            "1. 컴퓨터에서 해당 엑셀 파일을 Microsoft Excel 프로그램으로 직접 더블클릭하여 엽니다.\n"
            "2. 상단 메뉴에서 [파일] -> [다른 이름으로 저장]을 선택합니다.\n"
            "3. 동일한 Excel 통합 문서 (*.xlsx) 형식으로 새 이름으로 저장합니다. (Excel이 파일을 저장하면서 깨진 구조를 자동 치료합니다.)\n"
            "4. 새로 저장한 엑셀 파일을 시스템에 다시 업로드하여 가져오기를 실행해 주십시오."
        )
    elif "permission" in err_lower or "winerror 32" in err_lower or "file locks" in err_lower:
        return (
            "⚠️ [보안 솔루션 선점 대기 지연 오류]\n\n"
            "PC에 설치된 백신(알약 등) 또는 사내 문서보안 프로그램이 임시 파일을 검사하는 시간이 길어져 삭제가 지연되었습니다.\n\n"
            "💡 해결 방법: 화면을 새로고침하고 잠시 후 다시 실행 버튼을 눌러주십시오."
        )
    elif "column" in err_lower or "header" in err_lower:
        return (
            "⚠️ [엑셀 열 헤더 불일치 오류]\n\n"
            "업로드하신 파일의 주민번호, 날짜 등의 열 헤더 이름이 규격과 맞지 않습니다.\n\n"
            "💡 해결 방법: 표준 엑셀 양식을 다운로드하여 동일한 형식으로 데이터가 적혀있는지 대조 후 업로드해 주십시오."
        )
    else:
        return f"⚠️ [가져오기 중 오류 발생]\n\n실패 원인: {raw_error_str}"

def generate_worker_template() -> bytes:
    """근로자 일괄등록을 위한 표준 엑셀 양식 파일을 생성하여 바이너리로 반환합니다."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "근로자 일괄등록 양식"
    ws.views.sheetView[0].showGridLines = True
    # 헤더 정의 (숙소, 보건, 팀장 제외, 사번 -> 주민번호, 주월차제외 추가)
    headers = [
        "주민번호*", "성명*", "소속팀", "직종/공종", 
        "입사일(YYYY-MM-DD)*", "퇴사일(YYYY-MM-DD)", "주월차제외", "비고"
    ]
    ws.append(headers)
    # 샘플 데이터 추가
    sample_row = [
        "850315-1852212", "홍길동", "배관1팀", "배관공",
        "2026-01-01", "", "", "특이사항 없음"
    ]
    ws.append(sample_row)
    # 서식 적용
    header_fill = PatternFill(start_color="1F497D", end_color="1F497D", fill_type="solid") # 남색
    header_font = Font(name="맑은 고딕", size=10, bold=True, color="FFFFFF")
    data_font = Font(name="맑은 고딕", size=10)
    align_center = Alignment(horizontal="center", vertical="center")
    thin_border = Border(
        left=Side(style='thin', color='D9D9D9'),
        right=Side(style='thin', color='D9D9D9'),
        top=Side(style='thin', color='D9D9D9'),
        bottom=Side(style='thin', color='D9D9D9')
    )
    # 헤더 스타일링
    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = align_center
        cell.border = thin_border
    # 데이터 행 스타일링
    for row_idx in range(2, 3):
        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            cell.font = data_font
            cell.alignment = align_center
            cell.border = thin_border
    # 열 너비 자동 조정
    ws.column_dimensions["A"].width = 25
    ws.column_dimensions["B"].width = 15
    ws.column_dimensions["C"].width = 18
    ws.column_dimensions["D"].width = 18
    ws.column_dimensions["E"].width = 25
    ws.column_dimensions["F"].width = 25
    ws.column_dimensions["G"].width = 15
    ws.column_dimensions["H"].width = 30
    # 안내 메시지 시트 추가
    ws_guide = wb.create_sheet(title="작성 안내")
    ws_guide.views.sheetView[0].showGridLines = True
    ws_guide.column_dimensions["A"].width = 30
    ws_guide.column_dimensions["B"].width = 60
    ws_guide.append(["항목명", "설명 및 작성 규칙"])
    ws_guide.append(["주민번호*", "근로자의 고유 주민등록번호 (필수, 예: 850315-1852212, 중복 불가)"])
    ws_guide.append(["성명*", "근로자의 실명 (필수, 공백 자동 제거됨)"])
    ws_guide.append(["소속팀", "소속 팀명 (예: 배관1팀, 전기2팀)"])
    ws_guide.append(["직종/공종", "실무 직종명 (예: 배관공, 계장공, 조공)"])
    ws_guide.append(["입사일*", "근로 계약상의 입사 연월일 (필수, YYYY-MM-DD 형식, 예: 2026-05-15)"])
    ws_guide.append(["퇴사일", "퇴사한 근로자일 경우 퇴사 연월일 입력 (YYYY-MM-DD 형식, 재직 중이면 공란)"])
    ws_guide.append(["주월차제외", "주휴/월차 계산 대상에서 제외할지 여부 ('제외' 또는 '1' 기입 시 제외되며 공란 시 대상 포함)"])
    ws_guide.append(["비고", "근로자 특이사항 및 메모 (선택사항)"])
    # 가이드 헤더 스타일링
    for c in range(1, 3):
        cell = ws_guide.cell(row=1, column=c)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = align_center
        cell.border = thin_border
    for r in range(2, 10):
        ws_guide.cell(row=r, column=1).font = Font(name="맑은 고딕", size=10, bold=True)
        ws_guide.cell(row=r, column=1).border = thin_border
        ws_guide.cell(row=r, column=2).font = data_font
        ws_guide.cell(row=r, column=2).border = thin_border
    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()
def generate_daily_attendance_template() -> bytes:
    """일일 출역일보 업로드를 위한 표준 엑셀 양식 파일을 생성하여 바이너리로 반환합니다."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "일일출역일보 업로드 양식"
    ws.views.sheetView[0].showGridLines = True
    # 헤더 정의
    headers = ["주민번호*", "성명*", "일반공수", "연장공수"]
    ws.append(headers)
    # 샘플 데이터
    sample_row = ["850315-1852212", "홍길동", "1.0", "0.5"]
    ws.append(sample_row)
    # 서식 적용
    header_fill = PatternFill(start_color="1F497D", end_color="1F497D", fill_type="solid") # 남색
    header_font = Font(name="맑은 고딕", size=10, bold=True, color="FFFFFF")
    data_font = Font(name="맑은 고딕", size=10)
    align_center = Alignment(horizontal="center", vertical="center")
    thin_border = Border(
        left=Side(style='thin', color='D9D9D9'),
        right=Side(style='thin', color='D9D9D9'),
        top=Side(style='thin', color='D9D9D9'),
        bottom=Side(style='thin', color='D9D9D9')
    )
    # 헤더 스타일링
    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = align_center
        cell.border = thin_border
    # 데이터 행 스타일링
    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=2, column=col_idx)
        cell.font = data_font
        cell.alignment = align_center
        cell.border = thin_border
    # 열 너비 조정
    ws.column_dimensions["A"].width = 25
    ws.column_dimensions["B"].width = 15
    ws.column_dimensions["C"].width = 15
    ws.column_dimensions["D"].width = 15
    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()
def parse_and_import_workers(file_content: bytes, user_id: str) -> Tuple[int, int, List[str]]:
    """
    업로드된 근로자 등록 엑셀 파일을 읽어 유효성을 검증하고 데이터베이스에 등록합니다.
    returns: (신규 등록 수, 수정 등록 수, 에러 메시지 리스트)
    """
    errors = []
    valid_workers = []
    # 날짜 파싱 헬퍼 - datetime/date 객체, 엑셀 serial, 문자열 모두 처리
    def _parse_date_cell(raw_val):
        """
        엑셀 셀에서 읽은 값을 datetime.datetime으로 변환합니다.
        - datetime/date 객체: 그대로 반환
        - 문자열: YYYY-MM-DD, YYYY.MM.DD, YYYY/MM/DD, YYYY-MM-DD HH:MM:SS 등 지원
        """
        if isinstance(raw_val, (datetime.datetime, datetime.date)):
            return datetime.datetime(
                raw_val.year, raw_val.month, raw_val.day
            )
        s = str(raw_val).strip()
        # 시간 부분 제거 (예: "2026-04-07 00:00:00")
        s = s.split(" ")[0].split("T")[0]
        # 구분자 통일
        s = s.replace(".", "-").replace("/", "-")
        for fmt in ("%Y-%m-%d", "%Y%m%d"):
            try:
                return datetime.datetime.strptime(s, fmt)
            except ValueError:
                continue
        raise ValueError(f"날짜 형식 인식 불가: {raw_val!r}")
    try:
        # Excel 로드 (날짜 열은 자동 타입 추론 후 별도 파싱 처리)
        df = pd.read_excel(io.BytesIO(file_content), sheet_name=0, dtype=str)
    except Exception as e:
        return 0, 0, [f"엑셀 파일을 열 수 없습니다: {e}"]
    # 열 검증 (필수 헤더 존재 여부 확인)
    required_cols = ["주민번호*", "성명*", "입사일(YYYY-MM-DD)*"]
    missing_cols = [c for c in required_cols if c not in df.columns]
    if missing_cols:
        # 다양한 대체 헤더명 허용 처리
        fallback_map = {
            "주민번호*": ["주민번호", "주민등록번호*", "주민등록번호", "사번*", "사번", "ID", "worker_id"],
            "성명*": ["성명", "이름*", "이름", "성함*", "성함", "name"],
            "입사일(YYYY-MM-DD)*": ["입사일(YYYY-MM-DD)", "입사일*", "입사일"]
        }
        for k, v_list in fallback_map.items():
            if k in missing_cols:
                for v in v_list:
                    if v in df.columns:
                        df.rename(columns={v: k}, inplace=True)
                        missing_cols.remove(k)
                        break
        if missing_cols:
            return 0, 0, [f"필수 열 헤더가 존재하지 않습니다: {', '.join(missing_cols)}"]
    seen_ids = set()
    # 한 행씩 검증
    for idx, row in df.iterrows():
        row_num = idx + 2 # 엑셀 실제 행 번호 (헤더가 1)
        # 1. 주민번호 검증
        worker_id_raw = row.get("주민번호*")
        if pd.isna(worker_id_raw) or str(worker_id_raw).strip() == "":
            errors.append(f"{row_num}행: 주민번호가 비어있습니다.")
            continue
        worker_id = str(worker_id_raw).strip()
        # 엑셀 파일 내 주민번호 중복 검증
        if worker_id in seen_ids:
            errors.append(f"{row_num}행: 파일 내에 주민번호({worker_id})가 중복하여 존재합니다.")
            continue
        seen_ids.add(worker_id)
        # 2. 성명 검증
        name_raw = row.get("성명*")
        if pd.isna(name_raw) or str(name_raw).strip() == "":
            errors.append(f"{row_num}행: 성명이 비어있습니다.")
            continue
        name = str(name_raw).strip()
        # 2.5 주월차제외 여부 독출
        exclude_val_raw = row.get("주월차제외")
        if "주월차제외" not in row and "주월차 제외" in row:
            exclude_val_raw = row.get("주월차 제외")
        exclude_holiday = 0
        if not pd.isna(exclude_val_raw):
            val_str = str(exclude_val_raw).strip().lower()
            if val_str in ("1", "1.0", "true", "o", "y", "yes", "예", "제외"):
                exclude_holiday = 1

        # 3. 날짜 검증 (입사일)
        hire_date_raw = row.get("입사일(YYYY-MM-DD)*")
        if pd.isna(hire_date_raw) or str(hire_date_raw).strip() in ("", "nan", "NaT", "None"):
            errors.append(f"{row_num}행: 입사일이 비어있습니다.")
            continue
        try:
            dt_hire = _parse_date_cell(hire_date_raw)
            hire_date = dt_hire.strftime("%Y-%m-%d")
        except ValueError:
            errors.append(f"{row_num}행: 입사일({hire_date_raw!r}) 형식이 올바르지 않습니다. YYYY-MM-DD 형식이어야 합니다.")
            continue
        # 4. 날짜 검증 (퇴사일 - 선택)
        resignation_date_raw = row.get("퇴사일(YYYY-MM-DD)")
        resignation_date = None
        if not pd.isna(resignation_date_raw) and str(resignation_date_raw).strip() not in ("", "nan", "NaT", "None"):
            try:
                dt_res = _parse_date_cell(resignation_date_raw)
                resignation_date = dt_res.strftime("%Y-%m-%d")
                # 퇴사일이 입사일보다 빠른지 검증
                if dt_res < dt_hire:
                    errors.append(f"{row_num}행: 퇴사일({resignation_date})이 입사일({hire_date})보다 빠를 수 없습니다.")
                    continue
            except ValueError:
                errors.append(f"{row_num}행: 퇴사일({resignation_date_raw!r}) 형식이 올바르지 않습니다. YYYY-MM-DD 형식이어야 합니다.")
                continue
        # 5. 수당 대상 여부는 더 이상 관리하지 않으므로 기본값 0으로 통일
        has_lodging = 0
        has_health = 0
        is_team_leader = 0
        team = str(row.get("소속팀")).strip() if not pd.isna(row.get("소속팀")) else None
        trade = str(row.get("직종/공종")).strip() if not pd.isna(row.get("직종/공종")) else None
        remarks = str(row.get("비고")).strip() if not pd.isna(row.get("비고")) else None
        valid_workers.append({
            "worker_id": worker_id,
            "name": name,
            "has_lodging": has_lodging,
            "has_health": has_health,
            "is_team_leader": is_team_leader,
            "hire_date": hire_date,
            "resignation_date": resignation_date,
            "team": team,
            "trade": trade,
            "remarks": remarks
        })
    if errors:
        # 에러가 한 개라도 있으면 트랜잭션을 보호하기 위해 중단하고 리턴
        return 0, 0, errors
    # 데이터베이스 적재 진행
    if valid_workers:
        added, updated = db_manager.bulk_insert_workers(valid_workers, user_id)
        return added, updated, []
    return 0, 0, ["엑셀 파일에 등록할 데이터 행이 존재하지 않습니다."]
# 일일 출역 파일(일일 출역일보) 가져오기 기능
def import_daily_excel(file_content: bytes, file_name: str, date_str: str, user_id: str) -> Tuple[int, List[Dict[str, Any]]]:
    """
    일일 출역 엑셀 파일(사번, 이름, 일반공수, 연장공수)을 파싱하여 데이터베이스에 저장합니다.
    검증 실패 시 excel_match_failures 테이블에 기록합니다.
    """
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        df = pd.read_excel(io.BytesIO(file_content), sheet_name=0)
    except Exception as e:
        db_manager.log_import(file_name, user_id, 0, "실패", f"엑셀 읽기 에러: {e}")
        raise ValueError(f"엑셀 파일을 파싱할 수 없습니다: {e}")
    # 열이름 매핑 지원
    col_mapping = {
        "주민번호": ["주민번호", "주민등록번호", "사번", "사원번호", "ID", "worker_id", "주민번호*", "주민등록번호*", "사번*"],
        "이름": ["이름", "성명", "성함", "name", "이름*", "성명*"],
        "일반공수": ["일반공수", "일반", "공수", "normal_weight"],
        "연장공수": ["연장공수", "연장", "overtime_weight"]
    }
    mapped_cols = {}
    for standard_col, aliases in col_mapping.items():
        found = False
        for col in df.columns:
            if str(col).strip() in aliases:
                mapped_cols[standard_col] = col
                found = True
                break
        if not found:
            # 필수 열이 없으면 에러
            if standard_col in ["주민번호", "이름", "일반공수"]:
                db_manager.log_import(file_name, user_id, 0, "실패", f"필수 열 헤더 누락: {standard_col}")
                raise ValueError(f"엑셀 파일에서 '{standard_col}' 열을 찾을 수 없습니다. 열 이름을 확인해 주세요.")
    # 근로자 목록 조회 (매칭 용도)
    db_workers = db_manager.get_all_workers()
    worker_by_id = {w["worker_id"]: w for w in db_workers}
    # 동명이인 매칭 처리용 딕셔너리 구축
    workers_by_name = {}
    for w in db_workers:
        name = w["name"]
        workers_by_name.setdefault(name, []).append(w)
    records_to_save = []
    failures = []
    conn = db_manager.get_db_connection()
    cursor = conn.cursor()
    for idx, row in df.iterrows():
        row_num = idx + 2 # 엑셀 실제 행
        raw_id = row.get(mapped_cols.get("주민번호"))
        raw_name = row.get(mapped_cols.get("이름"))
        raw_normal = row.get(mapped_cols.get("일반공수"))
        raw_overtime = row.get(mapped_cols.get("연장공수"), 0.0)
        # 기본 공백 제거 및 문자열화
        name_clean = str(raw_name).strip() if not pd.isna(raw_name) else ""
        id_clean = None
        if not pd.isna(raw_id):
            try:
                # 주민번호(또는 사번)을 정수로 파싱 후 문자열로 변환 (예: 10001.0 -> "10001")
                id_clean = str(int(float(raw_id)))
            except ValueError:
                id_clean = str(raw_id).strip()
        # 1. 밸리데이션 검사
        failure_reason = None
        if not name_clean and not id_clean:
            # 사번과 이름이 모두 비어있는 행은 그냥 스킵
            continue
        # 일반공수 값이 비어있는 경우(누락공수 등) 0.0으로 기본 처리
        try:
            val_normal = float(raw_normal) if not pd.isna(raw_normal) else 0.0
            val_overtime = float(raw_overtime) if not pd.isna(raw_overtime) else 0.0
            if val_normal < 0.0 or val_overtime < 0.0:
                failure_reason = f"공수 값은 음수일 수 없습니다. (일반:{val_normal}, 연장:{val_overtime})"
            elif val_normal > 2.0 or val_overtime > 2.0:
                failure_reason = f"단일 공수 가중치 제한(2.0)을 초과했습니다. (일반:{val_normal}, 연장:{val_overtime})"
            elif (val_normal + val_overtime) > config.MAX_DAILY_TOTAL_HOURS:
                failure_reason = f"하루 최대 공수 시간 제한({config.MAX_DAILY_TOTAL_HOURS})을 초과했습니다. (합계:{val_normal + val_overtime})"
        except ValueError:
                failure_reason = f"공수 값 형식이 올바르지 않습니다. (일반:{raw_normal}, 연장:{raw_overtime})"
        if failure_reason:
            failures.append({
                "row_index": row_num,
                "raw_worker_id": str(raw_id),
                "raw_name": name_clean,
                "raw_normal_weight": None,
                "raw_overtime_weight": None,
                "failure_reason": failure_reason
            })
            continue
        # 2. 사번/성명 마스터 테이블 매칭 진행
        target_worker_id = None
        if id_clean and id_clean in worker_by_id:
            # 사번으로 완벽 매칭
            target_worker_id = id_clean
        elif name_clean:
            # 주민번호 누락 시 이름으로 매칭 시도
            matched_workers = workers_by_name.get(name_clean, [])
            if len(matched_workers) == 1:
                target_worker_id = matched_workers[0]["worker_id"]
            elif len(matched_workers) > 1:
                failure_reason = f"동명이인이 존재하여 주민번호 매칭이 필요합니다. (성명: '{name_clean}')"
            else:
                failure_reason = f"등록되지 않은 근로자 성명입니다. (성명: '{name_clean}')"
        else:
            failure_reason = f"주민번호({id_clean})가 마스터 테이블에 존재하지 않으며 성명도 비어있습니다."
        if failure_reason:
            failures.append({
                "row_index": row_num,
                "raw_worker_id": str(raw_id) if not pd.isna(raw_id) else None,
                "raw_name": name_clean,
                "raw_normal_weight": val_normal,
                "raw_overtime_weight": val_overtime,
                "failure_reason": failure_reason
            })
            continue
        # 3. 매칭 완료 - 저장 준비
        worker_info = worker_by_id[target_worker_id]
        # 사용자가 직접 입력하므로 업로드 시 0.0으로 기본 설정
        lodging_w = 0.0
        health_w = 0.0
        leader_w = 0.0
        # 기존 버전을 데이터베이스에서 가져오기 (낙관적 락 연동)
        cursor.execute("SELECT version FROM daily_attendance WHERE date = ? AND worker_id = ?;", (date_str, target_worker_id))
        ver_row = cursor.fetchone()
        version = ver_row["version"] if ver_row else 1
        records_to_save.append({
            "date": date_str,
            "worker_id": target_worker_id,
            "normal_weight": val_normal,
            "overtime_weight": val_overtime,
            "lodging_weight": lodging_w,
            "health_weight": health_w,
            "leader_weight": leader_w,
            "status": "출근" if val_normal > 0.0 else "휴무",
            "is_weekly_manual": 0,
            "is_monthly_manual": 0,
            "version": version
        })
    # 매칭 실패 건 DB excel_match_failures 테이블에 기입
    if failures:
        for f in failures:
            cursor.execute("""
                INSERT INTO excel_match_failures (
                    timestamp, file_path, date, row_index, raw_worker_id, raw_name, 
                    raw_normal_weight, raw_overtime_weight, failure_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (timestamp, file_name, date_str, f["row_index"], f["raw_worker_id"], 
                  f["raw_name"], f["raw_normal_weight"], f["raw_overtime_weight"], f["failure_reason"]))
    conn.commit()
    conn.close()
    # 매칭 성공 건 일괄 벌크 저장
    if records_to_save:
        db_manager.save_attendance_bulk(records_to_save, user_id, force_overwrite=True)
    db_manager.log_import(file_name, user_id, len(records_to_save), "성공" if not failures else "일부 매칭실패", 
                          f"성공: {len(records_to_save)}건, 실패: {len(failures)}건")
    return len(records_to_save), failures
# 월말 보고서(Excel) 내보내기 기능
def export_monthly_excel(df_pivot: pd.DataFrame, year_month: str, df_custom: pd.DataFrame = None) -> bytes:
    """월말 공수 정산표 및 추가 수당 집계표 데이터를 시트별 서식을 갖춘 엑셀 바이너리로 변환합니다."""
    wb = openpyxl.Workbook()
    ws1 = wb.active
    ws1.title = f"{year_month} 공수정산표"
    
    header_fill = PatternFill(start_color="1F497D", end_color="1F497D", fill_type="solid") # Navy
    header_font = Font(name="맑은 고딕", size=9, bold=True, color="FFFFFF")
    data_font = Font(name="맑은 고딕", size=9)
    total_fill = PatternFill(start_color="E6F2FF", end_color="E6F2FF", fill_type="solid")
    total_font = Font(name="맑은 고딕", size=9, bold=True)
    align_center = Alignment(horizontal="center", vertical="center")
    thin_border = Border(
        left=Side(style='thin', color='D9D9D9'),
        right=Side(style='thin', color='D9D9D9'),
        top=Side(style='thin', color='D9D9D9'),
        bottom=Side(style='thin', color='D9D9D9')
    )

    def write_and_style_sheet(ws, df):
        ws.views.sheetView[0].showGridLines = True
        headers = list(df.columns)
        ws.append(headers)
        for idx, row in df.iterrows():
            ws.append(list(row))
        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=1, column=col_idx)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = align_center
            cell.border = thin_border
        resigned_fill = PatternFill(start_color="FDE8E8", end_color="FDE8E8", fill_type="solid") # Soft Red
        resigned_font = Font(name="맑은 고딕", size=9, color="9C0006", bold=True)
        for row_idx in range(2, ws.max_row + 1):
            is_total_row = (ws.cell(row=row_idx, column=1).value == "일일 합계")
            row_name_val = str(ws.cell(row=row_idx, column=2).value or "")
            row_status_val = str(ws.cell(row=row_idx, column=3).value or "")
            is_resigned_row = ("(퇴사" in row_name_val) or ("퇴사" in row_status_val)
            for col_idx in range(1, len(headers) + 1):
                cell = ws.cell(row=row_idx, column=col_idx)
                cell.border = thin_border
                if is_total_row:
                    cell.font = total_font
                    cell.fill = total_fill
                elif is_resigned_row:
                    cell.font = resigned_font
                    cell.fill = resigned_fill
                else:
                    cell.font = data_font
                cell.alignment = align_center
        for col in ws.columns:
            col_name = col[0].value
            col_letter = openpyxl.utils.get_column_letter(col[0].column)
            if col_name in ["주민번호", "사번", "성명"]:
                ws.column_dimensions[col_letter].width = 12
            elif col_name in ["팀", "직종"]:
                ws.column_dimensions[col_letter].width = 15
            elif col_name in ["출역", "연장", "주차", "월차", "숙소", "보건", "팀장", "기타", "총공수", "추가수당 합계"] or (col_name and str(col_name).endswith("수당")):
                ws.column_dimensions[col_letter].width = 14
            else:
                ws.column_dimensions[col_letter].width = 6

    # Sheet 1: 메인 공수정산표
    write_and_style_sheet(ws1, df_pivot)

    # Sheet 2: 추가 수당 집계표 (df_custom이 존재하고 비어있지 않은 경우)
    if df_custom is not None and not df_custom.empty:
        ws2 = wb.create_sheet(title=f"{year_month} 추가수당 집계표")
        write_and_style_sheet(ws2, df_custom)

    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()
# --- 기능 고도화: 외부 엑셀 연동 및 일괄 공수 입력 파서 ---
def repair_excel_file_via_excel(file_path: str) -> str:
    """
    손상된 스타일 XML 정보가 있는 엑셀 파일을 openpyxl로 안전하게 읽어
    새로운 임시 경로에 재저장하여 구조를 정비합니다.
    win32com/Excel 설치 없이 동작합니다.
    """
    import os
    import tempfile
    abs_path = os.path.abspath(file_path)
    temp_dir = tempfile.gettempdir()
    temp_name = f"repaired_{datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')}.xlsx"
    repaired_path = os.path.join(temp_dir, temp_name)
    wb = None
    # openpyxl: keep_vba=False, read_only=False 로 열어 재저장 (스타일 문제 자동 정비)
    try:
        wb = openpyxl.load_workbook(abs_path, data_only=True, keep_vba=False)
        wb.save(repaired_path)
    except Exception as e:
        # 복구 실패 시 원본 경로를 그대로 반환하여 파싱 시도
        return abs_path
    finally:
        if wb:
            try:
                wb.close()
            except Exception:
                pass
    return repaired_path
def parse_hyundai_daily_attendance(file_path: str, date_str: str, user_id: str) -> Dict[str, Any]:
    """
    현대건설 일일출역현황 양식을 파싱하여 출역이 1인 대상자의 '기본' 값은 일반공수, '연장' 값은 연장공수로 반영합니다.
    - date_str: YYYY-MM-DD 형식
    """
    import re
    import os
    db_date = date_str.replace("-", "") # YYYYMMDD
    repaired_path = None
    wb = None
    # 1. 엑셀 파일 복구
    try:
        repaired_path = repair_excel_file_via_excel(file_path)
    except Exception as e:
        return {"success": False, "error": f"파일 구조 복구 실패: {e}"}
    try:
        wb = openpyxl.load_workbook(repaired_path, data_only=True)
        sheet = wb.active  # 첫 번째 시트 로드
        # 2. 근로자 DB 매핑용 조회
        conn = db_manager.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT worker_id, name, has_lodging, has_health, is_team_leader FROM workers;")
        workers_db = {w["worker_id"]: dict(w) for w in cursor.fetchall()}
        success_count = 0
        skip_count = 0
        unmatched_workers = []
        # 행 데이터를 순회하며 매칭
        # Row 1: 헤더, Row 2: 서브헤더, Row 3: 합계 행, Row 4부터 실데이터
        for r_idx in range(4, sheet.max_row + 1):
            col0 = sheet.cell(row=r_idx, column=1).value
            if not col0:
                continue
            col0_str = str(col0).strip()
            # 이름(주민번호) 양식 파싱 (예: 홍길동(850315-1852212))
            m = re.match(r"^([^\(]+)\(([^)]+)\)", col0_str)
            if not m:
                continue
            name = m.group(1).strip()
            resident_no = m.group(2).strip() # worker_id 매칭 키
            # 기본(일반공수), 연장(연장공수), 출역 여부 획득
            basic_val = sheet.cell(row=r_idx, column=5).value  # '기본' (5번째 열)
            overtime_val = sheet.cell(row=r_idx, column=6).value  # '연장' (6번째 열)
            attendance_state = sheet.cell(row=r_idx, column=7).value  # '출역' (7번째 열)
            # 출역 상태가 1 또는 '1' 또는 'O'인 사람만 유효 출근으로 처리
            is_present = False
            if attendance_state in [1, "1", "O", "o"]:
                is_present = True
            if not is_present:
                skip_count += 1
                continue
            # DB의 근로자 정보와 매칭 확인
            if resident_no not in workers_db:
                unmatched_workers.append(f"{name}({resident_no})")
                continue
            worker = workers_db[resident_no]
            normal_weight = float(basic_val or 0.0)
            overtime_weight = float(overtime_val or 0.0)
            # 기존 출역 정보 있는지 조회
            cursor.execute("""
                SELECT lodging_weight, health_weight, leader_weight, version 
                FROM daily_attendance 
                WHERE date = ? AND worker_id = ?;
            """, (db_date, resident_no))
            existing = cursor.fetchone()
            if existing:
                # 기존 데이터 갱신 (일반, 연장공수 교체)
                cursor.execute("""
                    UPDATE daily_attendance
                    SET normal_weight = ?, overtime_weight = ?, status = '출근', version = version + 1
                    WHERE date = ? AND worker_id = ?;
                """, (normal_weight, overtime_weight, db_date, resident_no))
            else:
                # 사용자가 직접 입력하므로 신규 등록 시 0.0으로 기본 설정
                lodging_w = 0.0
                health_w = 0.0
                leader_w = 0.0
                cursor.execute("""
                    INSERT INTO daily_attendance (
                        date, worker_id, normal_weight, overtime_weight, lodging_weight, 
                        health_weight, leader_weight, weekly_holiday, monthly_holiday, status, version
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, 0.0, 0.0, '출근', 1);
                """, (db_date, resident_no, normal_weight, overtime_weight, lodging_w, health_w, leader_w))
            # 감사 로그 기록
            db_manager.log_audit(
                user_id=user_id,
                worker_id=resident_no,
                action=f"현대건설 일일출역 연동 입력",
                before_value="미존재 혹은 이전 값",
                after_value=f"일반:{normal_weight}, 연장:{overtime_weight}",
                conn=conn
            )
            success_count += 1
        conn.commit()
        conn.close()
        return {
            "success": True,
            "success_count": success_count,
            "skip_count": skip_count,
            "unmatched_workers": unmatched_workers
        }
    except Exception as e:
        friendly_msg = get_friendly_error_message(str(e))
        return {"success": False, "error": friendly_msg}
    finally:
        if wb:
            try:
                wb.close()
            except Exception:
                pass
        if repaired_path and os.path.exists(repaired_path):
            safe_remove(repaired_path)
def generate_bulk_attendance_template(custom_allowances: List[str]) -> bytes:
    """선택적 덮어쓰기가 가능한 일괄 공수 입력을 위한 표준 엑셀 양식을 생성합니다."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "공수 일괄 입력"
    ws.views.sheetView[0].showGridLines = True
    # 주민번호로 변경, 보건수당 제외
    headers = ["주민번호*", "성명*", "날짜(YYYY-MM-DD)*", "일반공수", "연장공수", "전월 누락공수", "차감공수", "숙소수당", "팀장수당"]
    for allowance in custom_allowances:
        headers.append(f"{allowance}수당")
    ws.append(headers)
    # 가이드 행 기입
    guide_row = ["850315-1852212", "홍길동", "2026-07-02", "1.0", "0.5", "0.0", "0.0", "1.0", "1.0"]
    for _ in custom_allowances:
        guide_row.append("")
    ws.append(guide_row)
    # 스타일 장식
    header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid") # 청록색 계열
    header_font = Font(name="맑은 고딕", size=10, bold=True, color="FFFFFF")
    data_font = Font(name="맑은 고딕", size=10)
    align_center = Alignment(horizontal="center", vertical="center")
    thin_border = Border(
        left=Side(style='thin', color='D9D9D9'),
        right=Side(style='thin', color='D9D9D9'),
        top=Side(style='thin', color='D9D9D9'),
        bottom=Side(style='thin', color='D9D9D9')
    )
    for c_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=c_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = align_center
        cell.border = thin_border
    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=2, column=col_idx)
        cell.font = data_font
        cell.alignment = align_center
        cell.border = thin_border
    ws.column_dimensions["A"].width = 25
    ws.column_dimensions["B"].width = 15
    ws.column_dimensions["C"].width = 25
    for c_idx in range(4, len(headers) + 1):
        col_letter = openpyxl.utils.get_column_letter(c_idx)
        ws.column_dimensions[col_letter].width = 15
    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()
def parse_and_import_bulk_attendance(file_path: str, user_id: str) -> Dict[str, Any]:
    """
    선택적 덮어쓰기식 공수 일괄 등록 엑셀을 로드하여 데이터베이스에 반영합니다.
    기입된 항목(일반, 연장 등)만 선택적으로 업데이트하고, 비어있는 열은 기존 수치를 유지합니다.
    """
    import os
    # 1. 엑셀 파일 복구
    repaired_path = None
    wb = None
    try:
        repaired_path = repair_excel_file_via_excel(file_path)
    except Exception as e:
        return {"success": False, "error": f"파일 구조 복구 실패: {e}"}
    try:
        wb = openpyxl.load_workbook(repaired_path, data_only=True)
        ws = wb.active
        # 1. 헤더 추출
        headers = [str(ws.cell(row=1, column=c).value).strip() for c in range(1, ws.max_column + 1)]
        # 주민번호(사번) 열 찾기
        worker_id_col = None
        for h in ["주민번호*", "주민번호", "주민등록번호*", "주민등록번호", "사번*", "사번", "사원번호", "ID", "worker_id"]:
            if h in headers:
                worker_id_col = h
                break
        # 날짜 열 찾기
        date_col = None
        for h in ["날짜(YYYY-MM-DD)*", "날짜(YYYY-MM-DD)", "날짜*", "날짜"]:
            if h in headers:
                date_col = h
                break
        if not worker_id_col or not date_col:
            return {"success": False, "error": "엑셀 필수 헤더('주민번호*', '날짜(YYYY-MM-DD)*')가 누락되었습니다."}
        col_indices = {h: headers.index(h) for h in headers}
        # DB 근로자 및 정의된 커스텀 수당 리스트 로드
        conn = db_manager.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT worker_id, name, has_lodging, has_health, is_team_leader FROM workers;")
        workers_db = {w["worker_id"]: dict(w) for w in cursor.fetchall()}
        custom_types = [t["type_id"] for t in db_manager.get_custom_weight_types(conn=conn)]
        success_count = 0
        error_rows = []
        # 헬퍼 함수: 별칭 대응 기입값 조회
        def get_patched_value_aliases(aliases, existing_val, default_val=0.0):
            for alias in aliases:
                if alias in col_indices:
                    val = ws.cell(row=r_idx, column=col_indices[alias] + 1).value
                    if val is not None and str(val).strip() != "":
                        try:
                            return float(val)
                        except ValueError:
                            pass
            return existing_val if existing_val is not None else default_val
        # 헬퍼 함수: 날짜를 유연하게 YYYYMMDD로 파싱
        def _parse_date_flexible(raw_val) -> str:
            if isinstance(raw_val, (datetime.datetime, datetime.date)):
                return raw_val.strftime("%Y%m%d")
            s = str(raw_val).strip()
            # 시간 부분 분리 (예: "2026-07-03 00:00:00" -> "2026-07-03")
            s = s.split(" ")[0].split("T")[0]
            # 소수점 제거 (숫자타입 실수 오인 방지)
            if "." in s and s.replace(".", "").isdigit():
                s = s.split(".")[0]
            s = s.replace("-", "").replace("/", "").replace(".", "").replace(" ", "")
            if len(s) == 8:
                return s
            elif len(s) == 6:
                # YYMMDD -> 20YYMMDD
                return "20" + s
            raise ValueError(f"자릿수 불일치: {raw_val}")
        # 행 스캔 (2행부터 데이터 행)
        for r_idx in range(2, ws.max_row + 1):
            worker_id_val = ws.cell(row=r_idx, column=col_indices[worker_id_col] + 1).value
            date_val = ws.cell(row=r_idx, column=col_indices[date_col] + 1).value
            if not worker_id_val or not date_val:
                continue
            worker_id = str(worker_id_val).strip()
            try:
                date_raw = _parse_date_flexible(date_val)
            except Exception:
                error_rows.append(f"Row {r_idx}: 날짜 형식이 잘못되었습니다 ({date_val})")
                continue
            if worker_id not in workers_db:
                error_rows.append(f"Row {r_idx}: 등록되지 않은 주민번호입니다 ({worker_id})")
                continue
            worker = workers_db[worker_id]
            # 기존 출역 정보 획득
            cursor.execute("""
                SELECT normal_weight, overtime_weight, lodging_weight, health_weight, leader_weight, 
                       weekly_holiday, monthly_holiday, prev_month_missing, deduction, status, version 
                FROM daily_attendance 
                WHERE date = ? AND worker_id = ?;
            """, (date_raw, worker_id))
            existing_record = cursor.fetchone()
            # 셀 값 갱신 타겟 리스트 작성
            # 데이터가 비어있지 않으면 교체, 비어있으면 기존값 유지
            def get_patched_value(col_header, existing_val, default_val=0.0):
                if col_header in col_indices:
                    val = ws.cell(row=r_idx, column=col_indices[col_header] + 1).value
                    if val is not None and str(val).strip() != "":
                        return float(val)
                return existing_val if existing_val is not None else default_val
            if existing_record:
                rec = dict(existing_record)
                n_w = get_patched_value("일반공수", rec["normal_weight"])
                o_w = get_patched_value("연장공수", rec["overtime_weight"])
                p_m = get_patched_value_aliases(["전월 누락공수", "전월누락공수", "전월 누락 공수", "전월누락", "누락공수", "누락"], rec["prev_month_missing"])
                ded = get_patched_value_aliases(["차감공수", "차감", "공수차감", "deduction"], rec["deduction"])
                l_w = get_patched_value("숙소수당", rec["lodging_weight"])
                h_w = get_patched_value("보건수당", rec["health_weight"])
                le_w = get_patched_value("팀장수당", rec["leader_weight"])
                status = rec["status"]
                # 덮어쓰기 업데이트
                cursor.execute("""
                    UPDATE daily_attendance
                    SET normal_weight = ?, overtime_weight = ?, prev_month_missing = ?, deduction = ?, lodging_weight = ?, 
                        health_weight = ?, leader_weight = ?, version = version + 1
                    WHERE date = ? AND worker_id = ?;
                """, (n_w, o_w, p_m, ded, l_w, h_w, le_w, date_raw, worker_id))
            else:
                # 사용자가 직접 입력하므로 신규 데이터 없는 경우 0.0으로 기본 설정
                def_l = 0.0
                def_h = 0.0
                def_le = 0.0
                n_w = get_patched_value("일반공수", 0.0)
                o_w = get_patched_value("연장공수", 0.0)
                p_m = get_patched_value_aliases(["전월 누락공수", "전월누락공수", "전월 누락 공수", "전월누락", "누락공수", "누락"], 0.0)
                ded = get_patched_value_aliases(["차감공수", "차감", "공수차감", "deduction"], 0.0)
                l_w = get_patched_value("숙소수당", def_l)
                h_w = get_patched_value("보건수당", def_h)
                le_w = get_patched_value("팀장수당", def_le)
                cursor.execute("""
                    INSERT INTO daily_attendance (
                        date, worker_id, normal_weight, overtime_weight, prev_month_missing, deduction, lodging_weight, 
                        health_weight, leader_weight, weekly_holiday, monthly_holiday, status, version
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0.0, 0.0, '출근', 1);
                """, (date_raw, worker_id, n_w, o_w, p_m, ded, l_w, h_w, le_w))
            # 커스텀 추가 수당 컬럼 연동 스캔 및 덮어쓰기
            for custom_type in custom_types:
                col_name = f"{custom_type}수당"
                if col_name in col_indices:
                    custom_val = ws.cell(row=r_idx, column=col_indices[col_name] + 1).value
                    if custom_val is not None and str(custom_val).strip() != "":
                        val_float = float(custom_val)
                        db_manager.save_daily_custom_attendance(date_raw, worker_id, custom_type, val_float, conn=conn)
            # 감사 로그 남기기
            db_manager.log_audit(
                user_id=user_id,
                worker_id=worker_id,
                action="공수 선택적 일괄 업로드 반영",
                before_value="이전 상태",
                after_value=f"일반:{n_w}, 연장:{o_w}, 숙소:{l_w}, 보건:{h_w}, 팀장:{le_w}",
                conn=conn
            )
            success_count += 1
        conn.commit()
        conn.close()
        return {
            "success": True,
            "success_count": success_count,
            "error_rows": error_rows
        }
    except Exception as e:
        friendly_msg = get_friendly_error_message(str(e))
        return {"success": False, "error": friendly_msg}
    finally:
        if wb:
            try:
                wb.close()
            except Exception:
                pass
        if repaired_path and os.path.exists(repaired_path):
            safe_remove(repaired_path)