#!/usr/bin/env python3
#
# Local Copr Git (lc-git)
# A simple git trigger manager for Local Copr
# Copyright (C) 2026 Yuanxi (Sunny) Yang
# License: GPLv3+

import os
import sys
import shutil
import argparse
import subprocess

def validate_name(name):
    """防止路径穿越，只允许简单目录名"""
    if "/" in name or "\\" in name or name in [".", ".."]:
        print(f"Error: Invalid package name '{name}'. Slashes are not allowed.")
        sys.exit(1)

def do_create(args):
    rpm_repo = os.path.abspath(args.repo)
    if not os.path.exists(rpm_repo):
        print(f"Error: RPM Repo {rpm_repo} does not exist. Run 'lc init' first.")
        sys.exit(1)    
    name = args.name
    validate_name(name)
    
    # 目标路径: repo/forges/name (普通 Git 仓库)
    repo_path = os.path.join(rpm_repo, "forges", name)
    
    if os.path.exists(repo_path):
        print(f"Error: Repo {repo_path} already exists.")
        sys.exit(1)
        
    print(f"[{sys.argv[0]}] Creating git repo at: {repo_path}")
    os.makedirs(repo_path)
    
    # 1. 初始化普通仓库
    subprocess.run(["git", "init", "-q"], cwd=repo_path, check=True)
    
    # 2. 关键配置：允许 Push 更新工作区
    # 如果没有这行，Push 到当前分支会被 Git 拒绝
    subprocess.run(["git", "config", "receive.denyCurrentBranch", "updateInstead"], cwd=repo_path, check=True)
    
    # 3. 写入 Hook
    hook_path = os.path.join(repo_path, ".git", "hooks", "post-receive")
    config_file = os.path.join(rpm_repo, ".lc_config")  

    # Hook 脚本逻辑：
    # 1. 清洗 Git 变量
    # 2. 切换到工作区 (cd .. 从 .git 出来)
    # 3. 后台执行 lc build

    script = f"""#!/bin/bash
# LC-GIT Smart Hook

while read oldrev newrev refname; do
    unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE
    cd "{repo_path}"
    
    # 同步代码
    git reset --hard "$newrev" >/dev/null

    # 准备日志
    LOG_DIR="{rpm_repo}/.build_logs"
    mkdir -p "$LOG_DIR"
    TIMESTAMP=$(date +%Y%m%d-%H%M%S)
    LOG_FILE="$LOG_DIR/{name}-$TIMESTAMP-${{newrev:0:7}}.log"
    PLAN_FILE="$LOG_DIR/{name}-$TIMESTAMP-plan.json"

    echo "remote: [LC] 📥 Push received. Log: $LOG_FILE"

    # --- 核心判定逻辑 ---
    # 使用 Python 解析配置 (比 grep/sed 可靠)
    IS_REBUILD=$(python3 -c "import json, os; print('yes' if os.path.exists('{config_file}') and json.load(open('{config_file}')).get('auto_rebuild') else 'no')")

    (
        if [ "$IS_REBUILD" == "yes" ]; then
            echo "=== 🔄 Auto-Rebuild Enabled ==="
            echo "1. Planning..."
            # 调用 Planner
            lc-rebuild --repo "{rpm_repo}" --trigger "{name}" --output "$PLAN_FILE"
            
            if [ $? -eq 0 ]; then
                echo "2. Executing Chain..."
                # 调用 Builder (Chain 模式)
                lc build --torepo "{rpm_repo}" --chain "$PLAN_FILE"
            else
                echo "❌ Planning failed. Fallback to single build."
                lc build --source . --torepo "{rpm_repo}"
            fi
        else
            echo "=== 🔨 Single Build Mode ==="
            # 调用 Builder (单包模式)
            lc build --source . --torepo "{rpm_repo}"
        fi
    ) > "$LOG_FILE" 2>&1 &

    echo "remote: [LC] Task submitted (PID: $!)."
    break
done
"""

    with open(hook_path, "w") as f:
        f.write(script)
    
    # 赋予执行权限
    os.chmod(hook_path, 0o755)
    
    print(f"[{sys.argv[0]}] Success.")
    print(f"Usage: git remote add local {repo_path}")
    print(f"       git push local main")

def do_delete(args):
    rpm_repo = os.path.abspath(args.repo)
    name = args.name
    validate_name(name)
    
    repo_path = os.path.join(rpm_repo, "forges", name)
    
    if not os.path.exists(repo_path):
        print(f"Error: Repo {repo_path} does not exist.")
        sys.exit(1)
        
    print(f"!!! WARNING !!! Delete git repo {repo_path}?")
    if input("Type 'yes': ").lower() == "yes":
        shutil.rmtree(repo_path)
        print("Deleted.")

def do_list(args):
    rpm_repo = os.path.abspath(args.repo)
    forges_dir = os.path.join(rpm_repo, "forges")
    
    print(f"Packages in {rpm_repo}:")
    print("-" * 40)
    
    if not os.path.exists(forges_dir):
        print("(none)")
        return

    # 获取所有子目录并排序
    packages = []
    try:
        items = os.listdir(forges_dir)
        for item in items:
            full_path = os.path.join(forges_dir, item)
            if os.path.isdir(full_path):
                packages.append(item)
    except OSError as e:
        print(f"Error reading directory: {e}")
        sys.exit(1)
        
    packages.sort()
    
    if not packages:
        print("(none)")
    else:
        for pkg in packages:
            # 简单美化：如果是 git 仓库则显示，否则标记为目录
            # 这里简单起见，只要在 forges 下的目录都认为是包
            print(f"  {pkg}")
            
    print("-" * 40)
    print(f"Total: {len(packages)}")

def main():
    parser = argparse.ArgumentParser(description="Local Copr Git Manager")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # Create command
    p_c = subparsers.add_parser("create", help="Create a new package git repo")
    p_c.add_argument("name", help="Package name")
    p_c.add_argument("--repo", required=True, help="Path to Local Copr root")
    p_c.set_defaults(func=do_create)
    
    # Delete command
    p_d = subparsers.add_parser("delete", help="Delete a package git repo")
    p_d.add_argument("name", help="Package name")
    p_d.add_argument("--repo", required=True, help="Path to Local Copr root")
    p_d.set_defaults(func=do_delete)
    
    # List command
    p_l = subparsers.add_parser("list", help="List all package git repos")
    p_l.add_argument("--repo", required=True, help="Path to Local Copr root")
    p_l.set_defaults(func=do_list)
    
    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()