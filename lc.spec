Name:           lc
Version:        2.1
Release:        1%{?dist}
Summary:        Local Copr - A lightweight local RPM build system
License:        GPLv3+
URL:            https://github.com/sunnyyangyangyang/local-copr

Source0:        lc.py
Source1:        lc-add-repo.py
Source2:        tmpfs_tmponly.py

BuildRequires:  python3-devel
Requires:       python3
Requires:       mock
Requires:       createrepo_c
Requires:       gnupg
Requires:       systemd
Requires:       dnf
Requires:       expect
Requires:       rpmdevtools
Requires:       rpm-sign
BuildArch:      noarch

%description
Local Copr (lc) allows you to build, sign, and maintain local RPM repositories.

%install
install -D -m 755 %{SOURCE0} %{buildroot}%{_bindir}/lc
install -D -m 755 %{SOURCE1} %{buildroot}%{_bindir}/lc-add-repo
# Install selective tmpfs plugin for mock
install -D -m 644 %{SOURCE2} %{buildroot}%{python3_sitelib}/mockbuild/plugins/tmpfs_tmponly.py

%files
%{_bindir}/lc
%{_bindir}/lc-add-repo
%{python3_sitelib}/mockbuild/plugins/tmpfs_tmponly.py
%{python3_sitelib}/mockbuild/plugins/__pycache__/tmpfs_tmponly.*.py*

%changelog
* Mon Jul 20 2026 Yuanxi Yang <yxh9956@gmail.com> - 2.0-1
- Remove lc-rebuild and lc-git tools (chain/rebuild/git features)
- Simplify CLI: --source is now required for build
- Add lc-add-repo refresh subcommand for repo metadata update

* Sat May 30 2026 Yuanxi Yang <yxh9956@gmail.com> - 1.6-1
- Fix chain mode: replace sys.exit with exception for proper error handling
- Fix bare except swallowing KeyboardInterrupt
* Sat May 30 2026 Yuanxi Yang <yxh9956@gmail.com> - 1.5-1
- Add --extra-mock-args to pass args directly to mock
- Merge --use-ssd/--use-tmp-ssd into --storage with choices: tmpfs, tmpfs-tmponly, ssd

* Thu Jan 08 2026 Yuanxi Yang <yxh9956@gmail.com> - 0.1.0-1
- Initial self-hosted package
