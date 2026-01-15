# Local Copr (lc)

A lightweight, secure local RPM build system for Fedora/RHEL-based distributions. Build and manage your own RPM repositories without needing Copr infrastructure.

## Features

- 🏗️ **Local RPM Building** - Build RPMs in isolated mock environments
- 🔁 **Git Automation** - **Push-to-Build** workflow via `lc-git` hooks  
- 🔐 **GPG Signing Support** - Optional package and repository signing
- 🛡️ **Resource Control** - Memory and CPU limits for safe builds
- 🌐 **Network Isolation** - Offline builds by default
- 📦 **Repository Management** - Create and maintain local yum/dnf repositories
- 🔗 **Auto-Rebuild Planner** - Intelligent dependency-based rebuild chains via `lc-rebuild`
- ⚙️ **Configuration per Package** - JSON config files for package-specific build options
- 🔧 **Zero-Config** - Works out of the box with sensible defaults

## Architecture

Local Copr consists of four tools with clear separation of duties:

- **`lc`** - Main build tool (runs as regular user)
  - Supports manual builds, chain builds via JSON plans
  - Automatic version bumping for incremental builds
  - Multiple storage backends (tmpfs, SSD, hybrid tmpfs)

- **`lc-git`** - Git integration manager (manages local forges and build triggers)  
  - Creates "forges" (git repositories) inside your RPM repository
  - Push-to-build workflow with automatic hook installation
  - Supports both local repos and remote cloning

- **`lc-rebuild`** - Dependency planning tool using libdnf5
  - Analyzes package dependencies for rebuild orchestration  
  - Generates build plans that respect dependency chains
  - Integrates with conf.json for per-package configuration

- **`lc-add-repo`** - System integration tool (requires sudo)
  - Adds local repositories to system package manager
  - Handles GPG key import and repository registration
  - Manages repo files in /etc/yum.repos.d/

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
sudo dnf install mock createrepo_c rpm-build rpmdevtools spectool expect git python3-libdnf5 systemd
```

The `lc-rebuild` tool requires `python3-libdnf5` for dependency resolution.

**Important:** Add your user to the mock group for build permissions:

```bash
sudo usermod -aG mock $USER
newgrp mock
```
> **Note:** This is required even when installing from Copr, as the build tools need mock access.

#### Manual Installation Steps

```bash
# Temporary manual installation (use at your own risk)
sudo cp lc /usr/local/bin/
sudo cp lc-git /usr/local/bin/  
sudo cp lc-add-repo /usr/local/bin/
sudo chmod +x /usr/local/bin/lc /usr/local/bin/lc-git /usr/local/bin/lc-add-repo
```

**Note:** Manual installation is not recommended for production use. Use the official RPM package instead.

## Quick Start

### 1. Create a Local Repository

```bash
# Without GPG signing
lc init --repo ~/my-rpms

# With GPG signing (recommended)  
lc init --repo ~/my-rpms --gpg-key YOUR_GPG_KEY_ID

# Enable auto-rebuild feature for dependency chains
lc init --repo ~/my-rpms --enable-rebuild
```

### 2. Automate with Git (Push-to-Build)

Instead of manually building, create a managed git repo inside your RPM repository:

```bash
# Create a "forge" for your package
lc-git create my-package --repo ~/my-rpms

