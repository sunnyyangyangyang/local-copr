# -*- coding: utf-8 -*-
# vim:expandtab:autoindent:tabstop=4:shiftwidth=4:filetype=python:textwidth=0:
# License: GPL3 or later see COPYING
# Written by Yuanxi "Sunny" Yang for Local Copr Project
# Copyright (C) 2026 Sunny Yang <yxh9956@gmail.com>
# Based on work originally written by Michael Brown
# Original copyright (C) 2007 Michael E Brown <mebrown@michaels-house.net>

# python library imports
import os

# our imports
from mockbuild.trace_decorator import getLog, traceLog
import mockbuild.util

requires_api_version = "1.1"


# plugin entry point
@traceLog()
def init(plugins, conf, buildroot):
    system_ram_bytes = os.sysconf(os.sysconf_names['SC_PAGE_SIZE']) * os.sysconf(os.sysconf_names['SC_PHYS_PAGES'])
    system_ram_mb = system_ram_bytes / (1024 * 1024)
    if system_ram_mb > conf.get('required_ram_mb', 4096):  # Default 4GB requirement
        SelectiveTmpfs(plugins, conf, buildroot)
    else:
        getLog().warning(
            "Selective Tmpfs plugin disabled. "
            "System does not have the required amount of RAM to enable selective tmpfs. "
            "System has %sMB RAM, but the config specifies the minimum required is %sMB RAM. ",
            system_ram_mb, conf.get('required_ram_mb', 4096))


class SelectiveTmpfs(object):
    """Selective Tmpfs - Only mount /tmp on tmpfs, keep other directories on SSD"""
    
    @traceLog()
    def __init__(self, plugins, conf, buildroot):
        self.buildroot = buildroot
        self.main_config = buildroot.config
        self.state = buildroot.state
        self.conf = conf
        self.maxSize = self.conf.get('max_fs_size')
        self.mode = self.conf.get('mode', '1777')   # /tmp 的权限
        
        # 关键修改：定义 /tmp 路径
        self.tmpfs_path = os.path.join(buildroot.make_chroot_path(), 'tmp')
        
        self.optArgs = ['-o', 'mode=%s' % self.mode]
        self.optArgs += ['-o', 'nr_inodes=0']
        if self.maxSize:
            self.optArgs += ['-o', 'size=' + self.maxSize]
        
        plugins.add_hook("mount_root", self._tmpfsMount)
        plugins.add_hook("postumount", self._tmpfsPostUmount)
        plugins.add_hook("umount_root", self._tmpfsUmount)
        
        # 关键修改：检查 /tmp 是否已挂载
        if not os.path.ismount(self.tmpfs_path):
            self.mounted = False
        else:
            self.mounted = True
        
        getLog().info("Selective tmpfs initialized for /tmp")

    @traceLog()
    def _tmpfsMount(self):
        if not self.mounted:
            # 关键修改：创建 /tmp 目录（如果不存在）
            os.makedirs(self.tmpfs_path, mode=0o1777, exist_ok=True)
            
            getLog().info("mounting tmpfs at %s.", self.tmpfs_path)
            mountCmd = ["mount", "-n", "-t", "tmpfs"] + self.optArgs + \
                    ["mock_chroot_tmpfs", self.tmpfs_path]  # 挂载到 /tmp
            mockbuild.util.do(mountCmd, shell=False)
        else:
            getLog().info("reusing tmpfs at %s.", self.tmpfs_path)
        self.mounted = True


    @traceLog()
    def _tmpfsPostUmount(self):
        if "keep_mounted" in self.conf and self.conf["keep_mounted"]:
            self.mounted = False
        else:
            self._tmpfsUmount()

    @traceLog()
    def _tmpfsUmount(self):
        if not self.mounted:
            return
        force = False
        getLog().info("unmounting tmpfs from /tmp.")
        umountCmd = ["umount", "-n", self.tmpfs_path]  # 卸载 /tmp
        try:
            mockbuild.util.do(umountCmd, shell=False)
        except:
            getLog().warning("tmpfs-plugin: exception while umounting tmpfs! (cwd: %s)", 
                            mockbuild.util.pretty_getcwd())
            force = True
        if force:
            umountCmd = ["umount", "-R", "-n", "-f", self.tmpfs_path]
            try:
                mockbuild.util.do(umountCmd, shell=False)
            except:
                getLog().warning("tmpfs-plugin: exception while force umounting tmpfs! (cwd: %s)", 
                            mockbuild.util.pretty_getcwd())
        self.mounted = False
