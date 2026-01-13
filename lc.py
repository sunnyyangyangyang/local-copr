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
import re
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
tool_name = "lc (Local-Copr)"
CONFIG_FILE = ".lc_config" # 存储仓库配置（如GPG Key ID）

def parse_size_bytes(size_str):
    """
    解析类似 '16G', '512M', '1024' 的字符串为字节整数。
    如果解析失败或输入是百分比，返回 None。
    """
    if not size_str:
        return None
    
    units = {
        'K': 1024,
        'M': 1024**2,
        'G': 1024**3,
        'T': 1024**4
    }
    
    s = size_str.upper().strip()
    
    # 暂不处理百分比（因为不知道 Host 总内存），如果是百分比则忽略 Swap 自动计算
    if '%' in s:
        return None

    try:
        # 纯数字，默认单位 bytes
        if s.isdigit():
            return int(s)
            
        # 带单位
        for unit, multiplier in units.items():
            if s.endswith(unit):
                number = float(s[:-1])
                return int(number * multiplier)
    except:
        return None
    
    return None

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

    # [新增] 保存 Rebuild 设置    
    if args.enable_rebuild:
        print(f"[{tool_name}] 🔄 Auto-Rebuild (Chain) Enabled.")
        config["auto_rebuild"] = True
    else:
        config["auto_rebuild"] = False
        
    with open(os.path.join(repo_path, CONFIG_FILE), "w") as f:
        json.dump(config, f)

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

