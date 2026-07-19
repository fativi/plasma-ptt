# Plasma Push-to-Talk (PTT) Daemon

A lightweight, Wayland-compatible push-to-talk daemon for KDE Plasma and PipeWire.

Instead of relying on window focus or Wayland-restricted keyloggers, it reads raw hardware events directly from `/dev/input/` for system-wide microphone muting and unmuting. Includes a PyQt6 system tray icon for visual feedback and supports custom audio chirps.

## Features

- **Wayland & X11 compatible:** Intercepts hardware events directly using `evdev` (mice, keyboards, controllers, and joysticks).
- **Multi-device support:** Configure multiple input devices simultaneously.
- **Hotplugging:** Configured USB/wireless devices (such as DualSense controllers) automatically reconnect when plugged in or turned on.
- **Stuck-state prevention:** Detects disconnected devices and releases any active PTT signals.
- **Mic overlap:** Keeps the microphone open as long as at least one configured PTT button is held down.
- **PipeWire integration:** Uses `wpctl` to mute/unmute the default audio source.
- **System tray indicator:** A PyQt6 tray icon showing the current microphone state.
- **Master toggle hotkey:** A configurable hardware hotkey to pause PTT and lock the mic open.
- **Audio feedback:** Generates ascending/descending dual-tone chimes when toggling modes, and supports custom walkie-talkie chirps for PTT.
- **Systemd service:** Runs as a systemd user service and restarts automatically on failure.

## Installation

Clone the repository and run the included installation script. The script detects your package manager (Arch/pacman, Debian/apt, or Fedora/dnf) and installs the necessary Python dependencies.

```bash
git clone https://github.com/fativi/plasma-ptt.git
cd plasma-ptt
chmod +x install.sh
./install.sh
```

> **Note:** The installer adds your user to the `input` group so the script can read hardware events without root privileges. If this is your first time being added to that group, you must log out and back in for the change to take effect.

## Configuration

The installer launches a GUI configuration dialog for managing your push-to-talk devices.

- **Add devices:** Select an input device from the dropdown, click **Capture Button**, and press the key/button you want to map.
- **Remove devices:** Highlight a device in the list and click **Remove Selected Device**.
- **Hotplugging:** Wireless devices (like joysticks or DualSense controllers) can be configured while disconnected. The daemon waits for them to reconnect.

To reconfigure your bindings at any time:

- Right-click the microphone tray icon and select **Setup**.

## Master Enable/Disable Toggle

You can configure a global shortcut to temporarily disable push-to-talk (leaving your mic open) without clicking the tray icon.

**Method 1: Built-in hardware hotkey**
1. Right-click the system tray icon and open **Setup**.
2. In the **Master Enable/Disable Toggle** section, select your target device from the dropdown.
3. Click **Capture Toggle Button** and press your desired key or button.
4. Save your configuration.

**Method 2: KDE keyboard shortcut via UNIX signal**

Use this if you prefer a complex key combination (like `Ctrl + Shift + M`) via KDE's native shortcut system:

1. Open KDE System Settings > Keyboard > Shortcuts.
2. Add a new Command shortcut.
3. Set the command to: `pkill -SIGUSR1 -f plasma-ptt.py`
4. Set the trigger to your preferred key combination.
5. Click Apply.

## Custom Audio Feedback

The daemon provides built-in audio feedback:

- **PTT mode toggles**: `ptt_enabled.wav` and `ptt_disabled.wav` are automatically generated and played when toggling PTT on and off.
- **PTT chirps**: Drop custom `.wav` files into the sounds directory to play a chirp when pressing and releasing the PTT button.

Sound file locations:

```
~/.config/plasma-ptt/sounds/ptt_open.wav     # Mic open
~/.config/plasma-ptt/sounds/ptt_close.wav    # Mic close
~/.config/plasma-ptt/sounds/ptt_enabled.wav  # PTT enabled
~/.config/plasma-ptt/sounds/ptt_disabled.wav # PTT disabled
```

Restart the service after modifying sound files.

## File Locations

```
~/.local/bin/plasma-ptt.py                        # Executable
~/.config/systemd/user/plasma-ptt.service         # Systemd service
~/.config/plasma-ptt/                             # Configuration & sounds
```

## Service Management

```bash
systemctl --user status plasma-ptt.service
systemctl --user restart plasma-ptt.service
systemctl --user stop plasma-ptt.service
```

To follow the logs:

```bash
journalctl --user -u plasma-ptt.service -f
```
