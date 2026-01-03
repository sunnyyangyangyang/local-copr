#!/usr/bin/env python3
#
# Local Copr (lc) - A lightweight local RPM build system
# Copyright (C) 2026 Yuanxi (Sunny) Yang
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
import os
import sys
import argparse
import subprocess
import glob
import shutil
import tempfile
import tarfile
import json
from datetime import datetime

# --- 配置常量 ---
MOCK_CONFIG = os.getenv("LC_MOCK_CONFIG", "fedora-43-x86_64") 
tool_name = "lc (Local-Copr)"
CONFIG_FILE = ".lc_config" # 存储仓库配置（如GPG Key ID）

def run_cmd(cmd, cwd=None, env=None, capture_output=False):
    """封装 subprocess"""
    if not capture_output:
        print(f"[{tool_name}] CMD: {' '.join(cmd)}")
    try:
        if capture_output:
            return subprocess.check_output(cmd, cwd=cwd, env=env, text=True).strip()
        subprocess.run(cmd, cwd=cwd, env=env, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error executing command: {e}")
        sys.exit(1)

def do_init(args):
    """初始化仓库"""
    repo_path = os.path.abspath(args.repo)
    gpg_key = args.gpg_key
    
    print(f"[{tool_name}] Initializing repo at: {repo_path}")
    
    if not os.path.exists(repo_path):
        os.makedirs(repo_path)
    
    # 1. 记录配置 (GPG ID)
    config = {}
    if gpg_key:
        print(f"[{tool_name}] GPG Signing Enabled. Key ID: {gpg_key}")
        config["gpg_key_id"] = gpg_key
        
        # 2. 导出公钥到仓库根目录
        pub_key_path = os.path.join(repo_path, "RPM-GPG-KEY-local")
        print(f"-> Exporting public key to {pub_key_path}...")
        with open(pub_key_path, "w") as f:
            subprocess.run(["gpg", "--export", "--armor", gpg_key], stdout=f, check=True)
    
    # 保存 .lc_config
    with open(os.path.join(repo_path, CONFIG_FILE), "w") as f:
        json.dump(config, f)

    # 3. 初始化 Repodata
    run_cmd(["createrepo_c", repo_path])
    if gpg_key:
        sign_repodata(repo_path, gpg_key)
    # 4. 生成 .repo 模板
    repo_name = os.path.basename(repo_path)
    if gpg_key:
        # 开启 GPG 检查
        gpg_block = f"""gpgcheck=1
repo_gpgcheck=1
gpgkey=file://{repo_path}/RPM-GPG-KEY-local"""
    else:
        # 关闭 GPG 检查
        gpg_block = "gpgcheck=0"

    readme_content = f"""[{repo_name}]
name=Local Copr - {repo_name}
baseurl=file://{repo_path}
enabled=1
{gpg_block}
"""
    readme_path = os.path.join(repo_path, "local.repo")
    with open(readme_path, "w") as f:
        f.write(readme_content)
        
    print(f"[{tool_name}] Success. Repo config template saved to {readme_path}")

def do_delete(args):
    """删除仓库"""
    repo_path = os.path.abspath(args.repo)
    # 安全检查 (略，保持原有逻辑)
    forbidden_paths = ["/", "/home", "/usr", "/var", "/etc", os.path.expanduser("~")]
    if repo_path in forbidden_paths:
        sys.exit(1)
    if not os.path.exists(repo_path):
        print(f"Error: Repo {repo_path} does not exist.")
        sys.exit(1)
        
    print(f"!!! WARNING !!! Delete {repo_path}?")
    if input("Type 'yes': ").lower() == "yes":
        shutil.rmtree(repo_path)
        print("Deleted.")

def sign_rpms(repo_path, rpm_files, key_id):
    """对 RPM 文件进行签名"""
    if not rpm_files:
        return
    print(f"--- Signing {len(rpm_files)} RPMs with Key {key_id} ---")
    # 使用 rpm --addsign
    # 注意：这需要 gpg-agent 处于活动状态，否则会弹出密码输入框或报错
    cmd = ["rpm", "--addsign", "--define", f"_gpg_name {key_id}"] + rpm_files
    run_cmd(cmd)

def sign_repodata(repo_path, key_id):
    """对 repomd.xml 进行签名"""
    repodata_xml = os.path.join(repo_path, "repodata", "repomd.xml")
    if os.path.exists(repodata_xml):
        print(f"--- Signing repodata with Key {key_id} ---")
        # 生成 repomd.xml.asc
        # --yes 覆盖旧签名
        cmd = ["gpg", "--detach-sign", "--armor", "--yes", "--default-key", key_id, repodata_xml]
        run_cmd(cmd)

def do_build(args):
    """执行构建流程"""
    source_dir_origin = os.path.abspath(args.source)
    repo_dir = os.path.abspath(args.torepo)
    
    # 读取仓库配置，检查是否启用 GPG
    gpg_key_id = None
    config_path = os.path.join(repo_dir, CONFIG_FILE)
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                cfg = json.load(f)
                gpg_key_id = cfg.get("gpg_key_id")
        except:
            pass

    # Mock 基础参数
    mock_base_args = ["mock", "-r", MOCK_CONFIG, "--define", "_changelog_date_check 0"]
    if not args.use_ssd:
        mock_base_args.append("--enable-plugin=tmpfs")
    if args.jobs:
        print(f"[{tool_name}] Limiting concurrency to: -j{args.jobs}")
        # 覆盖 _smp_mflags 宏，强制 rpmbuild 使用指定核心数
        mock_base_args.extend(["--define", f"_smp_mflags -j{args.jobs}"])

    # 路径检查 (略)
    if not os.path.isdir(source_dir_origin): sys.exit(1)
    if not os.path.isdir(repo_dir): sys.exit(1)

    # 确定 Spec
    spec_file_arg = args.spec
    if spec_file_arg:
        spec_path_origin = os.path.abspath(spec_file_arg)
    else:
        specs = glob.glob(os.path.join(source_dir_origin, "*.spec"))
        if not specs: sys.exit(1)
        spec_path_origin = specs[0]

    # 工作区
    with tempfile.TemporaryDirectory(prefix="lc-build-") as work_dir:
        # Step 0: Copy Source to RAM
        temp_src_dir = os.path.join(work_dir, "clean_sources")
        shutil.copytree(source_dir_origin, temp_src_dir, dirs_exist_ok=True, 
                        ignore=shutil.ignore_patterns('.git', '.svn'))
        rel_spec_path = os.path.relpath(spec_path_origin, source_dir_origin)
        temp_spec_path = os.path.join(temp_src_dir, rel_spec_path)

        # Step A: Spectool
        run_cmd(["spectool", "-g", "-C", temp_src_dir, temp_spec_path], cwd=temp_src_dir)

        # Step B: SRPM
        srpm_result_dir = os.path.join(work_dir, "srpm_result")
        os.makedirs(srpm_result_dir)
        cmd_srpm = mock_base_args + ["--buildsrpm", "--spec", temp_spec_path, "--sources", temp_src_dir, "--resultdir", srpm_result_dir]
        run_cmd(cmd_srpm)
        src_rpms = glob.glob(os.path.join(srpm_result_dir, "*.src.rpm"))
        target_srpm = src_rpms[0]

        # Step C: RPM
        rpm_result_dir = os.path.join(work_dir, "rpm_result")
        os.makedirs(rpm_result_dir)
        cmd_rpm = mock_base_args + ["--rebuild", target_srpm, "--resultdir", rpm_result_dir]
        if args.addrepo:
            for repo in args.addrepo:
                repo_url = f"file://{os.path.abspath(repo)}" if os.path.exists(repo) else repo
                cmd_rpm.append(f"--addrepo={repo_url}")
        run_cmd(cmd_rpm)

        # Step D: Move & Collect
        new_rpms = [] # 记录新生成的 RPM 路径
        built_rpms = glob.glob(os.path.join(rpm_result_dir, "*.rpm"))
        for rpm in built_rpms:
            if "debuginfo" in rpm or rpm.endswith(".src.rpm"): continue
            dest = shutil.copy2(rpm, repo_dir)
            new_rpms.append(dest) # 记录目标路径
            print(f"-> Saved RPM: {os.path.basename(rpm)}")

        # --- 特性 3: GPG 签名 (RPM Level) ---
        if gpg_key_id:
            sign_rpms(repo_dir, new_rpms, gpg_key_id)

        # Step D+: Archive Logs (略，保持逻辑)
        logs_dir = os.path.join(repo_dir, ".build_logs")
        if not os.path.exists(logs_dir): os.makedirs(logs_dir)
        archive_path = os.path.join(logs_dir, f"{os.path.basename(temp_spec_path).replace('.spec','')}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.tar.gz")
        with tarfile.open(archive_path, "w:gz") as tar:
            tar.add(rpm_result_dir, arcname="build-log")

    # Step E: Update Index
    run_cmd(["createrepo_c", "--update", repo_dir])
    
    # --- 特性 4: GPG 签名 (Repo Level) ---
    if gpg_key_id:
        sign_repodata(repo_dir, gpg_key_id)
        
    print(f"[{tool_name}] Done!")

def main():
    parser = argparse.ArgumentParser(description="Local Copr (lc) - Secure Build Tool")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Init
    p_init = subparsers.add_parser("init", help="Init new repo")
    p_init.add_argument("--repo", required=True)
    p_init.add_argument("--gpg-key", help="GPG Key ID to enable signing (e.g. 3AA5C0AD)")
    p_init.set_defaults(func=do_init)

    # Delete
    p_del = subparsers.add_parser("remove", help="Delete a repo")
    p_del.add_argument("--repo", required=True)
    p_del.set_defaults(func=do_delete)

    # Build
    p_build = subparsers.add_parser("build", help="Build RPM")
    p_build.add_argument("--source", required=True)
    p_build.add_argument("--torepo", required=True)
    p_build.add_argument("--spec", help="Specific spec")
    p_build.add_argument("--addrepo", action="append")
    p_build.add_argument("--use-ssd", action="store_true")
    p_build.add_argument("--jobs", type=int, help="Limit build cores (e.g. 8 to prevent OOM)")
    p_build.set_defaults(func=do_build)

    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()