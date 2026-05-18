Name:           plasma-ptt
Version:        1.0
Release:        1%{?dist}
Summary:        A Wayland-compatible Push-to-Talk background daemon for KDE Plasma and PipeWire
BuildArch:      noarch

License:        GPLv3
URL:            https://github.com/fativi/plasma-ptt
Source0:        %{name}-%{version}.tar.gz

Requires:       python3-evdev
Requires:       python3-pyqt6

%description
Plasma Push-to-Talk (PTT) is a lightweight background daemon that intercepts raw hardware events directly from /dev/input/ to provide flawless, system-wide microphone muting and unmuting without relying on window focus or Wayland-restricted keyloggers.

%prep
%autosetup

%build
# Nothing to build natively

%install
rm -rf $RPM_BUILD_ROOT
make DESTDIR=$RPM_BUILD_ROOT PREFIX=/usr install

%post
echo "================================================================"
echo " You need to be in the 'input' group to read hardware events."
echo " Run: sudo usermod -aG input \$USER"
echo " Then reboot or completely log out and log back in."
echo "================================================================"
echo "To enable the service, run the following as your normal user:"
echo "systemctl --user enable --now plasma-ptt.service"

%files
/usr/bin/plasma-ptt
/usr/lib/systemd/user/plasma-ptt.service

%changelog
* Mon May 18 2026 Brian <fativi@github.com> - 1.0-1
- Initial RPM release
