# run_tests.py
import sys
import os
import traceback

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Load test modules
import tests.test_db_manager as t1
import tests.test_calc_engine as t2
import tests.test_excel_io as t3

def run_test_module(name, module):
    print(f"\nRunning {name} tests...")
    
    # Find all functions starting with test_
    tests_funcs = [
        getattr(module, attr) 
        for attr in dir(module) 
        if attr.startswith("test_") and callable(getattr(module, attr))
    ]
    
    # Run setup
    if hasattr(module, "setup_module"):
        module.setup_module(None)
        
    passed = 0
    failed = 0
    for func in tests_funcs:
        try:
            func()
            print(f"  [PASS] {func.__name__}")
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {func.__name__}: {e}")
            traceback.print_exc()
            failed += 1
            
    # Run teardown
    if hasattr(module, "teardown_module"):
        module.teardown_module(None)
        
    return passed, failed

if __name__ == "__main__":
    p1, f1 = run_test_module("test_db_manager", t1)
    p2, f2 = run_test_module("test_calc_engine", t2)
    p3, f3 = run_test_module("test_excel_io", t3)

    total_passed = p1 + p2 + p3
    total_failed = f1 + f2 + f3
    print(f"\n=== Test Summary ===")
    print(f"Passed: {total_passed}, Failed: {total_failed}")
    if total_failed > 0:
        sys.exit(1)
    else:
        sys.exit(0)
