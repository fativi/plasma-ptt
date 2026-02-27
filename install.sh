#!/usr/bin/env bash

echo "=== Plasma Push-to-Talk Installer ==="

# 1. Verify files exist in the current directory
for file in plasma-ptt.py plasma-ptt.service plasma-ptt-setup.desktop; do
    if [ ! -f "$file" ]; then
        echo "Error: $file not found in the current directory."
        exit 1
    fi
done

# 2. Detect Package Manager and Install Dependencies
echo "-> Checking and installing dependencies..."
if command -v pacman &> /dev/null; then
    echo "   Arch/CachyOS detected (pacman)."
    if ! pacman -Qs python-evdev > /dev/null || ! pacman -Qs python-pyqt6 > /dev/null; then
        sudo pacman -S --needed python-evdev python-pyqt6
    else
        echo "   Dependencies already met."
    fi
elif command -v apt-get &> /dev/null; then
    echo "   Debian/Pop!_OS/Ubuntu detected (apt)."
    sudo apt-get update
    sudo apt-get install -y python3-evdev python3-pyqt6
elif command -v dnf &> /dev/null; then
    echo "   Fedora detected (dnf)."
    sudo dnf install -y python3-evdev python3-pyqt6
else
    echo "   Error: Unsupported package manager. Please install the evdev and PyQt6 Python packages manually."
    exit 1
fi

# 3. Verify 'input' group membership
echo "-> Checking input group permissions..."
GROUP_CHANGED=false
if ! groups "$USER" | grep -q "\binput\b"; then
    echo "   Adding $USER to the 'input' group..."
    sudo usermod -aG input "$USER"
    GROUP_CHANGED=true
else
    echo "   User is already in the 'input' group."
fi

# 4. Create directories and copy files
echo "-> Creating directories and copying files..."
mkdir -p ~/.local/bin
mkdir -p ~/.config/systemd/user
mkdir -p ~/.local/share/applications
mkdir -p ~/.config/plasma-ptt/sounds

cp plasma-ptt.py ~/.local/bin/
chmod +x ~/.local/bin/plasma-ptt.py

cp plasma-ptt.service ~/.config/systemd/user/
cp plasma-ptt-setup.desktop ~/.local/share/applications/

# Update the desktop database so the DE sees the new app launcher immediately
update-desktop-database ~/.local/share/applications/ 2>/dev/null || true

# 5. Generate default PTT chirps if missing and ffmpeg is available
echo "-> Checking for PTT audio chirps..."
SOUND_DIR=~/.config/plasma-ptt/sounds
if command -v ffmpeg &> /dev/null; then
    if [ ! -f "$SOUND_DIR/ptt_open.wav" ]; then
        echo "   Generating default ptt_open.wav..."
        ffmpeg -f lavfi -i "sine=frequency=1000:duration=0.1" "$SOUND_DIR/ptt_open.wav" -loglevel quiet
    fi
    if [ ! -f "$SOUND_DIR/ptt_close.wav" ]; then
        echo "   Generating default ptt_close.wav..."
        ffmpeg -f lavfi -i "sine=frequency=400:duration=0.1" "$SOUND_DIR/ptt_close.wav" -loglevel quiet
    fi
else
    echo "   ffmpeg not found. Skipping default chirp generation."
    echo "   (You can manually drop ptt_open.wav and ptt_close.wav into ~/.config/plasma-ptt/sounds/)"
fi

# 6. Run initial setup if no config exists
if [ ! -f ~/.config/plasma-ptt/config.json ]; then
    echo "-> No configuration found. Launching initial setup..."
    ~/.local/bin/plasma-ptt.py --setup
fi

# 7. Enable and start systemd service
echo "-> Configuring systemd background service..."
systemctl --user daemon-reload
systemctl --user enable plasma-ptt.service

if [ "$GROUP_CHANGED" = true ]; then
    echo ""
    echo "=================================================================="
    echo " WARNING: You were just added to the 'input' group."
    echo " The background service will NOT start successfully right now."
    echo " Please log out of your desktop session completely and log back in."
    echo "=================================================================="
else
    systemctl --user restart plasma-ptt.service
    echo "-> Service started successfully!"
    echo "=== Installation Complete ==="
fi
