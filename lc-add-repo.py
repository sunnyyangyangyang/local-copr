#!/usr/bin/env python3
#
# lc-add-repo - Automatically add Local Copr repository to system
# Copyright (C) 2026 Yuanxi (Sunny) Yang
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

import os
import sys
import json
import shutil
import argparse
import subprocess

CONFIG_FILE = ".lc_config"
REPO_D = "/etc/yum.repos.d"

def check_root():
    """检查是否有 root 权限"""
    if os.geteuid() != 0:
        print("Error: This script must be run with sudo/root privileges")
        print(f"Usage: sudo {sys.argv[0]} <repo_path>")
        sys.exit(1)

def validate_repo(repo_path):
    """验证是否是有效的 lc 仓库"""
    if not os.path.isdir(repo_path):
        print(f"Error: {repo_path} is not a directory")
        return False
    
    # 检查是否存在 .lc_config（标识是 lc 管理的仓库）
    config_path = os.path.join(repo_path, CONFIG_FILE)
    if not os.path.exists(config_path):
        print(f"Warning: {repo_path} does not contain {CONFIG_FILE}")
        print("This may not be a lc-managed repository")
        response = input("Continue anyway? (yes/no): ")
        if response.lower() != "yes":
            return False
    
    # 检查是否存在 repodata
    repodata_path = os.path.join(repo_path, "repodata")
    if not os.path.exists(repodata_path):
        print(f"Error: {repo_path} does not contain repodata/")
        print("Please run 'createrepo_c' first or use 'lc init'")
        return False
    
    return True

def load_repo_config(repo_path):
    """读取仓库配置"""
    config_path = os.path.join(repo_path, CONFIG_FILE)
    config = {}
    
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                config = json.load(f)
        except Exception as e:
            print(f"Warning: Cannot read config file: {e}")
    
    return config

def import_gpg_key(repo_path):
    """导入 GPG 公钥"""
    gpg_key_path = os.path.join(repo_path, "RPM-GPG-KEY-local")
    
    if not os.path.exists(gpg_key_path):
        print(f"Error: GPG key file not found at {gpg_key_path}")
        return False
    
    print(f"Importing GPG key from {gpg_key_path}...")
    try:
        subprocess.run(["rpm", "--import", gpg_key_path], check=True)
        print("✓ GPG key imported successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error: Failed to import GPG key: {e}")
        return False

def generate_repo_file(repo_path, config, repo_name=None):
    """生成 .repo 文件内容"""
    repo_path = os.path.abspath(repo_path)
    
    if repo_name is None:
        repo_name = os.path.basename(repo_path)
    
    gpg_key_id = config.get("gpg_key_id")
    
    if gpg_key_id:
        gpg_block = f"""gpgcheck=1
repo_gpgcheck=1
gpgkey=file://{repo_path}/RPM-GPG-KEY-local"""
    else:
        gpg_block = "gpgcheck=0"
    
    repo_content = f"""[{repo_name}]
name=Local Copr - {repo_name}
baseurl=file://{repo_path}
enabled=1
{gpg_block}
"""
    return repo_content

def install_repo_file(repo_path, config, args):
    """安装 .repo 文件到系统"""
    repo_name = args.name if args.name else os.path.basename(repo_path)
    repo_filename = f"{repo_name}.repo"
    target_path = os.path.join(REPO_D, repo_filename)
    
    # 检查是否已存在
    if os.path.exists(target_path) and not args.force:
        print(f"Error: {target_path} already exists")
        print("Use --force to overwrite")
        return False
    
    # 生成配置内容
    repo_content = generate_repo_file(repo_path, config, repo_name)
    
    # 写入文件
    try:
        with open(target_path, "w") as f:
            f.write(repo_content)
        print(f"✓ Repository configuration installed to {target_path}")
        return True
    except Exception as e:
        print(f"Error: Failed to write repo file: {e}")
        return False

