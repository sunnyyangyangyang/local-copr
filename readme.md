### P0: 核心功能完善 (Core Features)

- [ ] **Native Git Support (Git 直通车)**
    *   **现状**：目前 `lc` 依赖 `shutil.copytree` 复制目录，且依赖 Spec 里写死的 `Source0` URL 下载 tar 包。
    *   **目标**：支持直接从本地 Git 仓库生成 Source，无需 Spec 里有远程 URL。
    *   **实现思路**：
        1.  检测 Source 目录是否有 `.git`。
        2.  如果有，解析 Spec 里的 `Source0` 文件名（例如 `corefreq-2.0.9.tar.gz`）。
        3.  使用 `git archive --format=tar.gz --prefix=corefreq-2.0.9/ HEAD -o ...` 直接在内存中生成这个压缩包。
        4.  让 Mock 使用这个生成的包，跳过 `spectool` 下载。
    *   **价值**：彻底解决“为了打包还得先把代码推到 GitHub Release”的尴尬，实现真正的 Local First。

- [ ] **Self-Packaging (自举打包)**
    *   **现状**：`lc` 只是一个脚本。
    *   **目标**：创建 `local-copr.spec`，把 `lc` 打包成 RPM。
    *   **内容**：
        *   定义 `Requires: mock, python3, createrepo_c, ...`
        *   定义 `%install` 将脚本放入 `/usr/bin/lc`。
        *   使用 `lc` 来构建 `local-copr.rpm`。

### P1: 用户体验提升 (UX Improvements)

- [ ] **Global Configuration (全局配置)**
    *   **痛点**：每次都要输 `--torepo` 和 `--gpg-key` 很烦。
    *   **方案**：支持读取 `~/.config/lc/config.toml` 或环境变量。
    *   **配置项**：默认仓库路径、默认 GPG Key ID、默认 Mock Config (比如想默认用 `fedora-rawhide`)。

- [ ] **Debug Shell (调试模式)**
    *   **痛点**：构建失败时，Mock 环境直接销毁了，不知道里面发生了什么。
    *   **方案**：增加 `--shell-on-fail` 参数。如果构建失败，脚本暂停并打印 Mock Shell 进入命令（`mock -r ... --shell`），让用户进去现场排查，排查完退出后脚本再清理。

- [ ] **Simple HTTP Serve (局域网共享)**
    *   **痛点**：宿主机可以直接用 file://，但局域网其他机器想用你的包怎么办？
    *   **方案**：`lc serve --repo ./my-repo --port 8080`。
    *   **实现**：封装 Python 自带的 `http.server`，一键把仓库变成 HTTP 源。

### P2: 高级构建能力 (Advanced Build)

- [ ] **Dirty Build Mode (极速脏构建)**
    *   **痛点**：改一行代码想看效果，Mock 每次都重新初始化 chroot 还是太慢（虽然有 ccache）。
    *   **方案**：`lc build --dirty`。
    *   **实现**：不清理 Mock 的 Root，直接复用上次的环境进行增量编译（`mock --no-clean`）。这有污染风险，但对开发者调试极快。

- [ ] **Multi-Arch Support (多架构支持)**
    *   **痛点**：只能打 x86_64。
    *   **方案**：支持 `lc build --arch aarch64`。
    *   **实现**：透传参数给 Mock (`mock -r fedora-40-aarch64`)。前提是宿主机安装了 `qemu-user-static` 来支持跨架构模拟。

- [ ] **Mock Chain (依赖链构建)**
    *   **痛点**：A 依赖 B，B 依赖 C。现在得手动先编 C，再编 B...
    *   **方案**：`lc chain --list build_order.txt`。
    *   **实现**：读取一个简单的文本列表，按顺序自动执行构建，并且自动把前一个构建的产物作为 `--addrepo` 注入给下一个构建。

---

### 建议优先执行顺序

1.  **Package it into rpm**: 先给自己个名分，方便管理版本。
2.  **Add local git repo support**: 这是开发体验提升最大的点。
3.  **Global Configuration**: 解决重复输入参数的疲劳。