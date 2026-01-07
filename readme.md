# Local Copr (lc)

A lightweight, secure local RPM build system for Fedora/RHEL-based distributions. Build and manage your own RPM repositories without needing Copr infrastructure.

## Features

- 🏗️ **Local RPM Building** - Build RPMs in isolated mock environments
- 🔐 **GPG Signing Support** - Optional package and repository signing
- 🛡️ **Resource Control** - Memory and CPU limits for safe builds
- 🌐 **Network Isolation** - Offline builds by default
- 📦 **Repository Management** - Create and maintain local yum/dnf repositories
- 🔧 **Zero-Config** - Works out of the box with sensible defaults

## Architecture

Local Copr consists of two tools with clear separation of privileges:

- **`lc`** - Main build tool (runs as regular user)
- **`lc-add-repo`** - System integration tool (requires sudo)

## Installation

### Prerequisites

```bash
sudo dnf install mock createrepo_c rpm-build rpmdevtools spectool
```

### Install Local Copr

> ⚠️ **Warning:** Manual installation to `/usr/local/bin/` is not recommended for production use.  
> **RPM package coming soon** for proper system integration!

For now, you can install manually:

```bash
# Temporary manual installation (use at your own risk)
sudo cp lc /usr/local/bin/
sudo cp lc-add-repo /usr/local/bin/
sudo chmod +x /usr/local/bin/lc /usr/local/bin/lc-add-repo

# Add your user to mock group
sudo usermod -aG mock $USER
newgrp mock
```

**Recommended:** Wait for the official RPM package, or build from source using the provided spec file (coming soon).

## Quick Start

### 1. Create a Local Repository

```bash
# Without GPG signing
lc init --repo ~/my-rpms

# With GPG signing (recommended)
lc init --repo ~/my-rpms --gpg-key YOUR_GPG_KEY_ID
```

### 2. Build Your First Package

```bash
# Basic build
lc build --source ~/myproject --torepo ~/my-rpms

# With custom spec file
lc build --source ~/myproject --spec ~/myproject/custom.spec --torepo ~/my-rpms

# Limit resources
lc build --source ~/myproject --torepo ~/my-rpms --jobs 4 --max-mem 4G
```

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

**Options:**
- `--repo` - Path to create repository
- `--gpg-key` - GPG key ID for signing (optional)

**Example:**
```bash
lc init --repo ~/rpmbuild/REPOS/myrepo --gpg-key 3AA5C0AD
```

#### Build Package

```bash
lc build --source <path> --torepo <repo> [options]
```

**Options:**
- `--source` - Source directory containing spec file and sources
- `--torepo` - Target repository path
- `--spec` - Custom spec file path (auto-detected if omitted)
- `--addrepo` - Additional repositories for dependencies (can be used multiple times)
- `--jobs` - Limit CPU cores (e.g., `--jobs 4`)
- `--max-mem` - Limit memory usage (e.g., `--max-mem 4G`)
- `--enable-network` - Allow network access during build (disabled by default)
- `--use-ssd` - Build on SSD instead of tmpfs

**Examples:**

```bash
# Basic build
lc build --source ~/myapp --torepo ~/my-rpms

# Resource-limited build
lc build --source ~/myapp --torepo ~/my-rpms --jobs 4 --max-mem 4G

# Build with additional repository
lc build --source ~/myapp --torepo ~/my-rpms --addrepo ~/another-repo

# Network-enabled build (for packages that download during build)
lc build --source ~/myapp --torepo ~/my-rpms --enable-network
```

#### Remove Repository

```bash
lc remove --repo <path>
```

**Safety:** Requires confirmation and blocks deletion of system directories.

### `lc-add-repo` - System Integration Commands

#### Add Repository to System

```bash
sudo lc-add-repo add <repo-path> [options]
```

**Options:**
- `--name` - Custom repository name (defaults to directory name)
- `--force` - Overwrite existing repository configuration
- `--no-refresh` - Skip dnf cache refresh

**Example:**
```bash
sudo lc-add-repo add ~/my-rpms --name myrepo
```

#### Remove Repository from System

```bash
sudo lc-add-repo remove <repo-name> [--no-refresh]
```

**Example:**
```bash
sudo lc-add-repo remove myrepo
```

#### List Installed Repositories

```bash
lc-add-repo list
```

## Advanced Usage

### GPG Signing Workflow

