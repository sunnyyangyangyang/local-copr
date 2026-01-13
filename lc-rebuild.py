#!/usr/bin/env python3
"""
lc-rebuild (v4.0) - The Planner (Clean Architecture)
Convention:
  - Folder Name in 'forges/' is the unique Package ID (pkg_id).
  - conf.json keys MUST match Folder Names.
  - Automatically maps all RPM subpackages to their parent Folder ID.
  - No Regex Fallback: Relies purely on valid spec parsing.
"""

import os
import sys
import json
import argparse
import subprocess
import glob
from collections import defaultdict, deque

try:
    import libdnf5
except ImportError:
    print("Error: libdnf5 not found. Install with: sudo dnf install python3-libdnf5")
    sys.exit(1)

class Planner:
    def __init__(self, repo_path, add_repos=None, conf_path=None, verbose=False):
        self.repo_path = os.path.abspath(repo_path)
        self.forges_dir = os.path.join(self.repo_path, "forges")
        self.add_repos = add_repos or []
        self.verbose = verbose
        
        # 核心映射表： capability (e.g., pytorch-devel) -> pkg_id (e.g., pytorch)
        self.local_provides_map = {} 
        self.base = libdnf5.base.Base()
        self.cap_cache = {}
        
        # 加载外部配置
        if conf_path and os.path.exists(conf_path):
            self._load_addrepo_from_conf(conf_path)
        
        self._setup_repos()
        self._scan_local_registry()

    def log(self, msg):
        if self.verbose:
            print(f"[DEBUG] {msg}")

    def _load_addrepo_from_conf(self, conf_path):
        """
        从 conf.json 加载额外仓库。
        注意：conf.json 的 key 必须对应 forges/ 下的目录名。
        """
        try:
            with open(conf_path, 'r') as f:
                conf = json.load(f)
            
            # 这里不需要校验 key，因为我们只取里面的 addrepo 配置
            # 只要它是合法的 JSON 即可
            all_repos = set(self.add_repos)
            for pkg_id, pkg_conf in conf.items():
                repos = pkg_conf.get("addrepo", [])
                all_repos.update(repos)
            self.add_repos = list(all_repos)
            
        except Exception as e:
            print(f"[Planner] Warning: Failed to load conf.json: {e}")

    def _setup_repos(self):
        """初始化 libdnf5 用于查询外部依赖"""
        print(f"[Planner] Loading repositories...")
        self.base.load_config()
        repo_sack = self.base.get_repo_sack()
        
        # 本地 Repo
        local_repo = repo_sack.create_repo("lc-local")
        local_conf = local_repo.get_config()
        local_conf.baseurl = [f"file://{self.repo_path}"]
        local_conf.enabled = True
        local_conf.gpgcheck = False
        
        # 外部 Repos
        for idx, url in enumerate(self.add_repos):
            if os.path.isdir(url): url = f"file://{os.path.abspath(url)}"
            extra_repo = repo_sack.create_repo(f"lc-extra-{idx}")
            extra_repo.get_config().baseurl = [url]
            extra_repo.get_config().enabled = True
        
        self.base.setup()
        try:
            repo_sack.load_repos()
        except:
            pass 

    def _get_spec_path(self, pkg_dir):
        """在目录下查找唯一的 .spec 文件"""
        specs = glob.glob(os.path.join(pkg_dir, "*.spec"))
        if specs:
            return specs[0]
        return None

    def _scan_local_registry(self):
        """
        遍历 forges/ 下的所有目录，建立 '包名 -> 目录名' 的映射。
        这是核心逻辑：无论 Spec 叫什么，都以目录名为准。
        """
        if not os.path.exists(self.forges_dir): return
        
        print("[Planner] Scanning local sources (Strict Mode)...")
        # 获取所有目录名作为 pkg_id
        pkg_ids = [d for d in os.listdir(self.forges_dir) if os.path.isdir(os.path.join(self.forges_dir, d))]
        
        for pkg_id in pkg_ids:
            pkg_dir = os.path.join(self.forges_dir, pkg_id)
            spec_path = self._get_spec_path(pkg_dir)
            
            if not spec_path:
                self.log(f"Skipping {pkg_id}: No spec file found.")
                continue
            
            # 使用相对路径 + CWD，确保 rpmspec 能找到 patch 文件
            rel_spec = os.path.basename(spec_path)
            
            try:
                # 1. 获取纯净的 RPM 包名 (Name, Subpackages)
                # --qf %{NAME} 确保不带版本号，解决匹配问题
                cmd = ["rpmspec", "-q", "--qf", "%{NAME}\n", rel_spec]
                output = subprocess.check_output(cmd, cwd=pkg_dir, text=True, stderr=subprocess.PIPE)
                
                for line in output.splitlines():
                    rpm_name = line.strip()
                    if rpm_name: 
                        # 注册映射：谁提供了 rpm_name？是 pkg_id (目录)
                        self.local_provides_map[rpm_name] = pkg_id
                
                # 2. 获取显式的 Provides (虚拟能力)
                # 例如 Provides: python3-torch
                cmd_prov = ["rpmspec", "-q", "--provides", rel_spec]
                output_prov = subprocess.check_output(cmd_prov, cwd=pkg_dir, text=True, stderr=subprocess.PIPE)
                
                for line in output_prov.splitlines():
                    cap = line.strip()
                    if cap:
                        self.local_provides_map[cap] = pkg_id
                        
            except subprocess.CalledProcessError as e:
                # 在 V4.0 中，如果 rpmspec 失败，我们不再容错。
                # 这意味着用户的 Spec 必须是合法的（或宿主机环境必须满足解析条件）。
                print(f"[Planner] ⚠️  Parse failed for '{pkg_id}': {e.stderr.strip().splitlines()[0]}")

        self.log(f"Registered {len(self.local_provides_map)} local capabilities.")

    def get_spec_build_requires(self, spec_path, pkg_dir):
        """解析 BuildRequires"""
        deps = set()
        rel_spec = os.path.basename(spec_path)

        try:
            cmd = ["rpmspec", "-q", "--buildrequires", rel_spec]
            result = subprocess.check_output(cmd, cwd=pkg_dir, text=True, stderr=subprocess.DEVNULL)
            for line in result.splitlines():
                deps.add(line.strip())
        except subprocess.CalledProcessError:
            pass
            
        return deps

    def resolve_provider(self, capability):
        """解析谁提供了这个能力"""
        if capability in self.cap_cache:
            return self.cap_cache[capability]
        
        # 1. 优先查本地源码映射 (Source Truth)
        if capability in self.local_provides_map:
            provider_id = self.local_provides_map[capability]
            self.cap_cache[capability] = provider_id
            return provider_id

        # 2. 查二进制仓库 (Binary Truth)
        try:
            query = libdnf5.rpm.PackageQuery(self.base)
            query.filter_provides([capability])
            for pkg in query:  # pyright: ignore[reportGeneralTypeIssues]
                # 注意：外部仓库返回的是 RPM Name，但在我们的逻辑里，
                # 如果它不是本地管理的，我们其实只关心它存在即可。
                # 返回 RPM Name 作为 ID。
                provider_name = pkg.get_name()
                self.cap_cache[capability] = provider_name
                return provider_name
        except:
            pass
            
        return None

    def generate_plan(self, trigger_ids, output_file):
        if not os.path.exists(self.forges_dir): return
        
        # 获取所有被管理的包 ID (即目录名)
        managed_pkg_ids = set(
            d for d in os.listdir(self.forges_dir) 
            if os.path.isdir(os.path.join(self.forges_dir, d))
        )
        
        print(f"[Planner] Graphing dependencies for {len(managed_pkg_ids)} projects...")
        
        dep_graph = defaultdict(set)
        
        for consumer_id in managed_pkg_ids:
            pkg_dir = os.path.join(self.forges_dir, consumer_id)
            spec_path = self._get_spec_path(pkg_dir)
            if not spec_path: continue
            
            # 解析需求
            reqs = self.get_spec_build_requires(spec_path, pkg_dir)
            
            for req in reqs:
                if req.startswith("rpmlib(") or req.startswith("config("): continue
                
                provider_id = self.resolve_provider(req)
                
                # 只有当提供者也是本地管理的包时，才建立图连接
                if provider_id and provider_id in managed_pkg_ids:
                    if provider_id != consumer_id:
                        # 记录：provider 被 consumer 依赖
                        dep_graph[provider_id].add(consumer_id)
                        self.log(f"Link: {provider_id} -> {consumer_id} (via {req})")

        # BFS 遍历受影响的包
        affected = {} 
        queue = deque()
        
        # trigger_ids 必须是目录名
        for pid in trigger_ids:
            if pid not in managed_pkg_ids:
                print(f"[Planner] Warning: Trigger '{pid}' is not a valid local project directory.")
                continue
            affected[pid] = 0
            queue.append((pid, 0))
            
        while queue:
            curr, level = queue.popleft()
            consumers = dep_graph.get(curr, [])
            for consumer in consumers:
                next_level = level + 1
                if consumer not in affected or affected[consumer] > next_level:
                    affected[consumer] = next_level
                    queue.append((consumer, next_level))
                    
        # 生成任务列表
        tasks = []
        for pkg_id, lvl in affected.items():
            tasks.append({
                "package": pkg_id, # 这是目录名
                "level": lvl
            })
            
        # 按层级排序
        tasks.sort(key=lambda x: (x['level'], x['package']))
        
        plan = {"tasks": tasks}
        
        with open(output_file, "w") as f:
            json.dump(plan, f, indent=2)
            
        print(f"[Planner] Plan saved. Tasks: {len(tasks)}")
        for t in tasks:
            print(f"  - L{t['level']}: {t['package']}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--trigger", action="append", required=True, help="Trigger by FOLDER name")
    parser.add_argument("--addrepo", action="append")
    parser.add_argument("--conf", help="Path to conf.json (keys must match FOLDER names)")
    parser.add_argument("--output", required=True)
    parser.add_argument("--verbose", action="store_true")
    
    args = parser.parse_args()
    
    conf_path = args.conf
    if not conf_path:
        default_conf = os.path.join(args.repo, "forges", "conf.json")
        if os.path.exists(default_conf):
            conf_path = default_conf
    
    planner = Planner(args.repo, args.addrepo, conf_path, verbose=args.verbose)
    planner.generate_plan(args.trigger, args.output)

if __name__ == "__main__":
    main()