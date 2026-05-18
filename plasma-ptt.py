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
import select
from pathlib import Path
import evdev

from PyQt6.QtWidgets import (QApplication, QSystemTrayIcon, QMenu, QDialog, 
                             QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton, 
                             QDialogButtonBox, QMessageBox, QListWidget, QListWidgetItem)
from PyQt6.QtGui import QIcon, QAction, QPixmap, QPainter, QColor, QPen
from PyQt6.QtCore import QThread, pyqtSignal, QTimer, QSocketNotifier, Qt

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

class EvdevCaptureThread(QThread):
    captured = pyqtSignal(int)
    error = pyqtSignal(str)

    def __init__(self, device_path):
        super().__init__()
        self.device_path = device_path
        self._running = True

    def stop(self):
        self._running = False

    def run(self):
        try:
            device = evdev.InputDevice(self.device_path)
            while self._running:
                r, w, x = select.select([device.fd], [], [], 0.5)
                if r:
                    for event in device.read():
                        if event.type == evdev.ecodes.EV_KEY and event.value == 1:
                            self.captured.emit(event.code)
                            return
        except Exception as e:
            self.error.emit(str(e))


class SetupDialog(QDialog):
    def __init__(self, current_config=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Plasma PTT Setup")
        self.setMinimumWidth(450)
        
        self.current_config = current_config or {}
        self.devices = self.current_config.get('devices', [])
        # Migrate old config format
        if not self.devices and 'device_path' in self.current_config and 'button_code' in self.current_config:
            self.devices.append({
                'device_path': self.current_config['device_path'],
                'button_code': self.current_config['button_code']
            })

        self.selected_path = None
        self.button_code = None
        self.capture_thread = None
        
        layout = QVBoxLayout(self)
        
        # Configured Devices List
        layout.addWidget(QLabel("Configured Devices:"))
        self.devices_list = QListWidget()
        self.refresh_devices_list()
        layout.addWidget(self.devices_list)

        self.remove_btn = QPushButton("Remove Selected Device")
        self.remove_btn.clicked.connect(self.remove_selected_device)
        layout.addWidget(self.remove_btn)
        
        layout.addWidget(QLabel("--- Add New Device ---"))

        # Device Selection
        layout.addWidget(QLabel("Select Input Device:"))
        self.device_combo = QComboBox()
        self.populate_devices()
        self.device_combo.currentIndexChanged.connect(self.on_device_changed)
        layout.addWidget(self.device_combo)
        
        # Capture Section
        layout.addWidget(QLabel("Push-to-Talk Button:"))
        self.code_label = QLabel(f"<b>{self.button_code if self.button_code else 'None'}</b>")
        layout.addWidget(self.code_label)
        
        self.capture_btn = QPushButton("Capture Button")
        self.capture_btn.clicked.connect(self.toggle_capture)
        layout.addWidget(self.capture_btn)
        
        # Dialog Buttons
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.button_box.accepted.connect(self.save_and_accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)
        
    def populate_devices(self):
        by_id_dir = Path('/dev/input/by-id/')
        if not by_id_dir.exists():
            return
            
        index_to_select = -1
        
        for path in by_id_dir.iterdir():
            if not path.is_file() and not path.is_symlink():
                continue
                
            try:
                dev = evdev.InputDevice(str(path))
                self.device_combo.addItem(dev.name, str(path))
                if str(path) == self.selected_path:
                    index_to_select = self.device_combo.count() - 1
            except PermissionError:
                continue
            except Exception:
                continue
                
        if index_to_select >= 0:
            self.device_combo.setCurrentIndex(index_to_select)
        elif self.device_combo.count() > 0:
            self.selected_path = self.device_combo.itemData(0)

    def refresh_devices_list(self):
        self.devices_list.clear()
        for i, dev in enumerate(self.devices):
            item_text = f"Device: {dev.get('device_path')} | Button: {dev.get('button_code')}"
            item = QListWidgetItem(item_text)
            item.setData(Qt.ItemDataRole.UserRole, i)
            self.devices_list.addItem(item)

    def remove_selected_device(self):
        selected_items = self.devices_list.selectedItems()
        if not selected_items:
            return
        for item in selected_items:
            idx = item.data(Qt.ItemDataRole.UserRole)
            if 0 <= idx < len(self.devices):
                del self.devices[idx]
        self.refresh_devices_list()

    def on_device_changed(self, index):
        if index >= 0:
            self.selected_path = self.device_combo.itemData(index)

    def toggle_capture(self):
        if self.capture_thread:
            self.reset_capture_ui()
            return

        if not self.selected_path:
            return
            
        self.capture_btn.setText("Cancel Capture")
        self.capture_btn.setEnabled(True)
        self.device_combo.setEnabled(False)
        self.button_box.setEnabled(False)
        
        self.capture_thread = EvdevCaptureThread(self.selected_path)
        self.capture_thread.captured.connect(self.on_captured)
        self.capture_thread.error.connect(self.on_capture_error)
        self.capture_thread.start()

    def on_captured(self, code):
        self.button_code = code
        self.code_label.setText(f"<b>{code}</b>")
        self.devices.append({'device_path': self.selected_path, 'button_code': code})
        self.refresh_devices_list()
        self.reset_capture_ui()

    def on_capture_error(self, err_msg):
        QMessageBox.warning(self, "Capture Error", f"Failed to capture: {err_msg}")
        self.reset_capture_ui()

    def reset_capture_ui(self):
        if self.capture_thread:
            self.capture_thread.stop()
            self.capture_thread.wait()
            self.capture_thread = None
            
        self.capture_btn.setText("Capture Button")
        self.capture_btn.setEnabled(True)
        self.device_combo.setEnabled(True)
        self.button_box.setEnabled(True)

    def save_and_accept(self):
        if not self.devices:
            QMessageBox.warning(self, "Incomplete Configuration", "Please add at least one device and capture a button.")
            return
            
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            config_data = {'devices': self.devices}
            with open(CONFIG_FILE, 'w') as f:
                json.dump(config_data, f, indent=4)
                
            self.current_config = config_data
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not save config: {e}")

    def closeEvent(self, event):
        if self.capture_thread:
            self.capture_thread.stop()
            self.capture_thread.wait()
        super().closeEvent(event)


# --- background thread for mouse input ---
class EvdevThread(QThread):
    pressed = pyqtSignal()
    released = pyqtSignal()

    def __init__(self, devices_config):
        super().__init__()
        self.devices_config = devices_config
        self._running = True

    def stop(self):
        self._running = False

    def run(self):
        active_devices = {}  # device_path -> (InputDevice, button_code)
        pressed_states = {}  # device_path -> bool

        while self._running:
            # Attempt to reconnect disconnected devices
            for dev_conf in self.devices_config:
                path = dev_conf['device_path']
                if path not in active_devices:
                    if Path(path).exists():
                        try:
                            device = evdev.InputDevice(path)
                            active_devices[path] = (device, dev_conf['button_code'])
                            pressed_states[path] = False
                            print(f"Successfully connected/reconnected device: {path}")
                        except Exception as e:
                            pass

            if not active_devices:
                self.msleep(1000)
                continue

            fds = [dev.fd for dev, _ in active_devices.values()]
            fd_to_path = {dev.fd: path for path, (dev, _) in active_devices.items()}

            try:
                r, w, x = select.select(fds, [], [], 1.0)
                for fd in r:
                    path = fd_to_path[fd]
                    device, target_button = active_devices[path]
                    try:
                        for event in device.read():
                            if event.type == evdev.ecodes.EV_KEY and event.code == target_button:
                                if event.value == 1:
                                    if not pressed_states.get(path, False):
                                        pressed_states[path] = True
                                        self.pressed.emit()
                                elif event.value == 0:
                                    if pressed_states.get(path, False):
                                        pressed_states[path] = False
                                        self.released.emit()
                    except OSError as e:
                        print(f"Device disconnected: {device.path} ({e})")
                        if pressed_states.get(path, False):
                            pressed_states[path] = False
                            self.released.emit()
                        del active_devices[path]
            except OSError as e:
                # If select fails due to a bad fd, we need to find and remove it
                for path, (device, _) in list(active_devices.items()):
                    try:
                        select.select([device.fd], [], [], 0)
                    except OSError:
                        print(f"Removing disconnected device: {path}")
                        if pressed_states.get(path, False):
                            pressed_states[path] = False
                            self.released.emit()
                        del active_devices[path]


# --- main application ---
class PTTApp:
    def __init__(self, app, config):
        self.app = app
        self.config = config

        self.ptt_enabled = True
        self.is_transmitting = False
        self.pressed_count = 0

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

        self.setup_action = QAction("Setup")
        self.setup_action.triggered.connect(self.open_setup)
        self.menu.addAction(self.setup_action)

        self.menu.addSeparator()

        self.quit_action = QAction("Quit")
        self.quit_action.triggered.connect(self.quit_app)
        self.menu.addAction(self.quit_action)

        self.tray_icon.setContextMenu(self.menu)

        # Start input listener thread
        self.evdev_thread = None
        self.start_evdev_thread()

        # Initialize to muted state
        self.set_mic_mute('1')

        # Allow Python to catch Ctrl+C / Systemd Signals by yielding execution briefly
        self.timer = QTimer()
        self.timer.timeout.connect(lambda: None)
        self.timer.start(500)

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

    def start_evdev_thread(self):
        devices = self.config.get('devices', [])
        if not devices and 'device_path' in self.config and 'button_code' in self.config:
            devices = [{'device_path': self.config['device_path'], 'button_code': self.config['button_code']}]
            
        if not devices:
            return
            
        self.evdev_thread = EvdevThread(devices)
        self.evdev_thread.pressed.connect(self.on_press)
        self.evdev_thread.released.connect(self.on_release)
        self.evdev_thread.start()

    def stop_evdev_thread(self):
        if self.evdev_thread:
            self.evdev_thread.stop()
            self.evdev_thread.wait()
            self.evdev_thread = None

    def open_setup(self):
        self.stop_evdev_thread()

        dialog = SetupDialog(self.config)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.config = dialog.current_config

        devices = self.config.get('devices', [])
        if not devices and self.config and 'device_path' in self.config:
            devices = [{'device_path': self.config['device_path']}]

        if devices:
            self.start_evdev_thread()
        else:
            print("No devices configured, exiting...")
            self.quit_app()

    def create_icon(self, color_name):
        """Draws a microphone icon on the fly."""
        pixmap = QPixmap(64, 64)
        pixmap.fill(QColor("transparent"))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        color = QColor(color_name)
        pen = QPen(color)
        pen.setWidth(4)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        
        # Draw mic capsule
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawRoundedRect(24, 8, 16, 26, 8, 8)
        
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(pen)
        
        # Draw U shape stand
        painter.drawLine(16, 26, 16, 34)
        painter.drawLine(48, 26, 48, 34)
        painter.drawArc(16, 18, 32, 32, 180 * 16, 180 * 16)
        
        # Draw base
        painter.drawLine(32, 50, 32, 58)
        painter.drawLine(20, 58, 44, 58)
        
        # Add a slash for muted state
        if color_name == "crimson":
            # Create a transparent cutout behind the slash to improve legibility
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            clear_pen = QPen(Qt.GlobalColor.transparent)
            clear_pen.setWidth(8)
            clear_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(clear_pen)
            painter.drawLine(12, 12, 52, 52)
            
            # Draw the actual slash
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            pen.setWidth(4)
            painter.setPen(pen)
            painter.drawLine(12, 12, 52, 52)
            
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
            if self.pressed_count == 0:
                self.set_mic_mute('0')
                self.is_transmitting = True
                self.update_icon()
                self.play_ptt_chirp(True)
            self.pressed_count += 1

    def on_release(self):
        if self.ptt_enabled:
            self.pressed_count = max(0, self.pressed_count - 1)
            if self.pressed_count == 0:
                self.set_mic_mute('1')
                self.is_transmitting = False
                self.update_icon()
                self.play_ptt_chirp(False)

    def quit_app(self):
        print("Cleaning up and exiting...")
        self.set_mic_mute('0') # Unmute on exit
        self.stop_evdev_thread()
        self.app.quit()


if __name__ == '__main__':
    # Handle termination signals cleanly
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    signal.signal(signal.SIGTERM, signal.SIG_DFL)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    config = load_config()
    
    setup_requested = (len(sys.argv) > 1 and sys.argv[1] == '--setup')
    
    def has_configured_device(cfg):
        if not cfg: return False
        devs = cfg.get('devices', [])
        if not devs and 'device_path' in cfg:
            devs = [{'device_path': cfg['device_path']}]
        return len(devs) > 0

    needs_setup = not config or not has_configured_device(config)

    if setup_requested or needs_setup:
        dialog = SetupDialog(config)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            config = dialog.current_config
            if setup_requested:
                sys.exit(0)
        else:
            if needs_setup:
                print("Setup cancelled and no valid config exists. Exiting.")
                sys.exit(0)
            if setup_requested:
                sys.exit(0)

    if not config or not has_configured_device(config):
        sys.exit(1)

    ptt_app = PTTApp(app, config)
    sys.exit(app.exec())