def refresh_cache():
    """刷新 DNF/YUM 缓存"""
    print("\nRefreshing package manager cache...")
    try:
        # 尝试使用 dnf，如果不存在则使用 yum
        pkg_mgr = "dnf" if shutil.which("dnf") else "yum"
        subprocess.run([pkg_mgr, "makecache"], check=True)
        print(f"✓ Cache refreshed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Warning: Failed to refresh cache: {e}")
        print("You may need to run 'sudo dnf makecache' manually")
        return False

def do_add(args):
    """执行添加仓库操作"""
    repo_path = os.path.abspath(args.repo)
    
    print(f"Adding repository: {repo_path}")
    print("-" * 60)
    
    # 1. 验证仓库
    if not validate_repo(repo_path):
        sys.exit(1)
    
    # 2. 读取配置
    config = load_repo_config(repo_path)
    gpg_key_id = config.get("gpg_key_id")
    
    if gpg_key_id:
        print(f"Repository uses GPG signing (Key ID: {gpg_key_id})")
    else:
        print("Repository does not use GPG signing")
    
    # 3. 导入 GPG 密钥（如果需要）
    if gpg_key_id:
        if not import_gpg_key(repo_path):
            if not args.force:
                print("Aborting due to GPG key import failure")
                sys.exit(1)
    
    # 4. 安装 .repo 文件
    if not install_repo_file(repo_path, config, args):
        sys.exit(1)
    
    # 5. 刷新缓存
    if not args.no_refresh:
        refresh_cache()
    
    print("-" * 60)
    print("✓ Repository added successfully!")
    print(f"\nYou can now install packages with:")
    print(f"  sudo dnf install <package-name>")

def do_remove(args):
    """执行移除仓库操作"""
    repo_name = args.name
    repo_filename = f"{repo_name}.repo"
    target_path = os.path.join(REPO_D, repo_filename)
    
    if not os.path.exists(target_path):
        print(f"Error: Repository '{repo_name}' not found in {REPO_D}")
        sys.exit(1)
    
    print(f"Removing repository configuration: {target_path}")
    
    try:
        os.remove(target_path)
        print(f"✓ Repository '{repo_name}' removed successfully")
        
        if not args.no_refresh:
            refresh_cache()
    except Exception as e:
        print(f"Error: Failed to remove repository: {e}")
        sys.exit(1)

def do_list(args):
    """列出所有 lc 管理的仓库"""
    print("Local Copr repositories in system:")
    print("-" * 60)
    
    found = False
    for filename in os.listdir(REPO_D):
        if not filename.endswith(".repo"):
            continue
        
        filepath = os.path.join(REPO_D, filename)
        try:
            with open(filepath, "r") as f:
                content = f.read()
                # 简单检测：包含 "Local Copr" 或 "baseurl=file://"
                if "Local Copr" in content or "baseurl=file://" in content:
                    print(f"  • {filename}")
                    found = True
        except:
            continue
    
    if not found:
        print("  (none found)")

def main():
    parser = argparse.ArgumentParser(
        description="Add/Remove Local Copr repositories to/from system",
        epilog="This script must be run with sudo/root privileges"
    )
    
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # Add command
    p_add = subparsers.add_parser("add", help="Add a repository to system")
    p_add.add_argument("repo", help="Path to the lc repository")
    p_add.add_argument("--name", help="Custom repository name (default: directory name)")
    p_add.add_argument("--force", action="store_true", help="Overwrite existing repo file")
    p_add.add_argument("--no-refresh", action="store_true", help="Skip cache refresh")
    p_add.set_defaults(func=do_add)
    
    # Remove command
    p_remove = subparsers.add_parser("remove", help="Remove a repository from system")
    p_remove.add_argument("name", help="Repository name (without .repo extension)")
    p_remove.add_argument("--no-refresh", action="store_true", help="Skip cache refresh")
    p_remove.set_defaults(func=do_remove)
    
    # List command
    p_list = subparsers.add_parser("list", help="List Local Copr repositories")
    p_list.set_defaults(func=do_list)
    
    args = parser.parse_args()
    
    # list 命令不需要 root
    if args.command != "list":
        check_root()
    
    args.func(args)

if __name__ == "__main__":
    main()