1. **Generate GPG key** (if you don't have one):
```bash
gpg --full-generate-key
# Select RSA, 4096 bits, no expiration
# Note your key ID: gpg --list-keys
```

2. **Initialize signed repository**:
```bash
lc init --repo ~/signed-rpms --gpg-key YOUR_KEY_ID
```

3. **Build packages** (automatically signed):
```bash
lc build --source ~/myapp --torepo ~/signed-rpms
```

4. **Add to system** (GPG key automatically imported):
```bash
sudo lc-add-repo add ~/signed-rpms
```

### Multi-Repository Dependencies

Build packages that depend on other local repositories:

```bash
lc build --source ~/app \
         --torepo ~/my-rpms \
         --addrepo ~/base-rpms \
         --addrepo ~/libs-rpms
```

### Resource Management

For large builds on systems with limited resources:

```bash
# Prevent OOM by limiting memory and cores
lc build --source ~/big-project \
         --torepo ~/my-rpms \
         --jobs 4 \
         --max-mem 4G
```

### Build with Network Access

Some packages need to download dependencies during build:

```bash
lc build --source ~/rust-app \
         --torepo ~/my-rpms \
         --enable-network
```

**⚠️ Warning:** Only use `--enable-network` for trusted sources.

## Configuration

### Environment Variables

- `LC_MOCK_CONFIG` - Override default mock configuration (default: `fedora-43-x86_64`)

```bash
export LC_MOCK_CONFIG="fedora-42-aarch64"
lc build --source ~/myapp --torepo ~/my-rpms
```

### Repository Configuration File

Each repository contains a `.lc_config` file (JSON format):

```json
{
  "gpg_key_id": "3AA5C0AD"
}
```

## Directory Structure

```
~/my-rpms/
├── .lc_config              # Repository configuration
├── .build_logs/            # Archived build logs
│   └── package-20260107-123456.tar.gz
├── RPM-GPG-KEY-local       # Public GPG key (if signing enabled)
├── local.repo              # Repository configuration template
├── repodata/               # YUM/DNF metadata
│   ├── repomd.xml
│   └── repomd.xml.asc      # Signature (if enabled)
└── *.rpm                   # Built packages
```

## Security Features

### Privilege Separation
- **Build process** runs as regular user
- **System integration** requires sudo only when needed

### Network Isolation
- Builds run **offline by default**
- Network access requires explicit `--enable-network` flag

### Resource Limits
- Optional memory caps via `--max-mem`
- CPU core limits via `--jobs`

### Package Verification
- Optional GPG signing at package level
- Optional repository metadata signing
- Automatic key import on repository installation

## Troubleshooting

### Build Failures

**Check build logs:**
```bash
ls ~/my-rpms/.build_logs/
tar -xzf ~/my-rpms/.build_logs/package-*.tar.gz
less build-log/build.log
```

**Common issues:**
- Missing BuildRequires → Check spec file dependencies
- Out of memory → Use `--max-mem` and `--jobs` flags
- Network access needed → Add `--enable-network` flag

### Mock Configuration

**List available configurations:**
```bash
ls /etc/mock/*.cfg
```

**Use different configuration:**
```bash
export LC_MOCK_CONFIG="fedora-rawhide-x86_64"
lc build --source ~/myapp --torepo ~/my-rpms
```

### GPG Issues

**Verify GPG key:**
```bash
gpg --list-keys YOUR_KEY_ID
```

**Re-export public key:**
```bash
gpg --export --armor YOUR_KEY_ID > ~/my-rpms/RPM-GPG-KEY-local
```

**Check package signature:**
```bash
rpm -K ~/my-rpms/package-1.0-1.fc43.x86_64.rpm
```

## Comparison with Copr

| Feature | Local Copr (lc) | Fedora Copr |
|---------|----------------|-------------|
| Setup | Instant | Requires account |
| Privacy | 100% local | Public/private repos |
| Network | Not required | Required |
| Storage | Your disk | Copr servers |
| Speed | Local I/O | Network dependent |
| Use case | Personal/testing | Distribution |

## Examples

### Example 1: Simple Package Build

```bash
# Setup
lc init --repo ~/rpms

# Build
cd ~/myproject
lc build --source . --torepo ~/rpms

# Install
sudo lc-add-repo add ~/rpms
sudo dnf install myproject
```

### Example 2: Signed Repository

```bash
# Create signed repo
lc init --repo ~/secure-rpms --gpg-key 3AA5C0AD

# Build multiple packages
for project in app1 app2 app3; do
  lc build --source ~/$project --torepo ~/secure-rpms
done

# Deploy to system
sudo lc-add-repo add ~/secure-rpms
```

### Example 3: Resource-Constrained Build

```bash
# Build large project with limits
lc build --source ~/chromium \
         --torepo ~/rpms \
         --jobs 4 \
         --max-mem 8G \
         --use-ssd
```

## Contributing

Contributions welcome! This is a lightweight tool designed to stay simple.

## License

GNU General Public License v3.0 or later

Copyright (C) 2026 Yuanxi (Sunny) Yang

## Author

Yuanxi (Sunny) Yang

---

**Note:** Local Copr is designed for personal and development use. For public package distribution, consider using [Fedora Copr](https://copr.fedorainfracloud.org/).