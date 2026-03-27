#!/usr/bin/env python3
"""
将 dashboard.html 推送到 GitHub (amnesiacer/main)。
使用 SSH 方式推送，无需 token。
"""
import subprocess
import shutil
import datetime
import datetime
import os

# SSH clone of amnesiacer/main
REPO_DIR = '/tmp/main_repo'
DASHBOARD_SRC = os.path.join(os.path.dirname(__file__), '..', 'dashboard.html')

def run(cmd, cwd=None):
    print(f"$ {cmd}")
    r = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
    if r.stdout: print(r.stdout)
    if r.stderr: print(r.stderr)
    return r.returncode

def main():
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    shutil.copy2(DASHBOARD_SRC, os.path.join(REPO_DIR, 'dashboard.html'))
    shutil.copy2(DASHBOARD_SRC, os.path.join(REPO_DIR, 'index.html'))

    run(f'git add dashboard.html index.html', cwd=REPO_DIR)
    r = run(f'git diff --cached --quiet', cwd=REPO_DIR)
    if r == 0:
        print("没有变更需要推送。")
        return

    run(f'git commit -m "自动更新看板 {now}"', cwd=REPO_DIR)
    run('git push origin main', cwd=REPO_DIR)
    print("✅ 已推送到 GitHub!")

if __name__ == '__main__':
    main()
