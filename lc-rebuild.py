#!/usr/bin/env python3
"""
lc-rebuild (v3) - The Planner (Libdnf5 Edition)
High-performance build dependency resolution for Local Copr.
Copyright (C) 2026 Yuanxi (Sunny) Yang
"""

import os
import sys
import json
import argparse
import subprocess
from collections import defaultdict, deque
from datetime import datetime

# 尝试导入 libdnf5
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
        
        # 初始化 Libdnf5 Base
        self.base = libdnf5.base.Base()
        self.cap_cache = {}  # 缓存: capability -> provider_name
        
        # 初始化仓库
        self._setup_repos()

    def _setup_repos(self):
        """配置并加载仓库 (Libdnf5 方式)"""
        print(f"[Planner] Loading repositories via Libdnf5...")
        
        # 1. 加载系统配置 (读取 /etc/dnf/dnf.conf 和 /etc/yum.repos.d/)
        self.base.load_config()
        
        # 获取 Repo Sack (仓库集合管理器)
        repo_sack = self.base.get_repo_sack()
        
        # 2. 添加 Local Copr 自身
        local_repo = repo_sack.create_repo("lc-internal-local")
        local_conf = local_repo.get_config()
        local_conf.baseurl = [f"file://{self.repo_path}"]
        local_conf.enabled = True
        
        # 3. 添加额外的 Repo (--addrepo)
        for idx, url in enumerate(self.add_repos):
            if os.path.isdir(url):
                url = f"file://{os.path.abspath(url)}"
            
            extra_repo = repo_sack.create_repo(f"lc-internal-extra-{idx}")
            extra_repo.get_config().baseurl = [url]
            extra_repo.get_config().enabled = True
        
        # 4. ⚠️ 关键修复：调用 setup() 来完成 Base 初始化
        try:
            self.base.setup()
        except Exception as e:
            print(f"Warning during base.setup(): {e}")
        
        # 5. 加载元数据
        try:
            repo_sack.load_repos()
            
            # 获取包数量统计
            pkg_query = libdnf5.rpm.PackageQuery(self.base)
            print(f"[Planner] Sack loaded. Total available packages: {len(pkg_query)}")
        except Exception as e:
            print(f"Warning: Could not load some repos: {e}")
            print("         (This is normal if local repo has no repodata yet)")

    def get_spec_build_requires(self, spec_path):
        """
        使用 rpmspec 解析 Spec 文件中的 BuildRequires。
        这是最稳健的方法,因为它能正确处理 %ifdef, %package 等宏逻辑。
        """
        try:
            # -q --buildrequires: 查询构建依赖
            # --srpm: 模拟 SRPM 构建环境 (处理 SourceX 等宏)
            cmd = ["rpmspec", "-q", "--buildrequires", spec_path]
            result = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)
            
            deps = set()
            for line in result.splitlines():
                line = line.strip()
                if line: deps.add(line)
            return deps
        except subprocess.CalledProcessError:
            # Spec 可能语法错误,或者依赖宏未定义
            print(f"Warning: Could not parse spec {spec_path}")
            return set()

    def resolve_provider(self, capability):
        """
        使用 Libdnf5 查询哪个包提供了这个 capability
        """
        if capability in self.cap_cache:
            return self.cap_cache[capability]
            
        try:
            # 1. 创建查询对象
            query = libdnf5.rpm.PackageQuery(self.base)
            
            # 2. 过滤提供了该 capability 的包
            query.filter_provides([capability])
            
            # 3. 获取结果
            provider = None
            
            # 只要找到一个就行
            for pkg in query:
                provider = pkg.get_name()
                break
                
            self.cap_cache[capability] = provider
            return provider
        except Exception as e:
            # 如果查询失败（比如 pool 未初始化），返回 None
            print(f"Warning: Could not resolve '{capability}': {e}")
            return None

    def generate_plan(self, trigger_pkgs, output_file):
        """生成构建计划"""
        if not os.path.exists(self.forges_dir):
            print("Error: No forges directory found.")
            sys.exit(1)
            
        # 1. 获取所有受管包列表
        managed_pkgs = set(
            d for d in os.listdir(self.forges_dir) 
            if os.path.isdir(os.path.join(self.forges_dir, d))
        )
        
        print(f"[Planner] Scanning specs for {len(managed_pkgs)} managed packages...")
        
        # 2. 构建反向依赖图 (Provider -> Consumers)
        dep_graph = defaultdict(set)
        
        for consumer in managed_pkgs:
            # 找到 spec 文件
            pkg_dir = os.path.join(self.forges_dir, consumer)
            spec_path = os.path.join(pkg_dir, f"{consumer}.spec")
            if not os.path.exists(spec_path):
                # 尝试找任意 .spec
                specs = [f for f in os.listdir(pkg_dir) if f.endswith('.spec')]
                if specs: spec_path = os.path.join(pkg_dir, specs[0])
                else: continue
            
            # 解析依赖
            reqs = self.get_spec_build_requires(spec_path)
            
            for req in reqs:
                if req.startswith("rpmlib(") or req.startswith("config("): continue
                
                # 查询 DNF 数据库
                provider = self.resolve_provider(req)
                
                # 关键逻辑：如果 Provider 也是我们的受管包，则建立连接
                # 如果 Provider 是 glibc (系统包)，则忽略
                if provider and provider in managed_pkgs:
                    if provider != consumer:
                        dep_graph[provider].add(consumer)

        # 3. BFS 搜索影响范围
        print(f"[Planner] Analyzing chain for triggers: {', '.join(trigger_pkgs)}")
        
        affected = {} # pkg -> level
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
                    
        # 4. 输出结果
        tasks = []
        for pkg, lvl in affected.items():
            tasks.append({
                "package": pkg,
                "level": lvl,
                "reason": "trigger" if lvl == 0 else "build-dependency"
            })
            
        # 排序：Level 升序 -> 包名 字母序
        tasks.sort(key=lambda x: (x['level'], x['package']))
        
        plan = {
            "created_at": datetime.now().isoformat(),
            "engine": "libdnf5",
            "triggers": trigger_pkgs,
            "tasks": tasks
        }
        
        with open(output_file, "w") as f:
            json.dump(plan, f, indent=2)
            
        print(f"[Planner] Success. Plan saved to {output_file}")
        print(f"          Total packages to rebuild: {len(tasks)}")
        for t in tasks:
            print(f"          - Level {t['level']}: {t['package']}")

def main():
    parser = argparse.ArgumentParser(description="lc-rebuild (libdnf5)")
    parser.add_argument("--repo", required=True, help="Local Copr root path")
    parser.add_argument("--trigger", action="append", required=True, help="Changed packages")
    parser.add_argument("--addrepo", action="append", help="Additional repo URLs/Paths")
    parser.add_argument("--output", required=True, help="Output JSON path")
    
    args = parser.parse_args()
    
    planner = Planner(args.repo, args.addrepo)
    planner.generate_plan(args.trigger, args.output)

if __name__ == "__main__":
    main()