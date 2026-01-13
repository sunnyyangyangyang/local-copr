#!/usr/bin/env python3
#
# Local Copr Git (lc-git)
# A simple git trigger manager for Local Copr
# Copyright (C) 2026 Yuanxi (Sunny) Yang
# License: GPLv3+

import os
import sys
import json
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
    if not args.name and not args.remote:
        print("Error: You must provide a NAME or a --remote URL.")
        sys.exit(1)
        
    if not args.name and args.remote:
        # 从 URL 自动推断名字 (例如 user/repo.git -> repo)
        base = os.path.basename(args.remote)
        if base.endswith(".git"):
            base = base[:-4]
        args.name = base        
    name = args.name
    validate_name(name)
    
    # 目标路径: repo/forges/name (普通 Git 仓库)
    repo_path = os.path.join(rpm_repo, "forges", name)
    
    if os.path.exists(repo_path):
        print(f"Error: Repo {repo_path} already exists.")
        sys.exit(1)

    if args.remote:
        clone_cmd = ["git", "clone"]
        if args.branch:
            clone_cmd.extend(["--branch", args.branch])
            print(f"[{sys.argv[0]}] Cloning {args.remote} (branch: {args.branch}) into {repo_path}...")
        else:
            print(f"[{sys.argv[0]}] Cloning {args.remote} into {repo_path}...")
        clone_cmd.extend([args.remote, repo_path])
        subprocess.run(clone_cmd, check=True)
    else:
        print(f"[{sys.argv[0]}] Creating git repo at: {repo_path}")
        os.makedirs(repo_path)
        subprocess.run(["git", "init", "-q"], cwd=repo_path, check=True)
    
    # 2. 关键配置：允许 Push 更新工作区
    subprocess.run(["git", "config", "receive.denyCurrentBranch", "updateInstead"], cwd=repo_path, check=True)
    
    # 3. [新增] 创建空的 conf.json (如果不存在)
    forges_dir = os.path.join(rpm_repo, "forges")
    conf_path = os.path.join(forges_dir, "conf.json")
    
    if not os.path.exists(conf_path):
        print(f"[{sys.argv[0]}] Creating empty conf.json at: {conf_path}")
        with open(conf_path, "w") as f:
            json.dump({}, f, indent=2)
    
    # 4. 写入 Hook
    config_file = os.path.join(rpm_repo, ".lc_config")  

    # Hook 脚本逻辑：
    # 1. 清洗 Git 变量
    # 2. 切换到工作区 (cd .. 从 .git 出来)
    # 3. 检查 conf.json 是否存在，存在则传递给 lc build
    # 4. 后台执行 lc build

    script = f"""#!/bin/bash
# LC-GIT Smart Hook

# 获取当前脚本文件名 (post-receive, post-commit, or post-merge)
HOOK_NAME=$(basename "$0")

# 1. 确定输入源和新版本号
if [ "$HOOK_NAME" == "post-receive" ]; then
    # Push 模式：从 stdin 读取 (oldrev newrev refname)
    read oldrev newrev refname
else
    # 本地模式：手动获取 HEAD
    newrev=$(git rev-parse HEAD)
fi

unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE
cd "{repo_path}"

# 2. [关键安全修正] 只有 Push 模式才需要强制重置工作区
if [ "$HOOK_NAME" == "post-receive" ]; then
    git reset --hard "$newrev" >/dev/null
fi

# 3. 准备日志与构建
LOG_DIR="{rpm_repo}/.build_logs"
mkdir -p "$LOG_DIR"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
LOG_FILE="$LOG_DIR/{name}-$TIMESTAMP-${{newrev:0:7}}.log"
PLAN_FILE="$LOG_DIR/{name}-$TIMESTAMP-plan.json"

if [ "$HOOK_NAME" == "post-receive" ]; then
    echo "remote: [LC] 📥 Push received ($newrev). Log: $LOG_FILE"
else
    echo "[LC] 🔨 Local change detected ($newrev). Log: $LOG_FILE"
fi

# 4. [新增] 检查 conf.json 是否存在
CONF_FILE="{forges_dir}/conf.json"
CONF_ARG=""
if [ -f "$CONF_FILE" ]; then
    CONF_ARG="--conf $CONF_FILE"
fi

# 5. 后台触发构建任务
IS_REBUILD=$(python3 -c "import json, os; print('yes' if os.path.exists('{config_file}') and json.load(open('{config_file}')).get('auto_rebuild') else 'no')")

(
    if [ "$IS_REBUILD" == "yes" ]; then
        echo "=== 🔄 Auto-Rebuild Enabled ==="
        echo "1. Planning..."
        # [修改] lc-rebuild 也使用 conf
        lc-rebuild --repo "{rpm_repo}" --trigger "{name}" --output "$PLAN_FILE" $CONF_ARG
        
        if [ $? -eq 0 ]; then
            echo "2. Executing Chain..."
            lc build --torepo "{rpm_repo}" --chain "$PLAN_FILE" $CONF_ARG
        else
            echo "❌ Planning failed. Fallback to single build."
            lc build --source . --torepo "{rpm_repo}" $CONF_ARG
        fi
    else
        echo "=== 🔨 Single Build Mode ==="
        lc build --source . --torepo "{rpm_repo}" $CONF_ARG
    fi
) > "$LOG_FILE" 2>&1 &

if [ "$HOOK_NAME" == "post-receive" ]; then
    echo "remote: [LC] Task submitted (PID: $!)."
else
    echo "[LC] Task submitted (PID: $!). Check logs in .build_logs/"
fi
"""

    # 写入 Hook 到三个位置 (支持本地 commit/merge 和远程 push)
    hooks_dir = os.path.join(repo_path, ".git", "hooks")
    target_hooks = ["post-receive", "post-merge", "post-commit"]
    
    for hook_name in target_hooks:
        hook_path = os.path.join(hooks_dir, hook_name)
        with open(hook_path, "w") as f:
            f.write(script)
        os.chmod(hook_path, 0o755)
    
    print(f"[{sys.argv[0]}] Success.")
    print(f"Hooks installed: {', '.join(target_hooks)}")
    print(f"Config file: {conf_path} (edit this to set package-specific build options)")
    if not args.remote:
        print(f"Usage: git remote add local {repo_path}")

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
            print(f"  {pkg}")
    
    # 显示 conf.json 状态
    conf_path = os.path.join(forges_dir, "conf.json")
    if os.path.exists(conf_path):
        print("-" * 40)
        print(f"Config: {conf_path}")
            
    print("-" * 40)
    print(f"Total: {len(packages)}")

def main():
    parser = argparse.ArgumentParser(description="Local Copr Git Manager")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # Create command
    p_c = subparsers.add_parser("create", help="Create a new package git repo")
    p_c.add_argument("name", nargs="?", help="Package name (optional if --remote is used)")
    p_c.add_argument("--remote", help="Clone from an existing remote git URL")
    p_c.add_argument("--branch", help="Specific branch to clone (default: repository default)")
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