def _bump_spec_release(spec_path):
    """
    修改 Spec 文件，追加基于时间戳的 Patch 号，确保版本单调递增。
    例如: Release: 1%{?dist} -> Release: 1.p1700000000%{?dist}
    """
    import time
    import re
    
    try:
        with open(spec_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        new_lines = []
        # 生成一个简短的时间戳 patch 号 (例如 .p1704895000)
        patch_suffix = f".p{int(time.time())}"
        changed = False

        # 匹配 Release 行，忽略大小写
        release_pattern = re.compile(r'^(Release:\s*)(.+?)(%\{\?dist\})?$', re.IGNORECASE)

        for line in lines:
            match = release_pattern.match(line.strip())
            if match and not changed:
                # group(1): "Release: "
                # group(2): "1" 或 "1.p12345"
                # group(3): "%{?dist}" 或 None
                prefix = match.group(1)
                old_ver = match.group(2).strip()
                dist_macro = match.group(3) if match.group(3) else ""
                
                # 如果以前已经bump过 (包含 .p1...), 我们去掉旧后缀再加新的
                # 这样保证 git 里无论怎么改，构建出来的总是最新的
                base_ver = re.sub(r'\.p\d+$', '', old_ver)
                
                new_line = f"{prefix}{base_ver}{patch_suffix}{dist_macro}\n"
                new_lines.append(new_line)
                print(f"[{tool_name}] 🆙 Version Bump: {old_ver} -> {base_ver}{patch_suffix}")
                changed = True
            else:
                new_lines.append(line)
        
        with open(spec_path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
            
    except Exception as e:
        print(f"[{tool_name}] Warning: Failed to bump spec release: {e}")

def chain(args) :
    
    repo_dir = os.path.abspath(args.torepo)
    print(f"[{tool_name}] ⛓️  Chain Mode Triggered: {args.chain}")
    try:
        with open(args.chain) as f:
            tasks = json.load(f).get('tasks', [])
    except Exception as e:
        print(f"Error loading plan: {e}")
        return False

    total = len(tasks)
    print(f"[{tool_name}] Total tasks in chain: {total}")

    for idx, task in enumerate(tasks):
        pkg_name = task['package']
        print(f"\n[{tool_name}] ⏩ Chain Task ({idx+1}/{total}): {pkg_name}")
        args.source = os.path.join(repo_dir, "forges", pkg_name)
        
        # 递归调用 (复用所有逻辑)
        if not single_build(args):
            print(f"[{tool_name}] ❌ Chain broken at {pkg_name}. Stopping.")
            return False # 中断链条
        
        # 注意：do_build 结尾自带 createrepo，所以这里不用写
        # 下一次循环时，Repo 已经是新的了
        
    print(f"[{tool_name}] 🎉 Chain Execution Completed.")
    return True

def single_build(args):
    """执行构建流程"""
    repo_dir = os.path.abspath(args.torepo)
    source_dir_origin = os.path.abspath(args.source)
    pkg_name = os.path.basename(source_dir_origin)
    
    # --- 1. 变量初始化 ---
    target_mem = args.max_mem
    target_jobs = args.jobs
    target_net = args.enable_network
    target_tmp_ssd = args.use_tmp_ssd
    target_ssd = args.use_ssd
    target_extras = []
    
    # 初始化仓库列表 (从 CLI 继承)
    # 注意：我们要用 list() 复制一份，防止污染全局 args 对象
    target_addrepo = list(args.addrepo) if args.addrepo else []

    # --- 2. 自动定位配置文件 ---
    conf_path = getattr(args, 'conf', None)
    if not conf_path:
        # 默认去 forges/conf.json 找
        default_conf = os.path.join(repo_dir, "forges", "conf.json")
        if os.path.exists(default_conf):
            conf_path = default_conf
            print(f"[{tool_name}] ℹ️  Auto-detected config: {conf_path}")

    # --- 3. 读取并应用配置 ---
    if conf_path and os.path.exists(conf_path):
        try:
            with open(conf_path, 'r') as f:
                # 获取特定包的配置
                full_config = json.load(f)
                p_cfg = full_config.get(pkg_name)
                
                if p_cfg:
                    print(f"[{tool_name}] 🎯 Applying config for '{pkg_name}'")
                    # get(key, default) -> 有则覆盖，无则保持 CLI 原值
                    if "max_mem" in p_cfg: target_mem = p_cfg["max_mem"]
                    if "jobs" in p_cfg: target_jobs = p_cfg["jobs"]
                    if "enable_network" in p_cfg: target_net = p_cfg["enable_network"]
                    if "use_tmp_ssd" in p_cfg: target_tmp_ssd = p_cfg["use_tmp_ssd"]
                    if "use_ssd" in p_cfg: target_ssd = p_cfg["use_ssd"]
                    if "extra_mock_args" in p_cfg: target_extras = p_cfg["extra_mock_args"]
                    
                    # [重点] 合并 addrepo
                    conf_repos = p_cfg.get("addrepo", [])
                    if conf_repos:
                        print(f"[{tool_name}] 📦 Injecting {len(conf_repos)} extra repos")
                        target_addrepo.extend(conf_repos)
                else:
                    print(f"[{tool_name}] ⚠️  No config found for '{pkg_name}' in conf.json")
                        
        except Exception as e:
            print(f"[{tool_name}] ⚠️ Config load error: {e}")

    # --- 4. 准备 Mock 环境 ---
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
    mock_base_args = ["unbuffer", "mock", "--define", "_changelog_date_check 0"]

    if target_mem:
        if not shutil.which("systemd-run"):
            print(f"[{tool_name}] Error: --max-mem requires 'systemd-run'")
            sys.exit(1)
        
        systemd_props = ["-p", f"MemoryMax={target_mem}"]
        mem_bytes = parse_size_bytes(target_mem)
        if mem_bytes:
            swap_bytes = int(mem_bytes * 0.5)
            systemd_props.extend(["-p", f"MemorySwapMax={swap_bytes}"])
        
        mock_base_args = ["systemd-run", "--scope", "--user", "--quiet"] + systemd_props + mock_base_args    

    if target_net:
        print(f"[{tool_name}] 🌐 Network access enabled.")
        mock_base_args.append("--enable-network")
    
    if not (target_ssd or target_tmp_ssd):
        mock_base_args.append("--enable-plugin=tmpfs")
    if target_tmp_ssd:
        mock_base_args.append("--enable-plugin=tmpfs_tmponly")
        
    if target_jobs:
        mock_base_args.extend(["--define", f"_smp_mflags -j{target_jobs}"])

    if target_extras:
        mock_base_args.extend(target_extras)

    # 路径检查
    if not os.path.isdir(source_dir_origin): 
        print(f"Error: Source dir {source_dir_origin} not found")
        return False
        
    if not os.path.isdir(repo_dir): 
        print(f"Error: Repo dir {repo_dir} not found")
        return False

    # 确定 Spec
    spec_file_arg = args.spec
    if spec_file_arg:
        spec_path_origin = os.path.abspath(spec_file_arg)
    else:
        specs = glob.glob(os.path.join(source_dir_origin, "*.spec"))
        if not specs: 
            print("Error: No spec file found")
            return False
        spec_path_origin = specs[0]

    # --- 5. 开始构建 ---
    with tempfile.TemporaryDirectory(prefix="lc-build-") as work_dir:
        build_success = False
        spec_name = os.path.basename(spec_path_origin).replace('.spec','')
        log_source_dir = work_dir 
        rpm_result_dir = None 

        try:
            print(f"[{tool_name}] Preparing sources for {pkg_name}...")
            temp_src_dir = os.path.join(work_dir, "clean_sources")
            shutil.copytree(source_dir_origin, temp_src_dir, dirs_exist_ok=True, 
                            ignore=shutil.ignore_patterns('.git', '.svn'))
            rel_spec_path = os.path.relpath(spec_path_origin, source_dir_origin)
            temp_spec_path = os.path.join(temp_src_dir, rel_spec_path)
            spec_name = os.path.basename(temp_spec_path).replace('.spec','')

            # Spectool
            run_cmd(["spectool", "-g", "-C", temp_src_dir, temp_spec_path], cwd=temp_src_dir)
            
            # Version Bump
            _bump_spec_release(temp_spec_path)

            # SRPM
            srpm_result_dir = os.path.join(work_dir, "srpm_result")
            os.makedirs(srpm_result_dir)
            cmd_srpm = mock_base_args + ["--buildsrpm", "--spec", temp_spec_path, "--sources", temp_src_dir, "--resultdir", srpm_result_dir]
            run_cmd(cmd_srpm)
            src_rpms = glob.glob(os.path.join(srpm_result_dir, "*.src.rpm"))
            if not src_rpms: raise Exception("SRPM creation failed")
            target_srpm = src_rpms[0]

            # RPM
            rpm_result_dir = os.path.join(work_dir, "rpm_result")
            os.makedirs(rpm_result_dir)
            
            # 组装构建命令
            cmd_rpm = mock_base_args + ["--rebuild", target_srpm, "--resultdir", rpm_result_dir]
        
            # [关键] 注入本地 Repo
            cmd_rpm.append(f"--addrepo=file://{repo_dir}")

            # [关键] 注入外部 Repos (CLI + Conf)
            if target_addrepo:
                print(f"[{tool_name}] 🔗 Active repositories for build:")
                for repo in target_addrepo:
                    # 如果是本地路径，必须转为 file://
                    if os.path.exists(repo):
                        repo_url = f"file://{os.path.abspath(repo)}"
                    else:
                        repo_url = repo
                    
                    print(f"  -> {repo_url}")
                    cmd_rpm.append(f"--addrepo={repo_url}")
            
            # 执行
            run_cmd(cmd_rpm)

            # 保存结果
            new_rpms = [] 
            built_rpms = glob.glob(os.path.join(rpm_result_dir, "*.rpm"))
            for rpm in built_rpms:
                if "debuginfo" in rpm or rpm.endswith(".src.rpm"): continue
                dest = shutil.copy2(rpm, repo_dir)
                new_rpms.append(dest)
                print(f"-> Saved RPM: {os.path.basename(rpm)}")

            if gpg_key_id:
                sign_rpms(repo_dir, new_rpms, gpg_key_id)
            
            build_success = True
            log_source_dir = rpm_result_dir

        except Exception as e:
            print(f"[{tool_name}] ❌ Build Failed: {e}")
            build_success = False
            log_source_dir = work_dir

        finally:
            try:
                logs_dir = os.path.join(repo_dir, ".build_logs")
                if not os.path.exists(logs_dir): os.makedirs(logs_dir)
                timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
                status_str = "SUCCESS" if build_success else "FAILED"
                archive_name = f"{pkg_name}-{status_str}-{timestamp}.tar.gz"
                archive_path = os.path.join(logs_dir, archive_name)
                with tarfile.open(archive_path, "w:gz") as tar:
                    tar.add(log_source_dir, arcname=f"build-logs-{status_str}")
                print(f"[{tool_name}] Log saved: {archive_path}")
            except Exception as log_err:
                print(f"[{tool_name}] Log error: {log_err}")

    if not build_success: return False

    run_cmd(["createrepo_c", "--update", repo_dir])
    if gpg_key_id: sign_repodata(repo_dir, gpg_key_id)
        
    print(f"[{tool_name}] Package '{pkg_name}' done!")
    return True
def do_build(args):
    if args.chain:
        return chain(args)
    else: 
        return single_build(args)

def main():
    parser = argparse.ArgumentParser(description="Local Copr (lc) - Secure Build Tool")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Init
    p_init = subparsers.add_parser("init", help="Init new repo")
    p_init.add_argument("--repo", required=True)
    p_init.add_argument("--gpg-key", help="GPG Key ID to enable signing (e.g. 3AA5C0AD)")
    p_init.add_argument("--enable-rebuild", action="store_true", help="Enable automatic dependency rebuilds")
    p_init.set_defaults(func=do_init)
    p_init.set_defaults(func=do_init)

    # Delete
    p_del = subparsers.add_parser("remove", help="Delete a repo")
    p_del.add_argument("--repo", required=True)
    p_del.set_defaults(func=do_delete)

    # Build
    p_build = subparsers.add_parser("build", help="Build RPM")
    p_build.add_argument("--source", help="Source dir (required unless --chain)")
    p_build.add_argument("--torepo", required=True)
    p_build.add_argument("--spec", help="Specific spec")
    p_build.add_argument("--addrepo", action="append")
    p_build.add_argument("--use-ssd", action="store_true")
    p_build.add_argument("--use-tmp-ssd", action="store_true")
    p_build.add_argument("--jobs", type=int, help="Limit build cores (e.g. 8 to prevent OOM)")
    p_build.add_argument("--enable-network", action="store_true", help="Allow network access during build (default: offline)")
    p_build.add_argument("--max-mem", help="Limit max memory (e.g. 4G, 512M) using systemd-run")
    p_build.add_argument("--chain", help="Path to JSON build plan")
    p_build.add_argument("--conf", help="JSON config file for package-specific args") 
    p_build.set_defaults(func=do_build)

    args = parser.parse_args()
    if args.command == 'build':
        if not args.source and not args.chain:
            parser.error("Argument error: --source is required unless --chain is specified.")    
    args.func(args)

if __name__ == "__main__":
    main()