# Or clone from an existing remote (e.g., GitHub)
lc-git create --remote https://github.com/user/repo.git --repo ~/my-rpms
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
sudo dnf makecache
sudo dnf install your-package-name
```

## Usage Guide

### `lc` - Build Tool Commands

#### Initialize Repository

```bash
lc init --repo <path> [--gpg-key <key-id>] [--enable-rebuild]
```

#### Manual Build Package

```bash  
lc build --source <path> --torepo <repo> [options]
```

**Options:**
- `--source` - Source directory containing spec file and sources
- `--torepo` - Target repository path
- `--spec` - Specific spec file (defaults to first .spec found)
- `--jobs` - Limit CPU cores (e.g., `--jobs 4`)
- `--max-mem` - Limit memory usage (e.g., `--max-mem 4G`) using systemd-run
- `--enable-network` - Allow network access during build (default: offline)
- `--use-ssd` - Build on SSD instead of tmpfs for lower memory usage
- `--use-tmp-ssd` - Use selective tmpfs (only `/tmp` on RAM, other operations on SSD) 
- `--chain` - Execute rebuild plan from JSON file
- `--conf` - Path to package-specific configuration file
- `--addrepo` - Add external repositories for dependency resolution

### Storage Options Comparison

Choose the right storage option based on your system resources and needs:

| Option | Description | Memory Usage | Performance | Best For |
|--------|-------------|--------------|-------------|----------|
| Default (tmpfs) | Full build environment in RAM | High (~2GB+ free memory) | Fastest | Systems with abundant RAM |
| `--use-ssd` | All operations on SSD/HDD | Low | Slower | Limited RAM or large builds |
| `--use-tmp-ssd` - Use selective tmpfs (only `/tmp` directory in RAM, rest on disk) | Medium (~512MB+ free memory) | Balanced | **Recommended for most systems** |

The selective tmpfs option (`--use-tmp-ssd`) provides the best balance - critical temporary files are stored in fast RAM while other build artifacts use your SSD/HDD storage. It automatically checks system RAM (requires 4GB minimum).

### `lc-git` - Git Automation Commands

Manage "forges" (git repositories) inside your RPM repository. Pushing to—or modifying—these repositories automatically triggers `lc build`.

#### Create a Git Forge

**Option 1: Initialize a new empty repository**
```bash
lc-git create <package-name> --repo <repo-path>
```
Creates a bare-bones git repository at `<repo-path>/forges/<package-name>`.

**Option 2: Clone from an existing remote (e.g., GitHub)**
```bash  
lc-git create --remote <git-url> --repo <repo-path> [package-name]
```
Clones an upstream repository into your local forge.
- **Auto-naming:** If `[package-name]` is omitted, the name is derived from the URL (e.g., `user/repo.git` becomes `repo`).
- **Triggers:** Configured to trigger builds on **push** (post-receive), **local commit** (post-commit), and **pull/merge** (post-merge). This is ideal for mirroring upstream packages or developing locally.

#### List Packages

```bash
lc-git list --repo <repo-path>
```
Lists all git packages currently managed in the repository. Shows status of conf.json configuration file.

#### Delete a Git Forge

```bash  
lc-git delete <package-name> --repo <repo-path>
```
Removes the git repository from the `forges` directory (does not delete built RPMs).

### `lc-rebuild` - Dependency Planning Tool  

The dependency planner analyzes package interdependencies and generates rebuild plans for library updates. It uses libdnf5 to resolve dependencies and creates JSON build chains.

#### Generate Rebuild Plan

```bash
lc-rebuild --repo <path> --trigger <package-name> --output plan.json
```

**Options:**
- `--addrepo` - Additional repositories for dependency resolution (can be specified multiple times)
- `--conf` - Path to conf.json file with package-specific configurations  
- `--verbose` - Enable debug logging

#### Execute Rebuild Chain

When auto-rebuild is enabled, `lc-git` hooks automatically generate and execute rebuild plans:

```bash
# The hook runs this internally when auto-rebuild is enabled:
lc-rebuild --trigger <package-name> --output plan.json && lc build --chain plan.json
```

### Configuration per Package (`conf.json`)

Create `/path/to/forges/conf.json` for package-specific build options:

```json
{
  "torch": {
    "max_mem": "50G",
    "enable_network": true,
    "addrepo": [
      "https://developer.download.nvidia.com/compute/cuda/repos/rhel10/x86_64/",
      "https://download.copr.fedorainfracloud.org/results/rezso/ML/fedora-43-x86_64/"
    ]
  },
  "vision": {
    "max_mem": "50G",
    "enable_network": true,
    "addrepo": [
      "https://developer.download.nvidia.com/compute/cuda/repos/rhel10/x86_64/",
      "https://download.copr.fedorainfracloud.org/results/rezso/ML/fedora-43-x86_64/"
    ]
  }
}
```

### `lc-add-repo` - System Integration Commands

#### Add Repository to System

```bash  
sudo lc-add-repo add <repo-path> [--name custom-name] [--force] [--no-refresh]
```

Options:
- `--name` - Custom repository name (default: directory name)
- `--force` - Overwrite existing repo file
- `--no-refresh` - Skip cache refresh

#### Remove Repository from System

```bash  
sudo lc-add-repo remove <repo-name>
```

#### List Local Copr Repositories

```bash
lc-add-repo list
```
Lists all Local Copr repositories in the system.

## Advanced Usage

### The Git Workflow (Detailed)

`lc-git` creates a **Serverless CI/CD** experience using the filesystem hooks.

1.  **Create**: `lc-git create tool-x --repo ~/repos/main`
2.  **Push**: When you push to this repo, the `post-receive` hook:
    *   Resets the repo's working tree to your commit (`git reset --hard`).
    *   Triggers `lc build` in the background (detached process).
    *   Redirects output to a timestamped log file.
3.  **Feedback**: Your terminal immediately shows the log path:
    ```text
    remote: [LC] 📥 Push received (abc123def). Log: /home/user/repos/main/.build_logs/tool-x-20260108-120000-a1b2c3d.log
    remote: [LC] Task submitted (PID: 12345).
    ```
4.  **Monitor**: Watch the build live:
    ```bash  
    tail -f ~/repos/main/.build_logs/tool-x-SUCCESS-20260108-120000-a1b2c3d.log
    ```

### Auto-Rebuild Workflow

When `--enable-rebuild` is enabled during repo initialization:

1. **Create**: Initialize with rebuild support:
   ```bash
   lc init --repo ~/my-rpms --enable-rebuild
   ```

2. **Configure**: Create `/path/to/forges/conf.json` to define dependency relationships.

3. **Trigger**: When a package is updated via git push, the hook automatically:
   
   - Analyzes dependencies with `lc-rebuild`
   - Generates rebuild plan respecting dependency chains  
   - Executes full rebuild sequence if needed

### GPG Signing Workflow

1.  **Initialize**: `lc init --repo ~/secure-rpms --gpg-key YOUR_KEY_ID`

2.  **Git Trigger**: `lc-git create my-app --repo ~/secure-rpms`  

3.  **Push**: `git push local main`
    *   The background build will automatically sign the RPMs and repodata upon completion.

### Version Management

Local Copr automatically appends timestamp-based patches to ensure monotonic versioning:

```
Release: 1%{?dist}     → Release: 1.p1704895000%{?dist}
```

This ensures builds are always incremental and uniquely identifiable.

## Directory Structure

```bash
~/my-rpms/
├── .lc_config              # Repository configuration (auto-rebuild settings)
├── .build_logs/            # Build logs (Live & Archived)
│   ├── tool-x-SUCCESS-20260108-120000-a1b2c3d.log  # Real-time log from git push
│   └── package-20260107-123456.tar.gz
├── RPM-GPG-KEY-local       # Public GPG key (if enabled)  
├── local.repo              # Repo config template for dnf/yum
├── repodata/               # YUM/DNF metadata
├── x86_64/                 # Built packages (.rpm files)
└── forges/                 # <--- Managed Git Repositories
    ├── conf.json           # Package-specific build configuration  
    ├── my-package/         # Normal git repo with spec/source
    │   ├── .git/
    │   ├── my-package.spec
    │   └── src/
    ├── pytorch/            # Example: Complex multi-package project
    │   ├── .git/
    │   ├── pytorch.spec    
    │   └── patches/
    └── another-tool/
