# run_app.py
"""
PyInstaller 실행 파일 빌드용 진입 부트스트랩 스크립트
"""
import os
import sys
import shutil
import streamlit.web.cli as stcli

# Protobuf C++ DLL 로드 실패 우회
os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"

if __name__ == "__main__":
    # PyInstaller가 패키징을 임시 압축 해제하는 _MEIPASS 경로 혹은 스크립트 경로 획득
    base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    
    # 실행 파일(.exe)이 존재하는 실제 폴더 경로 획득
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
    else:
        exe_dir = os.path.dirname(os.path.abspath(__file__))
        
    # 실행 파일 옆에 있는 .streamlit 폴더(비밀번호 등 secrets.toml 포함)를
    # 실행 시 임시 해제 경로(_MEIPASS) 아래로 자동 동적 복사하여 Streamlit이 인식하게 합니다.
    # 이렇게 하면 유저가 exe 재컴파일 없이 외부 secrets.toml 수정으로 비밀번호 변경이 가능해집니다.
    src_streamlit = os.path.join(exe_dir, ".streamlit")
    dest_streamlit = os.path.join(base_path, ".streamlit")
    
    if os.path.exists(src_streamlit):
        try:
            # 기존 임시 경로 내 .streamlit이 존재하면 안전하게 교체
            if os.path.exists(dest_streamlit):
                shutil.rmtree(dest_streamlit)
            shutil.copytree(src_streamlit, dest_streamlit)
        except Exception as e:
            # 권한/파일 잠김 등으로 복사 실패 시 예외 처리
            print(f"[경고] 비밀번호 설정 복사 실패: {e}")
            
    # 작업 디렉토리를 해제 경로로 변경
    os.chdir(base_path)
    
    # 모듈 임포트 경로 추가
    if base_path not in sys.path:
        sys.path.insert(0, base_path)
        
    # Streamlit 메인 스크립트 경로 지정
    app_path = os.path.join(base_path, "app.py")
    
    # Streamlit CLI 인자 모사 실행
    sys.argv = [
        "streamlit",
        "run",
        app_path,
        "--global.developmentMode=false",
        "--server.fileWatcherType=none"
    ]
    
    sys.exit(stcli.main())
