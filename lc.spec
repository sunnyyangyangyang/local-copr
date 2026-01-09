Name:           lc
Version:        1.0
Release:        1%{?dist}
Summary:        Local Copr - A lightweight local RPM build system
License:        GPLv3+
URL:            https://github.com/sunnyyangyangyang/local-copr

Source0:        lc.py
Source1:        lc-add-repo.py
Source2:        lc-git.py
Source3:        lc-rebuild.py

Requires:       python3
Requires:       mock
Requires:       createrepo_c
Requires:       gnupg
Requires:       systemd
Requires:       dnf
Requires:       expect
Requires:       python3-libdnf5
BuildArch:      noarch

%description
Local Copr (lc) allows you to build, sign, and maintain local RPM repositories.

%install
install -D -m 755 %{SOURCE0} %{buildroot}%{_bindir}/lc
install -D -m 755 %{SOURCE1} %{buildroot}%{_bindir}/lc-add-repo
install -D -m 755 %{SOURCE2} %{buildroot}%{_bindir}/lc-git
install -D -m 755 %{SOURCE3} %{buildroot}%{_bindir}/lc-rebuild

%files
%{_bindir}/lc
%{_bindir}/lc-add-repo
%{_bindir}/lc-git
%{_bindir}/lc-rebuild

%changelog
* Thu Jan 08 2026 Yuanxi Yang <yxh9956@gmail.com> - 0.1.0-1
- Initial self-hosted package