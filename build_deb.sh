#!/usr/bin/env bash

# Build a simple .deb package using dpkg-deb

PKG_NAME="plasma-ptt"
VERSION=$(grep -m1 '__version__' plasma-ptt.py | cut -d'"' -f2)
if [ -z "$VERSION" ]; then
    VERSION="1.0.0"
fi
ARCH="all"
DEB_DIR="${PKG_NAME}_${VERSION}_${ARCH}"

echo "=== Building Debian Package for $PKG_NAME ==="

# 1. Create directory structure
mkdir -p "$DEB_DIR/DEBIAN"

# 2. Build the debian control file
cat <<EOF > "$DEB_DIR/DEBIAN/control"
Package: $PKG_NAME
Version: $VERSION
Architecture: $ARCH
Maintainer: Brian (fativi)
Depends: python3-evdev, python3-pyqt6
Description: A Wayland-compatible Push-to-Talk background daemon designed for KDE Plasma and PipeWire.
 It intercepts raw hardware events directly from /dev/input/ to provide flawless, system-wide microphone muting and unmuting without relying on window focus or Wayland-restricted keyloggers.
EOF

# 3. Create postinst script to inform the user about the input group
cat <<'EOF' > "$DEB_DIR/DEBIAN/postinst"
#!/bin/sh
set -e
if ! groups "$SUDO_USER" | grep -q "\binput\b"; then
    echo "================================================================"
    echo " You need to be in the 'input' group to read hardware events."
    echo " Run: sudo usermod -aG input \$USER"
    echo " Then reboot or completely log out and log back in."
    echo "================================================================"
fi
# Start or reload systemd user configuration
# User-level systemd services need to be enabled per-user, so we just prompt them.
echo "To enable the service, run the following as your normal user:"
echo "systemctl --user enable --now plasma-ptt.service"
EOF
chmod 755 "$DEB_DIR/DEBIAN/postinst"

# 4. Use the Makefile to install files into the DEB_DIR
make DESTDIR="$PWD/$DEB_DIR" PREFIX=/usr install

# 5. Build the .deb
dpkg-deb --build "$DEB_DIR"

# 6. Cleanup
rm -rf "$DEB_DIR"

echo "=== Success! Debian package created: ${DEB_DIR}.deb ==="
