#!/usr/bin/env python3
# Copyright (C) 2026 Brian McGuire
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import sys
import json
import os
import subprocess
import signal
import socket
from pathlib import Path
import evdev

from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QAction, QPixmap, QPainter, QColor
from PyQt6.QtCore import QThread, pyqtSignal, QTimer, QSocketNotifier

# --- CONFIGURATION PATHS ---
CONFIG_DIR = Path(os.getenv('XDG_CONFIG_HOME', Path.home() / '.config')) / 'plasma-ptt'
CONFIG_FILE = CONFIG_DIR / 'config.json'

def load_config():
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            pass
    return None

def run_setup():
    """Terminal-based setup for selecting the input device."""
    print("\n--- PTT Initial Setup ---")
    by_id_dir = Path('/dev/input/by-id/')
    
    if not by_id_dir.exists():
        print("Error: /dev/input/by-id/ not found.")
        sys.exit(1)

    devices = []
    permission_errors = 0
    
    for path in by_id_dir.iterdir():
        # Skip directories if any exist here
        if not path.is_file() and not path.is_symlink():
            continue
            
        try:
            dev = evdev.InputDevice(str(path))
            devices.append((str(path), dev.name))
        except PermissionError:
            permission_errors += 1
            continue  # Skip this specific device and keep checking others
        except Exception:
            continue

    if not devices:
        if permission_errors > 0:
            print("\nPermission denied: Could not read any devices.")
            print("Troubleshooting:")
            print("1. Verify you are in the input group: 'groups $USER'")
            print("2. You MUST log out of Plasma completely and log back in for group changes to take effect.")
        else:
            print("\nNo input devices found.")
        sys.exit(1)

    for i, (path, name) in enumerate(devices):
        print(f"[{i}] {name}")

    while True:
        try:
            choice = int(input("\nSelect the device number: "))
            if 0 <= choice < len(devices):
                selected_path = devices[choice][0]
                selected_dev = evdev.InputDevice(selected_path)
                break
        except ValueError:
            pass

    print(f"\n>>> PRESS THE BUTTON ON '{selected_dev.name}' TO USE FOR PTT <<<")
    target_button = None
    for event in selected_dev.read_loop():
        if event.type == evdev.ecodes.EV_KEY and event.value == 1:
            target_button = event.code
            break

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    config_data = {'device_path': selected_path, 'button_code': target_button}
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config_data, f, indent=4)
        
    print("Configuration saved! Starting system tray app...\n")
    return config_data

# --- background thread for mouse input ---
class EvdevThread(QThread):
    pressed = pyqtSignal()
    released = pyqtSignal()

    def __init__(self, device_path, target_button):
        super().__init__()
        self.device_path = device_path
        self.target_button = target_button

    def run(self):
        try:
            device = evdev.InputDevice(self.device_path)
            for event in device.read_loop():
                if event.type == evdev.ecodes.EV_KEY and event.code == self.target_button:
                    if event.value == 1:
                        self.pressed.emit()
                    elif event.value == 0:
                        self.released.emit()
        except Exception as e:
            print(f"Input device disconnected or error: {e}")
            sys.exit(1)

