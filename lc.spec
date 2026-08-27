Name:           lc
Version:        2.1
Release:        3%{?dist}
Summary:        Local Copr - A lightweight local RPM build system
License:        GPLv3+
URL:            https://github.com/sunnyyangyangyang/local-copr

Source0:        lc.py
Source1:        lc-add-repo.py
Source2:        tmpfs_tmponly.py
Source3:        lc-bash-completion

BuildRequires:  python3-devel
Requires:       python3
Suggests:       bash-completion
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
# Install bash completion (loaded on demand by the bash-completion package)
install -D -m 644 %{SOURCE3} %{buildroot}%{_datadir}/bash-completion/completions/lc
install -D -m 644 %{SOURCE3} %{buildroot}%{_datadir}/bash-completion/completions/lc-add-repo

%files
%{_bindir}/lc
%{_bindir}/lc-add-repo
%{_datadir}/bash-completion/completions/lc
%{_datadir}/bash-completion/completions/lc-add-repo
%{python3_sitelib}/mockbuild/plugins/tmpfs_tmponly.py
%{python3_sitelib}/mockbuild/plugins/__pycache__/tmpfs_tmponly.*.py*

%changelog
* Wed Aug 27 2026 Yuanxi Yang <yxh9956@gmail.com> - 2.1-3
- Fix bash completion dying at value positions (--torepo, after store_true flags)
- Complete --source/--torepo as directories; free-form values fall back to bash default completion
- lc-add-repo refresh now completes its repo-path argument

* Mon Aug 17 2026 Yuanxi Yang <yxh9956@gmail.com> - 2.1-2
- Add bash tab completion for lc and lc-add-repo (fixes #4)

* Fri Jul 31 2026 Yuanxi Yang <yxh9956@gmail.com> - 2.1-1
- Allow building directly from --spec without requiring --source

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
