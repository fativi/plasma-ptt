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
import re
import grp
import getpass
from pathlib import Path
import evdev

__version__ = "1.0.1"

from PyQt6.QtWidgets import (QApplication, QSystemTrayIcon, QMenu, QDialog, 
                             QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton, 
                             QDialogButtonBox, QMessageBox, QListWidget, QListWidgetItem,
                             QGroupBox)
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


def create_microphone_icon(color_name):
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


def get_friendly_device_name(path_str):
    device_type = None
    path_lower = path_str.lower()
    if 'mouse' in path_lower:
        device_type = 'Mouse'
    elif 'joystick' in path_lower or 'gamepad' in path_lower:
        device_type = 'Joystick/Controller'
    elif 'kbd' in path_lower or 'keyboard' in path_lower:
        device_type = 'Keyboard'

    try:
        dev = evdev.InputDevice(path_str)
        name = dev.name
    except Exception:
        # Fallback to cleaning up the path name
        path = Path(path_str)
        name = path.name
        # e.g., usb-Sony_Interactive_Entertainment_DualSense_Wireless_Controller-event-joystick
        if name.startswith('usb-'):
            name = name[4:]
        if name.startswith('pci-'):
            name = name[4:]
        # Remove event suffixes
        for suffix in ['-event-joystick', '-event-mouse', '-event-kbd', '-event', '-joystick', '-mouse', '-kbd']:
            if name.endswith(suffix):
                name = name[:-len(suffix)]
                break
        name = name.replace('_', ' ')
        name = f"{name} (Disconnected)"

    if device_type:
        return f"{name} [{device_type}]"
    return name


