# Local Copr (lc)

A lightweight, secure local RPM build system for Fedora/RHEL-based distributions. Build and manage your own RPM repositories without needing Copr infrastructure.

## Features

- 🏗️ **Local RPM Building** - Build RPMs in isolated mock environments
- 🔄 **Git Automation** - **Push-to-Build** workflow via `lc-git` hooks
- 🔐 **GPG Signing Support** - Optional package and repository signing
- 🛡️ **Resource Control** - Memory and CPU limits for safe builds
- 🌐 **Network Isolation** - Offline builds by default
- 📦 **Repository Management** - Create and maintain local yum/dnf repositories
- 🔧 **Zero-Config** - Works out of the box with sensible defaults

## Architecture

Local Copr consists of four tools with clear separation of duties:

- **`lc`** - Main build tool (runs as regular user)
- **`lc-git`** - Git integration manager (manages local forges and build triggers)  
- **`lc-rebuild`** - Dependency planner for rebuild orchestration
- **`lc-add-repo`** - System integration tool (requires sudo)

## Installation

### Install Local Copr

**Recommended:** Install from official repositories:

```bash
# Install the stable release from Copr (recommended)
sudo dnf copr enable sunnyyang/local-copr
sudo dnf install lc
```

> **Official repository:** https://copr.fedorainfracloud.org/coprs/sunnyyang/local-copr/

### Manual Installation (Legacy)

For development/testing purposes only, you can manually copy the scripts:

#### Prerequisites

```bash
sudo dnf install mock createrepo_c rpm-build rpmdevtools spectool expect git python3-libdnf5
```

The `lc-rebuild` tool requires `python3-libdnf5` for dependency resolution.


```bash
# Temporary manual installation (use at your own risk)
sudo cp lc /usr/local/bin/
sudo cp lc-git /usr/local/bin/
sudo cp lc-add-repo /usr/local/bin/
sudo chmod +x /usr/local/bin/lc /usr/local/bin/lc-git /usr/local/bin/lc-add-repo

# Add your user to mock group
sudo usermod -aG mock $USER
newgrp mock
```

**Note:** Manual installation is not recommended for production use. Use the official RPM package instead.

## Quick Start

### 1. Create a Local Repository

```bash
# Without GPG signing
lc init --repo ~/my-rpms

# With GPG signing (recommended)
lc init --repo ~/my-rpms --gpg-key YOUR_GPG_KEY_ID
```

### 2. Automate with Git (Push-to-Build)

Instead of manually building, create a managed git repo inside your RPM repository:

```bash
# Create a "forge" for your package
lc-git create my-package --repo ~/my-rpms
```

Then, in your source code directory:

```bash
# Add the local forge as a remote
git remote add local ~/my-rpms/forges/my-package

# Push to trigger build!
git push local main
```

*The build runs in the background. You will see a log file path in your terminal to track progress.*

### 3. Add Repository to System

```bash
# Install to system (requires sudo)
sudo lc-add-repo add ~/my-rpms

# Refresh cache and install packages
sudo dnf install your-package-name
```

## Usage Guide

### `lc` - Build Tool Commands

#### Initialize Repository

```bash
lc init --repo <path> [--gpg-key <key-id>]
```

#### Manual Build Package

```bash
lc build --source <path> --torepo <repo> [options]
```

**Options:**
- `--source` - Source directory containing spec file and sources
- `--torepo` - Target repository path
- `--jobs` - Limit CPU cores (e.g., `--jobs 4`)
- `--max-mem` - Limit memory usage (e.g., `--max-mem 4G`)
- `--enable-network` - Allow network access during build
- `--use-ssd` - Build on SSD instead of tmpfs

### `lc-git` - Git Automation Commands

Manage "forges" (git repositories) inside your RPM repository. Pushing to these repositories automatically triggers `lc build`.

#### Create a Git Forge

```bash
lc-git create <package-name> --repo <repo-path>
```
Creates a standard git repository at `<repo-path>/forges/<package-name>` with a pre-configured hook.

