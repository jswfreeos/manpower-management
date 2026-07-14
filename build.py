# build.py
"""
PyInstaller를 사용하여 공수관리시스템을 단일 실행 파일(.exe)로 빌드하는 스크립트
"""
import subprocess
import os
import sys

def build():
    # 현재 스크립트가 있는 디렉토리로 변경
    project_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(project_dir)
    
    # 아나콘다가 제거되었으므로, 현재 활성화된 python을 통해 PyInstaller를 실행하도록 설정합니다.
    cmd = [
        "python", "-m", "PyInstaller",
        "--onefile",
        "--name=노무관리시스템",
        "--clean",
        "--collect-all", "streamlit",
        "--copy-metadata", "streamlit",
        "--collect-all", "pyarrow",  # pyarrow DLL 파일 일괄 패키징
        
        # 빌드 속도 개선 및 EXE 용량 최적화를 위해 사용하지 않는 대용량 라이브러리 제외
        "--exclude-module", "scipy",
        "--exclude-module", "matplotlib",
        "--exclude-module", "sphinx",
        "--exclude-module", "PyQt5",
        "--exclude-module", "h5py",
        "--exclude-module", "PIL",
        "--exclude-module", "IPython",
        "--exclude-module", "notebook",
        "--exclude-module", "ipykernel",
        "--exclude-module", "jedi",
        "--exclude-module", "sympy",
        "--exclude-module", "bokeh",
        "--exclude-module", "plotly",
        "--exclude-module", "sklearn",
        "--exclude-module", "scikit-learn",
        
        "--add-data", "app.py;.",
        "--add-data", "config.py;.",
        "--add-data", "db_manager.py;.",
        "--add-data", "calc_engine.py;.",
        "--add-data", "validator.py;.",
        "--add-data", "excel_io.py;.",
        # .streamlit 설정은 정적 압축 해제 에러 방지 및 유저 비밀번호 자유로운 수정을 위해 
        # 빌드 압축 대상에서 제외하고 런타임에 외부 복사하는 방식으로 고도화합니다.
        "run_app.py"
    ]
    
    print("==================================================")
    print("      노무관리시스템 EXE 패키징 빌드를 시작합니다 (순수 파이썬 모드)")
    print("==================================================")
    print(f"실행 명령어: {' '.join(cmd)}\n")
    
    try:
        subprocess.run(cmd, check=True)
        print("\n==================================================")
        print("빌드가 성공적으로 완료되었습니다!")
        print("결과물 위치: C:\\Users\\user\\OneDrive - DAESUN E&C CO.,LTD\\문서\\공수관리시스템\\dist\\노무관리시스템.exe")
        print("==================================================")
    except subprocess.CalledProcessError as e:
        print(f"\n빌드 중 에러가 발생했습니다: {e}")
        sys.exit(1)

if __name__ == "__main__":
    build()
