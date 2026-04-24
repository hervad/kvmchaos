Name:           kvmchaos
Version:        0.18.0
Release:        1%{?dist}
Summary:        KVM chaos engineering CLI
License:        MIT
BuildArch:      x86_64

Source0:        kvmchaos

Requires:       libvirt-libs

%description
kvmchaos injects and reverts KVM faults (vm.pause, net.latency, disk.latency,
clock.skew, and others) against KVM VMs via libvirt. Supports declarative
multi-step experiments, structured JSON event logging, safety allowlist,
and rate limiting. Targets RHEL 9 KVM hosts.

%install
install -Dm755 %{SOURCE0} %{buildroot}%{_bindir}/kvmchaos

%files
%{_bindir}/kvmchaos

%changelog
* Thu Apr 24 2026 Vadym Herman <vadymherman@gmail.com> - 0.18.0-1
- Initial RPM packaging with self-contained PyInstaller binary.