```

## Performance Features

### Selective Tmpfs Plugin

The `tmpfs_tmponly.py` plugin provides optimized storage by mounting only `/tmp` on tmpfs while keeping other directories on SSD. This reduces memory usage by ~60% compared to full tmpfs while maintaining good performance.

**Requirements:** At least 4GB of system RAM
**Benefits:**
- Lower memory footprint than default tmpfs  
- Better for systems with limited RAM (2-4GB)
- Still fast build performance due to /tmp on SSD

### Resource Limits

Set CPU and memory limits to prevent builds from consuming excessive resources:

```bash
# Limit to 4 cores, 4GB memory 
lc build --jobs 4 --max-mem 4G --source my-package --torepo ~/repos/
```

## Security Features

### Privilege Separation
- **Build process (`lc`, `lc-git`)** runs as regular user.
- **System integration (`lc-add-repo`)** requires sudo only when needed.

### Network Isolation  
- Builds run **offline by default** for security and reproducibility.
- Git builds inherit this default. To enable network, specify `--enable-network`.

### Sandboxing
- All builds run in isolated mock chroots
- Filesystem isolation prevents cross-contamination
- Resource limits prevent DoS conditions

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

**Common Issues:**
- **Memory errors:** Use `--use-tmp-ssd` or increase system RAM
- **Missing dependencies:** Enable network with `--enable-network`
- **Permission denied:** Ensure user is in mock group: `sudo usermod -aG mock $USER`

### Dependency Resolution

**lc-rebuild requires python3-libdnf5:**
```bash  
sudo dnf install python3-libdnf5
```

**Rebuild plan generation fails:**
Check that conf.json keys match actual forge directory names.

## License

GNU General Public License v3.0 or later

Copyright (C) 2026 Yuanxi (Sunny) Yang

## Author

Yuanxi (Sunny) Yang <yxh9956@gmail.com>

---

**Note:** Local Copr is designed for personal and development use. For public package distribution, consider using [Fedora Copr](https://copr.fedorainfracloud.org/).

### Related Tools

- **mockbuild** - Base build system used by lc
- **createrepo_c** - Repository metadata generation  
- **systemd-run** - Resource limiting for builds (when --max-mem is used)
- **libdnf5** - Dependency resolution engine for lc-rebuild

### Contributing

Issues and pull requests welcome at https://github.com/sunnyyangyangyang/local-copr
