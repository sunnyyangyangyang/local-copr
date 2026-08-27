# Local Copr (lc)

A lightweight, secure local RPM build system for Fedora/RHEL-based distributions. Build and manage your own RPM repositories without needing Copr infrastructure.

This tool was developed with help of AI.

## Features

- 🏗️ **Local RPM Building** - Build RPMs in isolated mock environments
- 🔐 **GPG Signing Support** - Optional package and repository signing
- 🛡️ **Resource Control** - Memory and CPU limits for safe builds
- 🌐 **Network Isolation** - Offline builds by default
- 📦 **Repository Management** - Create and maintain local yum/dnf repositories
- ⚙️ **Configuration per Package** - JSON config files for package-specific build options
- 🔧 **Zero-Config** - Works out of the box with sensible defaults

## Architecture

Local Copr consists of two tools with clear separation of duties:

- **`lc`** - Main build tool (runs as regular user)
  - Automatic version bumping for incremental builds
  - Multiple storage backends (tmpfs, SSD, hybrid tmpfs)
  - Package-specific configuration via conf.json

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
sudo dnf install mock createrepo_c rpm-build rpmdevtools spectool expect systemd
```

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
sudo cp lc-add-repo /usr/local/bin/
sudo chmod +x /usr/local/bin/lc /usr/local/bin/lc-add-repo
```

**Note:** Manual installation is not recommended for production use. Use the official RPM package instead.

### Bash Completion

The RPM package installs bash tab completion for `lc` and `lc-add-repo` (requires the `bash-completion` package). It completes subcommands, options, and option values (`--source`/`--torepo` → directories, `--spec`/`--conf` → files, `--storage` → backends) automatically in a new shell session; free-form values fall back to bash's default completion.

For manual installations, source it yourself:

```bash
source /path/to/lc-bash-completion   # or add to ~/.bashrc
```

## Quick Start

### 1. Create a Local Repository

```bash
# Without GPG signing
lc init --repo ~/my-rpms

# With GPG signing (recommended)  
lc init --repo ~/my-rpms --gpg-key YOUR_GPG_KEY_ID
```

### 2. Build a Package

```bash
lc build --source /path/to/package-source --torepo ~/my-rpms
```

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
lc init --repo <path> [--gpg-key <key-id>]
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

### Configuration per Package (`conf.json`)

Create `conf.json` (or specify via `--conf`) for package-specific build options. Default location: `<repo>/forges/conf.json`.

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

#### Refresh Repository Metadata

```bash
lc-add-repo refresh <repo-path>
```
Updates repository metadata with `createrepo_c --update --no-database` and re-signs repodata if GPG is configured. Useful after manually adding RPMs to a repo directory.

#### List Local Copr Repositories

```bash
lc-add-repo list
```
Lists all Local Copr repositories in the system.

## Advanced Usage

### GPG Signing Workflow

1.  **Initialize**: `lc init --repo ~/secure-rpms --gpg-key YOUR_KEY_ID`

2.  **Build**: Build packages as usual. RPMs and repodata will be automatically signed upon completion.

### Version Management

Local Copr automatically appends timestamp-based patches to ensure monotonic versioning:

```
Release: 1%{?dist}     → Release: 1.p1704895000%{?dist}
```

This ensures builds are always incremental and uniquely identifiable.

## Directory Structure

```bash
~/my-rpms/
├── .lc_config              # Repository configuration (GPG key, etc.)
├── .build_logs/            # Build logs (archived as tar.gz)
│   └── package-20260107-123456.tar.gz
├── RPM-GPG-KEY-local       # Public GPG key (if enabled)
├── local.repo              # Repo config template for dnf/yum
├── repodata/               # YUM/DNF metadata
└── *.rpm                   # Built packages
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
- **Build process (`lc`)** runs as regular user.
- **System integration (`lc-add-repo`)** requires sudo only when needed.

### Network Isolation
- Builds run **offline by default** for security and reproducibility.
- To enable network, specify `--enable-network`.

### Sandboxing
- All builds run in isolated mock chroots
- Filesystem isolation prevents cross-contamination
- Resource limits prevent DoS conditions

## Troubleshooting

### Build Failures

**Check build logs:**
```bash
tar -xzf ~/my-rpms/.build_logs/package-*.tar.gz
less build-log/build.log
```

**Common Issues:**
- **Memory errors:** Use `--use-tmp-ssd` or increase system RAM
- **Missing dependencies:** Enable network with `--enable-network`
- **Permission denied:** Ensure user is in mock group: `sudo usermod -aG mock $USER`

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
- **spectool** - Source tarball download for spec files

### Contributing

Issues and pull requests welcome at https://github.com/sunnyyangyangyang/local-copr