#### List Packages

```bash
lc-git list --repo <repo-path>
```
Lists all git packages currently managed in the repository.

#### Delete a Git Forge

```bash
lc-git delete <package-name> --repo <repo-path>
```
Removes the git repository from the `forges` directory (does not delete built RPMs).

### `lc-rebuild` - Dependency Planning Tool

Automatically analyzes package dependencies and generates rebuild plans for library updates.

The tool is integrated into `lc init --enable-rebuild` and works seamlessly with the git automation workflow.

### `lc-add-repo` - System Integration Commands

#### Add/Remove Repository to System

```bash
sudo lc-add-repo add <repo-path> [--name custom-name]
sudo lc-add-repo remove <repo-name>
```

## Advanced Usage

### The Git Workflow (Detailed)

`lc-git` creates a **Serverless CI/CD** experience using the filesystem.

1.  **Create**: `lc-git create tool-x --repo ~/repos/main`
2.  **Push**: When you push to this repo, the `post-receive` hook:
    *   Resets the repo's working tree to your commit (`git reset --hard`).
    *   Triggers `lc build` in the background (detached process).
    *   Redirects output to a timestamped log file.
3.  **Feedback**: Your terminal immediately shows the log path:
    ```text
    remote: [LC] Build triggered in background (PID: 12345).
    remote: [LC] Live Log: /home/user/repos/main/.build_logs/20260108-120000-abc1234.log
    ```
4.  **Monitor**: Watch the build live:
    ```bash
    tail -f /home/user/repos/main/.build_logs/20260108-120000-abc1234.log
    ```

### GPG Signing Workflow

1.  **Initialize**: `lc init --repo ~/secure-rpms --gpg-key YOUR_KEY_ID`
2.  **Git Trigger**: `lc-git create my-app --repo ~/secure-rpms`
3.  **Push**: `git push local main`
    *   The background build will automatically sign the RPMs and the repodata upon completion.

## Directory Structure

```
~/my-rpms/
├── .lc_config              # Repository configuration
├── .build_logs/            # Build logs (Live & Archived)
│   ├── 20260108-100000-a1b2c3d.log  # Real-time log from git push
│   └── package-20260107-123456.tar.gz
├── RPM-GPG-KEY-local       # Public GPG key
├── local.repo              # Repo config template
├── repodata/               # YUM/DNF metadata
├── x86_64/                 # Built packages
└── forges/                 # <--- Managed Git Repositories
    ├── my-package/         # Normal git repo
    │   ├── .git/
    │   ├── my-package.spec
    │   └── src/
    └── another-tool/
```

## Security Features

### Privilege Separation
- **Build process (`lc`, `lc-git`)** runs as regular user.
- **System integration (`lc-add-repo`)** requires sudo only when needed.

### Network Isolation
- Builds run **offline by default**.
- Git builds inherit this default. To enable network for git builds, modify the hook or update `lc` defaults (customization via `.lc_config` coming soon).

## Troubleshooting

### Git Build Issues

**"remote: [LC] Live Log: ..." but nothing happens?**
Check the log file mentioned. If the log file is empty or missing, check if `lc` is in your PATH for non-interactive shells.

**"push works but files are empty?"**
`lc-git` uses `git reset --hard` to synchronize files. Ensure you are pushing to a branch, and the repo was created correctly with `lc-git`.

### Build Failures

**Check build logs:**
```bash
# For git builds, check the .log file directly
cat ~/my-rpms/.build_logs/DATE-TIME-COMMIT.log

# For manual builds, check the tarball
tar -xzf ~/my-rpms/.build_logs/package-*.tar.gz
less build-log/build.log
```

## License

GNU General Public License v3.0 or later

Copyright (C) 2026 Yuanxi (Sunny) Yang

## Author

Yuanxi (Sunny) Yang

---

**Note:** Local Copr is designed for personal and development use. For public package distribution, consider using [Fedora Copr](https://copr.fedorainfracloud.org/).
