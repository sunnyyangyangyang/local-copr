#!/usr/bin/env python3
import os
import sys
import argparse
import subprocess
import glob
import shutil
import tempfile

# --- 配置常量 ---
MOCK_CONFIG = "fedora-43-x86_64"  # 默认 Mock 环境，可改为 centos-stream-9-x86_64
tool_name = "lc (Local-Copr)"

def run_cmd(cmd, cwd=None, env=None):
    """封装 subprocess，统一处理打印和错误"""
    print(f"[{tool_name}] CMD: {' '.join(cmd)}")
    try:
        subprocess.run(cmd, cwd=cwd, env=env, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error executing command: {e}")
        sys.exit(1)

def do_init(args):
    """初始化仓库"""
    repo_path = os.path.abspath(args.repo)
    print(f"[{tool_name}] Initializing repo at: {repo_path}")
    
    if not os.path.exists(repo_path):
        os.makedirs(repo_path)
    
    # 初始化 repodata
    run_cmd(["createrepo_c", repo_path])
    
    # 生成一个方便用户使用的 .repo 模板
    repo_name = os.path.basename(repo_path)
    readme_content = f"""[{repo_name}]
name=Local Copr - {repo_name}
baseurl=file://{repo_path}
enabled=1
gpgcheck=0
"""
    readme_path = os.path.join(repo_path, "local.repo")
    with open(readme_path, "w") as f:
        f.write(readme_content)
        
    print(f"[{tool_name}] Success. Repo config template saved to {readme_path}")

def do_build(args):
    """执行构建流程"""
    source_dir = os.path.abspath(args.source)
    repo_dir = os.path.abspath(args.torepo)
    
    # 1. 检查基础环境
    if not os.path.isdir(source_dir):
        print(f"Error: Source directory {source_dir} does not exist.")
        sys.exit(1)
    if not os.path.isdir(repo_dir):
        print(f"Error: Repo directory {repo_dir} does not exist. Run 'lc init' first.")
        sys.exit(1)

    # 2. 确定 Spec 文件
    spec_file = args.spec
    if spec_file:
        spec_path = os.path.abspath(spec_file)
    else:
        # 自动探测
        specs = glob.glob(os.path.join(source_dir, "*.spec"))
        if not specs:
            print("Error: No .spec file found in source dir.")
            sys.exit(1)
        spec_path = specs[0]
        print(f"[{tool_name}] Auto-detected spec: {spec_path}")

    # 3. 准备临时构建目录 (Workspace)
    with tempfile.TemporaryDirectory(prefix="lc-build-") as work_dir:
        print(f"[{tool_name}] Workspace: {work_dir}")
        
        # --- Step A: 下载 Source (Spectool) ---
        print(f"--- Step A: Downloading sources ---")
        # spectool 需要在源码目录运行，把远程文件下下来
        run_cmd(["spectool", "-g", "-C", source_dir, spec_path], cwd=source_dir)

        # --- Step B: 构建 SRPM ---
        print(f"--- Step B: Building SRPM ---")
        srpm_result_dir = os.path.join(work_dir, "srpm_result")
        os.makedirs(srpm_result_dir)
        
        mock_srpm_cmd = [
            "mock", "-r", MOCK_CONFIG,
            "--buildsrpm",
            "--spec", spec_path,
            "--sources", source_dir,
            "--resultdir", srpm_result_dir
        ]
        run_cmd(mock_srpm_cmd)
        
        # 找到产出的 src.rpm
        src_rpms = glob.glob(os.path.join(srpm_result_dir, "*.src.rpm"))
        if not src_rpms:
            print("Error: Failed to generate SRPM.")
            sys.exit(1)
        target_srpm = src_rpms[0]
        print(f"[{tool_name}] SRPM created: {target_srpm}")

        # --- Step C: 构建 Binary RPM ---
        print(f"--- Step C: Building Binary RPM ---")
        rpm_result_dir = os.path.join(work_dir, "rpm_result")
        os.makedirs(rpm_result_dir)
        
        mock_build_cmd = [
            "mock", "-r", MOCK_CONFIG,
            "--rebuild", target_srpm,
            "--resultdir", rpm_result_dir
        ]
        
        # 处理 --addrepo
        if args.addrepo:
            for repo in args.addrepo:
                # 如果是本地路径，补全 file://
                if os.path.exists(repo):
                    repo_url = f"file://{os.path.abspath(repo)}"
                else:
                    repo_url = repo
                mock_build_cmd.append(f"--addrepo={repo_url}")
                print(f"[{tool_name}] Injecting repo: {repo_url}")

        run_cmd(mock_build_cmd)

        # --- Step D: 搬运产物 ---
        print(f"--- Step D: Collecting artifacts ---")
        built_rpms = glob.glob(os.path.join(rpm_result_dir, "*.rpm"))
        count = 0
        for rpm in built_rpms:
            # 默认不搬运 debuginfo 和 src.rpm，视需求而定
            if "debuginfo" in rpm or rpm.endswith(".src.rpm"):
                continue
            shutil.copy2(rpm, repo_dir)
            print(f"-> Copied: {os.path.basename(rpm)}")
            count += 1
        
        if count == 0:
            print("Warning: No binary RPMs were copied (check build logs).")

    # --- Step E: 更新索引 ---
    print(f"--- Step E: Updating Repo Index ---")
    run_cmd(["createrepo_c", "--update", repo_dir])
    print(f"[{tool_name}] Build Complete! Check: {repo_dir}")

def main():
    parser = argparse.ArgumentParser(description="Local Copr (lc) - MVP Tool")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Command: init
    parser_init = subparsers.add_parser("init", help="Initialize a new local repo")
    parser_init.add_argument("--repo", required=True, help="Path to the repo directory")
    parser_init.set_defaults(func=do_init)

    # Command: build
    parser_build = subparsers.add_parser("build", help="Build RPM from source")
    parser_build.add_argument("--source", required=True, help="Directory containing source code and spec")
    parser_build.add_argument("--torepo", required=True, help="Target repo directory")
    parser_build.add_argument("--spec", help="Specific spec file (optional, auto-detected if None)")
    parser_build.add_argument("--addrepo", action="append", help="Add extra repo (URL or local path)")
    parser_build.set_defaults(func=do_build)

    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()