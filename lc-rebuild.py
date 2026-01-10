#!/usr/bin/env python3
"""
lc-rebuild (v3.2) - The Planner (Hybrid Source/Repo Edition)
High-performance build dependency resolution for Local Copr.

Based on depsolve.py from Fedora Koschei project:
  Copyright (C) 2014-2016 Red Hat, Inc.
  Author: Michael Simacek <msimacek@redhat.com>
  Author: Mikolaj Izdebski <mizdebsk@redhat.com>

Original license: GNU General Public License v2 or later
"""

import os
import sys
import json
import argparse
import subprocess
from collections import defaultdict, deque
from datetime import datetime

try:
    import libdnf5
except ImportError:
    print("Error: libdnf5 not found. Install with: sudo dnf install python3-libdnf5")
    sys.exit(1)

class Planner:
    def __init__(self, repo_path, add_repos=None):
        self.repo_path = os.path.abspath(repo_path)
        self.forges_dir = os.path.join(self.repo_path, "forges")
        self.add_repos = add_repos or []
        
        # 1. 初始化 Libdnf5
        self.base = libdnf5.base.Base()
        self.cap_cache = {}  
        
        # 2. 初始化本地 Spec 缓存 (上帝视角)
        self.local_provides_map = {} # capability -> pkg_name
        
        # 3. 执行加载
        self._setup_repos()
        self._scan_local_provides()

    def _setup_repos(self):
        """配置并加载仓库"""
        print(f"[Planner] Loading repositories via Libdnf5...")
        self.base.load_config()
        repo_sack = self.base.get_repo_sack()
        
        local_repo = repo_sack.create_repo("lc-internal-local")
        local_conf = local_repo.get_config()
        local_conf.baseurl = [f"file://{self.repo_path}"]
        local_conf.enabled = True
        local_conf.gpgcheck = False # 规划阶段忽略签名
        
        for idx, url in enumerate(self.add_repos):
            if os.path.isdir(url): url = f"file://{os.path.abspath(url)}"
            extra_repo = repo_sack.create_repo(f"lc-internal-extra-{idx}")
            extra_repo.get_config().baseurl = [url]
            extra_repo.get_config().enabled = True
        
        self.base.setup()
        
        try:
            repo_sack.load_repos()
        except Exception as e:
            print(f"[Planner] Warning: Repo load issues (ignorable): {e}")

    def _scan_local_provides(self):
        """
        [关键增强] 扫描本地所有 Spec 文件，直接获取 Provides 信息。
        这解决了 Repo 延迟或缓存导致的依赖丢失问题。
        """
        if not os.path.exists(self.forges_dir): return
        
        print("[Planner] Pre-scanning local specs for Provides...")
        pkgs = [d for d in os.listdir(self.forges_dir) if os.path.isdir(os.path.join(self.forges_dir, d))]
        
        for pkg in pkgs:
            spec_path = os.path.join(self.forges_dir, pkg, f"{pkg}.spec")
            if not os.path.exists(spec_path): continue
            
            try:
                # 查询该 Spec 提供了什么 Capability
                # rpmspec -q --provides xxx.spec
                cmd = ["rpmspec", "-q", "--provides", spec_path]
                # stderr=DEVNULL 忽略宏未定义的警告
                output = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)
                
                for line in output.splitlines():
                    cap = line.strip()
                    if cap:
                        # 记录映射: lib-base-capability -> lib-base
                        self.local_provides_map[cap] = pkg
            except:
                pass

    def get_spec_build_requires(self, spec_path):
        try:
            cmd = ["rpmspec", "-q", "--buildrequires", spec_path]
            result = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)
            deps = set()
            for line in result.splitlines():
                line = line.strip()
                if line: deps.add(line)
            return deps
        except:
            return set()

    def resolve_provider(self, capability):
        """
        解析 Capability 是由哪个包提供的。
        优先级: 本地 Spec 映射 > Libdnf5 仓库查询
        """
        if capability in self.cap_cache:
            return self.cap_cache[capability]
            
        # 1. 优先查本地 Spec 映射 (Source Truth)
        if capability in self.local_provides_map:
            provider = self.local_provides_map[capability]
            self.cap_cache[capability] = provider
            return provider

        # 2. 查二进制仓库 (Binary Truth)
        try:
            query = libdnf5.rpm.PackageQuery(self.base)
            query.filter_provides([capability])
            for pkg in query:
                provider = pkg.get_name()
                self.cap_cache[capability] = provider
                return provider
        except:
            pass
            
        return None

    def generate_plan(self, trigger_pkgs, output_file):
        if not os.path.exists(self.forges_dir): return
            
        managed_pkgs = set(
            d for d in os.listdir(self.forges_dir) 
            if os.path.isdir(os.path.join(self.forges_dir, d))
        )
        
        print(f"[Planner] Analyzing dependencies for {len(managed_pkgs)} packages...")
        
        dep_graph = defaultdict(set)
        
        for consumer in managed_pkgs:
            spec_path = os.path.join(self.forges_dir, consumer, f"{consumer}.spec")
            if not os.path.exists(spec_path): continue
            
            reqs = self.get_spec_build_requires(spec_path)
            
            for req in reqs:
                if req.startswith("rpmlib(") or req.startswith("config("): continue
                
                provider = self.resolve_provider(req)
                
                if provider and provider in managed_pkgs:
                    if provider != consumer:
                        dep_graph[provider].add(consumer)

        # BFS 搜索
        affected = {} 
        queue = deque()
        
        for p in trigger_pkgs:
            affected[p] = 0
            queue.append((p, 0))
            
        while queue:
            curr, level = queue.popleft()
            consumers = dep_graph.get(curr, [])
            for consumer in consumers:
                next_level = level + 1
                if consumer not in affected or affected[consumer] > next_level:
                    affected[consumer] = next_level
                    queue.append((consumer, next_level))
                    
        tasks = []
        for pkg, lvl in affected.items():
            tasks.append({
                "package": pkg,
                "level": lvl
            })
            
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
    parser.add_argument("--trigger", action="append", required=True)
    parser.add_argument("--addrepo", action="append")
    parser.add_argument("--output", required=True)
    
    args = parser.parse_args()
    
    planner = Planner(args.repo, args.addrepo)
    planner.generate_plan(args.trigger, args.output)

if __name__ == "__main__":
    main()
