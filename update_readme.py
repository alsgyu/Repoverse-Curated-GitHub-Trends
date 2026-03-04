#!/usr/bin/env python3
"""래퍼: 레포 루트에서 python3 update_readme.py 로 실행 가능하도록 합니다."""
import os
import subprocess
import sys

repo_root = os.path.dirname(os.path.abspath(__file__))
script_path = os.path.join(repo_root, "GitTrendHub", "update_readme.py")
if not os.path.isfile(script_path):
    print(f"오류: 스크립트를 찾을 수 없습니다. {script_path}")
    sys.exit(1)
result = subprocess.run([sys.executable, script_path], cwd=repo_root)
sys.exit(result.returncode)