class SetupDialog(QDialog):
    def __init__(self, current_config=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Plasma PTT Setup")
        self.setWindowIcon(create_microphone_icon("dodgerblue"))
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
        self.toggle_selected_path = None
        self.button_code = None
        self.capture_thread = None
        
        layout = QVBoxLayout(self)
        
        # --- Group 1: PTT Input Devices ---
        input_group = QGroupBox("Push-to-Talk Input Devices")
        input_layout = QVBoxLayout()
        
        input_layout.addWidget(QLabel("Currently Configured Triggers:"))
        self.devices_list = QListWidget()
        self.refresh_devices_list()
        input_layout.addWidget(self.devices_list)

        self.remove_btn = QPushButton("Remove Selected Device")
        self.remove_btn.clicked.connect(self.remove_selected_device)
        input_layout.addWidget(self.remove_btn)
        
        add_label = QLabel("<b>Add New Trigger</b>")
        add_label.setContentsMargins(0, 10, 0, 5)
        input_layout.addWidget(add_label)

        h_layout1 = QHBoxLayout()
        h_layout1.addWidget(QLabel("Hardware Device:"))
        self.device_combo = QComboBox()
        self.device_combo.currentIndexChanged.connect(self.on_device_changed)
        h_layout1.addWidget(self.device_combo, stretch=1)
        input_layout.addLayout(h_layout1)

        h_layout2 = QHBoxLayout()
        h_layout2.addWidget(QLabel("Target Button Code:"))
        self.code_label = QLabel(f"<b>{self.button_code if self.button_code else 'None'}</b>")
        h_layout2.addWidget(self.code_label, stretch=1)
        self.capture_btn = QPushButton("Capture Button")
        self.capture_btn.clicked.connect(self.toggle_capture)
        h_layout2.addWidget(self.capture_btn)
        input_layout.addLayout(h_layout2)

        input_group.setLayout(input_layout)
        layout.addWidget(input_group)

        # --- Group 1.5: Master Enable/Disable Toggle ---
        toggle_group = QGroupBox("Master Enable/Disable Toggle")
        toggle_layout = QVBoxLayout()
        desc_label = QLabel("Set an optional global hotkey to pause Push-to-Talk and leave your microphone open:")
        desc_label.setWordWrap(True)
        toggle_layout.addWidget(desc_label)
        
        self.toggle_trigger = self.current_config.get('toggle_trigger', None)
        self.toggle_display_label = QLabel(self._format_toggle_text())
        toggle_layout.addWidget(self.toggle_display_label)

        t_h_layout1 = QHBoxLayout()
        t_h_layout1.addWidget(QLabel("Target Device:"))
        self.toggle_device_combo = QComboBox()
        self.toggle_device_combo.currentIndexChanged.connect(self.on_toggle_device_changed)
        t_h_layout1.addWidget(self.toggle_device_combo, stretch=1)
        toggle_layout.addLayout(t_h_layout1)

        t_h_layout = QHBoxLayout()
        self.toggle_capture_btn = QPushButton("Capture Toggle Button")
        self.toggle_capture_btn.clicked.connect(self.start_toggle_capture)
        t_h_layout.addWidget(self.toggle_capture_btn)
        
        self.toggle_clear_btn = QPushButton("Clear Toggle Button")
        self.toggle_clear_btn.clicked.connect(self.clear_toggle_trigger)
        t_h_layout.addWidget(self.toggle_clear_btn)
        toggle_layout.addLayout(t_h_layout)
        
        toggle_group.setLayout(toggle_layout)
        layout.addWidget(toggle_group)

        # --- Group 2: Microphone Selection ---
        mic_group = QGroupBox("Microphone Configuration")
        mic_layout = QVBoxLayout()
        mic_layout.addWidget(QLabel("Select the audio source to mute/unmute (falls back to system default):"))
        self.mic_combo = QComboBox()
        self.populate_mics()
        mic_layout.addWidget(self.mic_combo)
        
        mic_group.setLayout(mic_layout)
        layout.addWidget(mic_group)
        
        self.populate_devices()
        
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
        toggle_index_to_select = -1
        
        for path in by_id_dir.iterdir():
            if not path.is_file() and not path.is_symlink():
                continue
                
            try:
                # Test opening the device. If it's disconnected or not readable, it will throw an exception.
                dev = evdev.InputDevice(str(path))
                friendly = get_friendly_device_name(str(path))
                
                if hasattr(self, 'device_combo'):
                    self.device_combo.addItem(friendly, str(path))
                    if str(path) == self.selected_path:
                        index_to_select = self.device_combo.count() - 1
                        
                if hasattr(self, 'toggle_device_combo'):
                    self.toggle_device_combo.addItem(friendly, str(path))
                    if str(path) == self.toggle_selected_path:
                        toggle_index_to_select = self.toggle_device_combo.count() - 1
            except PermissionError:
                continue
            except Exception:
                continue
                
        if hasattr(self, 'device_combo'):
            if index_to_select >= 0:
                self.device_combo.setCurrentIndex(index_to_select)
            elif self.device_combo.count() > 0:
                self.selected_path = self.device_combo.itemData(0)
                
        if hasattr(self, 'toggle_device_combo'):
            if toggle_index_to_select >= 0:
                self.toggle_device_combo.setCurrentIndex(toggle_index_to_select)
            elif self.toggle_device_combo.count() > 0:
                self.toggle_selected_path = self.toggle_device_combo.itemData(0)

    def refresh_devices_list(self):
        self.devices_list.clear()
        for i, dev in enumerate(self.devices):
            path = dev.get('device_path')
            friendly_name = get_friendly_device_name(path)
            item_text = f"{friendly_name} | Button: {dev.get('button_code')}"
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

    def populate_mics(self):
        self.mic_combo.addItem("Default Source (System Default)", "default")
        
        mics = []
        try:
            # Try to list using pactl first
            res = subprocess.run(['pactl', 'list', 'sources'], capture_output=True, text=True, check=True)
            blocks = res.stdout.split('Source #')
            for block in blocks[1:]:
                lines = block.split('\n')
                name = None
                desc = None
                for line in lines:
                    line = line.strip()
                    if line.startswith('Name: '):
                        name = line[6:]
                    elif line.startswith('Description: '):
                        desc = line[13:]
                if name and not name.endswith('.monitor'):
                    mics.append((name, desc or name))
        except Exception as e:
            print(f"Could not list mic devices using pactl: {e}")
            # Fall back to parsing wpctl status
            try:
                res = subprocess.run(['wpctl', 'status'], capture_output=True, text=True, check=True)
                in_sources = False
                for line in res.stdout.split('\n'):
                    if 'Sources:' in line:
                        in_sources = True
                        continue
                    if in_sources:
                        # Stop if we leave the sources section
                        if not line.strip() or 'Filters:' in line or 'Streams:' in line or 'Video' in line or 'Settings' in line:
                            if line.strip() and not line.startswith(' │'):
                                in_sources = False
                        match = re.search(r'(\d+)\.\s+(.+?)\s*(?:\[|$)', line)
                        if match:
                            source_id = match.group(1)
                            desc = match.group(2).strip()
                            mics.append((source_id, desc))
            except Exception as ex:
                print(f"Could not list mic devices using wpctl: {ex}")

        # Add all discovered mics
        selected_mic = self.current_config.get('mic_device', 'default')
        index_to_select = 0
        
        for name, desc in mics:
            self.mic_combo.addItem(desc, name)
            if name == selected_mic:
                index_to_select = self.mic_combo.count() - 1
                
        self.mic_combo.setCurrentIndex(index_to_select)

    def on_device_changed(self, index):
        if index >= 0:
            self.selected_path = self.device_combo.itemData(index)

    def on_toggle_device_changed(self, index):
        if index >= 0:
            self.toggle_selected_path = self.toggle_device_combo.itemData(index)

    def _format_toggle_text(self):
        if not self.toggle_trigger:
            return "<b>None configured</b>"
        return f"<b>{self.toggle_trigger['button_code']}</b> (on {get_friendly_device_name(self.toggle_trigger['device_path'])})"

    def toggle_capture(self):
        if self.capture_thread:
            self.reset_capture_ui()
            return
        if not self.selected_path:
            return
        self.capture_btn.setText("Cancel Capture")
        self.capture_mode = 'ptt'
        self.disable_ui_for_capture()
        self.capture_thread = EvdevCaptureThread(self.selected_path)
        self.capture_thread.captured.connect(self.on_captured)
        self.capture_thread.error.connect(self.on_capture_error)
        self.capture_thread.start()

    def start_toggle_capture(self):
        if self.capture_thread:
            self.reset_capture_ui()
            return
        if not self.toggle_selected_path:
            return
        self.toggle_capture_btn.setText("Cancel Capture")
        self.capture_mode = 'toggle'
        self.disable_ui_for_capture()
        self.capture_thread = EvdevCaptureThread(self.toggle_selected_path)
        self.capture_thread.captured.connect(self.on_captured)
        self.capture_thread.error.connect(self.on_capture_error)
        self.capture_thread.start()

    def clear_toggle_trigger(self):
        self.toggle_trigger = None
        self.toggle_display_label.setText(self._format_toggle_text())

    def disable_ui_for_capture(self):
        self.capture_btn.setEnabled(False)
        if hasattr(self, 'toggle_capture_btn'):
            self.toggle_capture_btn.setEnabled(False)
        if getattr(self, 'capture_mode', 'ptt') == 'ptt':
            self.capture_btn.setEnabled(True)
        else:
            if hasattr(self, 'toggle_capture_btn'):
                self.toggle_capture_btn.setEnabled(True)
        self.device_combo.setEnabled(False)
        if hasattr(self, 'toggle_device_combo'):
            self.toggle_device_combo.setEnabled(False)
        self.button_box.setEnabled(False)

    def on_captured(self, code):
        if getattr(self, 'capture_mode', 'ptt') == 'ptt':
            self.button_code = code
            self.code_label.setText(f"<b>{code}</b>")
            self.devices.append({'device_path': self.selected_path, 'button_code': code})
            self.refresh_devices_list()
        else:
            self.toggle_trigger = {'device_path': self.toggle_selected_path, 'button_code': code}
            self.toggle_display_label.setText(self._format_toggle_text())
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
        if hasattr(self, 'toggle_capture_btn'):
            self.toggle_capture_btn.setText("Capture Toggle Button")
            self.toggle_capture_btn.setEnabled(True)
        self.capture_btn.setEnabled(True)
        self.device_combo.setEnabled(True)
        if hasattr(self, 'toggle_device_combo'):
            self.toggle_device_combo.setEnabled(True)
        self.button_box.setEnabled(True)

    def save_and_accept(self):
        if not self.devices:
            QMessageBox.warning(self, "Incomplete Configuration", "Please add at least one device and capture a button.")
            return
            
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            mic_device = self.mic_combo.currentData()
            config_data = {
                'devices': self.devices,
                'mic_device': mic_device,
                'toggle_trigger': self.toggle_trigger
            }
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
    toggle = pyqtSignal()

    def __init__(self, devices_config, toggle_trigger=None):
        super().__init__()
        self.devices_config = devices_config
        self.toggle_trigger = toggle_trigger
        self._running = True

    def stop(self):
        self._running = False

    def run(self):
        active_devices = {}  # device_path -> InputDevice
        pressed_states = {}  # device_path -> bool
        
        ptt_buttons = {}
        for dev_conf in self.devices_config:
            path = dev_conf['device_path']
            if path not in ptt_buttons:
                ptt_buttons[path] = set()
            ptt_buttons[path].add(dev_conf['button_code'])

        toggle_path = self.toggle_trigger['device_path'] if self.toggle_trigger else None
        toggle_btn = self.toggle_trigger['button_code'] if self.toggle_trigger else None

        target_paths = set(ptt_buttons.keys())
        if toggle_path:
            target_paths.add(toggle_path)

        while self._running:
            for path in target_paths:
                if path not in active_devices:
                    if Path(path).exists():
                        try:
                            device = evdev.InputDevice(path)
                            active_devices[path] = device
                            pressed_states[path] = False
                            print(f"Successfully connected/reconnected device: {path}")
                        except Exception:
                            pass

            if not active_devices:
                self.msleep(1000)
                continue

            fds = {dev.fd: path for path, dev in active_devices.items()}
            try:
                r, w, x = select.select(list(fds.keys()), [], [], 1.0)
                for fd in r:
                    path = fds[fd]
                    device = active_devices[path]
                    try:
                        for event in device.read():
                            if event.type == evdev.ecodes.EV_KEY:
                                # Check PTT buttons
                                if path in ptt_buttons and event.code in ptt_buttons[path]:
                                    if event.value == 1:
                                        if not pressed_states.get(path, False):
                                            pressed_states[path] = True
                                            self.pressed.emit()
                                    elif event.value == 0:
                                        if pressed_states.get(path, False):
                                            pressed_states[path] = False
                                            self.released.emit()
                                # Check Toggle button
                                if path == toggle_path and event.code == toggle_btn:
                                    if event.value == 1:
                                        self.toggle.emit()
                    except OSError as e:
                        print(f"Device disconnected: {device.path} ({e})")
                        if pressed_states.get(path, False):
                            pressed_states[path] = False
                            self.released.emit()
                        del active_devices[path]
            except OSError:
                for path, device in list(active_devices.items()):
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
            
        toggle_trigger = self.config.get('toggle_trigger', None)
        self.evdev_thread = EvdevThread(devices, toggle_trigger)
        self.evdev_thread.pressed.connect(self.on_press)
        self.evdev_thread.released.connect(self.on_release)
        self.evdev_thread.toggle.connect(self.hotkey_toggle_ptt)
        self.evdev_thread.start()

    def hotkey_toggle_ptt(self):
        current_state = self.toggle_action.isChecked()
        self.toggle_action.setChecked(not current_state)
        self.toggle_ptt()

    def stop_evdev_thread(self):
        if self.evdev_thread:
            self.evdev_thread.stop()
            self.evdev_thread.wait()
            self.evdev_thread = None

    def open_setup(self):
        self.stop_evdev_thread()
        
        # Check permissions
        try:
            groups = [g.gr_name for g in grp.getgrall() if getpass.getuser() in g.gr_mem]
            current_group = grp.getgrgid(os.getgid()).gr_name
            if 'input' not in groups and current_group != 'input':
                QMessageBox.critical(None, "Permission Denied", 
                    "You must be in the 'input' group to read hardware events.\n\n"
                    "Open a terminal and run:\n"
                    f"sudo usermod -aG input {getpass.getuser()}\n\n"
                    "Then completely log out and log back in to apply the changes.")
        except Exception as e:
            print(f"Failed group check: {e}")

        dialog = SetupDialog(self.config)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.config = dialog.current_config
            # Enable systemd user service after saving
            try:
                subprocess.run(['systemctl', '--user', 'enable', '--now', 'plasma-ptt.service'], check=False)
            except Exception:
                pass

        devices = self.config.get('devices', [])
        if not devices and self.config and 'device_path' in self.config:
            devices = [{'device_path': self.config['device_path']}]

        if devices:
            self.start_evdev_thread()
        else:
            print("No devices configured, exiting...")
            self.quit_app()

    def create_icon(self, color_name):
        return create_microphone_icon(color_name)

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
        mic_device = self.config.get('mic_device', 'default')
        if not mic_device or mic_device == 'default':
            subprocess.run(['wpctl', 'set-mute', '@DEFAULT_AUDIO_SOURCE@', state])
        else:
            if mic_device.isdigit():
                subprocess.run(['wpctl', 'set-mute', mic_device, state])
            else:
                subprocess.run(['pactl', 'set-source-mute', mic_device, state])

    def _get_sound_path(self, filename):
        """Helper to find custom sound or fallback to system installed sound."""
        user_sound = CONFIG_DIR / 'sounds' / filename
        system_sound = Path('/usr/share/plasma-ptt/sounds') / filename
        if user_sound.exists():
            return user_sound
        elif system_sound.exists():
            return system_sound
        return None

    def play_toggle_sound(self, ptt_is_active):
        """Plays the custom ascending/descending toggle sounds."""
        filename = 'ptt_enabled.wav' if ptt_is_active else 'ptt_disabled.wav'
        sound_to_play = self._get_sound_path(filename)
            
        if sound_to_play:
            subprocess.Popen(
                ['pw-play', str(sound_to_play)], 
                stdout=subprocess.DEVNULL, 
                stderr=subprocess.DEVNULL
            )
        else:
            print(f"Warning: Could not find toggle sound {filename}")

    def play_ptt_chirp(self, is_opening):
        """Plays a short, custom walkie-talkie chirp from the config folder."""
        filename = 'ptt_open.wav' if is_opening else 'ptt_close.wav'
        sound_file = self._get_sound_path(filename)

        if sound_file:
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