# --- main application ---
class PTTApp:
    def __init__(self, config):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)

        self.ptt_enabled = True
        self.is_transmitting = False

        # Setup Tray Icon
        self.tray_icon = QSystemTrayIcon()
        self.update_icon()
        self.tray_icon.setVisible(True)

        # Build Context Menu
        self.menu = QMenu()
        
        self.toggle_action = QAction("Enable Push-to-Talk")
        self.toggle_action.setCheckable(True)
        self.toggle_action.setChecked(True)
        self.toggle_action.triggered.connect(self.toggle_ptt)
        self.menu.addAction(self.toggle_action)
        
        self.menu.addSeparator()

        self.quit_action = QAction("Quit")
        self.quit_action.triggered.connect(self.quit_app)
        self.menu.addAction(self.quit_action)

        self.tray_icon.setContextMenu(self.menu)

        # Start input listener thread
        self.evdev_thread = EvdevThread(config['device_path'], config['button_code'])
        self.evdev_thread.pressed.connect(self.on_press)
        self.evdev_thread.released.connect(self.on_release)
        self.evdev_thread.start()

        # Initialize to muted state
        self.set_mic_mute('1')

        # Allow Python to catch Ctrl+C / Systemd Signals by yielding execution briefly
        timer = QTimer()
        timer.timeout.connect(lambda: None)
        timer.start(500)

        # Create a socket pair to bridge OS signals and Qt's event loop
        self.sig_fd_r, self.sig_fd_w = socket.socketpair()
        self.sig_fd_w.setblocking(False)
        self.sig_fd_r.setblocking(False)

        # Tell Python to write a byte to this socket when ANY signal arrives
        signal.set_wakeup_fd(self.sig_fd_w.fileno())

        # We still need a dummy Python handler so it doesn't ignore the signal entirely
        signal.signal(signal.SIGUSR1, lambda signum, frame: None)

        # Tell Qt to listen to the read end of the socket and wake up instantly
        self.notifier = QSocketNotifier(self.sig_fd_r.fileno(), QSocketNotifier.Type.Read)
        self.notifier.activated.connect(self.handle_signal_wakeup)

    def create_icon(self, color_name):
        """Draws a simple colored circle on the fly."""
        pixmap = QPixmap(64, 64)
        pixmap.fill(QColor("transparent"))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(color_name))
        painter.setPen(QColor("transparent"))
        painter.drawEllipse(4, 4, 56, 56)
        painter.end()
        return QIcon(pixmap)

    def update_icon(self):
        if not self.ptt_enabled:
            self.tray_icon.setIcon(self.create_icon("dodgerblue"))
            self.tray_icon.setToolTip("Mic Open (PTT Disabled)")
        elif self.is_transmitting:
            self.tray_icon.setIcon(self.create_icon("limegreen"))
            self.tray_icon.setToolTip("Transmitting")
        else:
            self.tray_icon.setIcon(self.create_icon("crimson"))
            self.tray_icon.setToolTip("Muted (PTT Ready)")

    def set_mic_mute(self, state):
        subprocess.run(['wpctl', 'set-mute', '@DEFAULT_AUDIO_SOURCE@', state])

    def play_toggle_sound(self, ptt_is_active):
        """Plays a native system sound, falling back through standard KDE/Linux themes."""
        if ptt_is_active:
            # Ascending tone when PTT is ready
            options = [
                '/usr/share/sounds/ocean/stereo/device-added.oga',
                '/usr/share/sounds/freedesktop/stereo/device-added.oga',
                '/usr/share/sounds/oxygen/stereo/device-added.ogg'
            ]
        else:
            # Descending tone when PTT is disabled (mic open)
            options = [
                '/usr/share/sounds/ocean/stereo/device-removed.oga',
                '/usr/share/sounds/freedesktop/stereo/device-removed.oga',
                '/usr/share/sounds/oxygen/stereo/device-removed.ogg'
            ]
            
        # Find the first sound file that actually exists on the system
        sound_to_play = None
        for snd in options:
            if Path(snd).exists():
                sound_to_play = snd
                break
                
        if not sound_to_play:
            print("Warning: Could not find sound files in Ocean, Freedesktop, or Oxygen themes.")
            return
            
        # Fire and forget in the background
        subprocess.Popen(
            ['pw-play', sound_to_play], 
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL
        )

    def play_ptt_chirp(self, is_opening):
        """Plays a short, custom walkie-talkie chirp from the config folder."""
        sound_dir = CONFIG_DIR / 'sounds'

        if is_opening:
            sound_file = sound_dir / 'ptt_open.wav'
        else:
            sound_file = sound_dir / 'ptt_close.wav'

        # It only attempts to play if you actually placed the files there
        if sound_file.exists():
            subprocess.Popen(
                ['pw-play', str(sound_file)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

    def toggle_ptt(self):
        self.ptt_enabled = self.toggle_action.isChecked()
        if not self.ptt_enabled:
            self.set_mic_mute('0') # Unmute
        else:
            self.set_mic_mute('1') # Mute

        self.update_icon()
        self.play_toggle_sound(self.ptt_enabled)

    def handle_signal_wakeup(self, fd):
        """Triggered by the socket when a UNIX signal hits."""
        # Read the byte to clear the socket buffer
        try:
            self.sig_fd_r.recv(1)
        except BlockingIOError:
            pass
        
        # Now we are guaranteed to be awake and inside the active Qt event loop!
        current_state = self.toggle_action.isChecked()
        self.toggle_action.setChecked(not current_state)
        self.toggle_ptt()

    def on_press(self):
        if self.ptt_enabled:
            self.set_mic_mute('0')
            self.is_transmitting = True
            self.update_icon()
            self.play_ptt_chirp(True)

    def on_release(self):
        if self.ptt_enabled:
            self.set_mic_mute('1')
            self.is_transmitting = False
            self.update_icon()
            self.play_ptt_chirp(False)

    def quit_app(self):
        print("Cleaning up and exiting...")
        self.set_mic_mute('0') # Unmute on exit
        self.app.quit()
        sys.exit(0)

    def run(self):
        sys.exit(self.app.exec())

if __name__ == '__main__':
    # Handle termination signals cleanly
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    signal.signal(signal.SIGTERM, signal.SIG_DFL)

    config = load_config()
    
    # Check if we passed the --setup flag from the desktop shortcut
    if len(sys.argv) > 1 and sys.argv[1] == '--setup':
        config = run_setup()
    elif not config or not Path(config.get('device_path', '')).exists():
        config = run_setup()

    app = PTTApp(config)
    app.run()
