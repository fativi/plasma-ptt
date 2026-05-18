# Plasma Push-to-Talk (PTT) Daemon

A lightweight, Wayland-compatible Push-to-Talk background daemon designed for KDE Plasma and PipeWire. 

Instead of relying on window focus or Wayland-restricted keyloggers, this tool reads raw hardware events directly from `/dev/input/` to provide flawless, system-wide microphone muting and unmuting. It includes a native PyQt6 system tray icon for visual feedback and supports custom audio chirps.

## ✨ Features
* **Wayland & X11 Compatible:** Intercepts hardware events directly using `evdev` (supporting mice, keyboards, controllers, and joysticks).
* **Multi-Device Support:** Configure multiple input devices simultaneously to trigger your Push-to-Talk signal.
* **Smart Hotplugging:** Configured USB/wireless devices (such as DualSense controllers) automatically reconnect when plugged in or turned on.
* **Stuck-State Prevention:** Automatically detects disconnected devices and cleanly releases any active PTT signals.
* **Smart Mic Overlap:** Keeps the microphone open as long as at least one configured PTT button is being held down.
* **Native PipeWire Integration:** Uses `wpctl` to mute/unmute the default audio source instantly.
* **System Tray Indicator:** A dynamic PyQt6 tray icon showing your current microphone state.
* **Master Toggle Hotkey:** Configure a built-in hardware hotkey to easily pause PTT and lock your mic open.
* **Audio Feedback:** Generates and plays ascending/descending dual-tone chimes when toggling modes, and supports custom walkie-talkie "chirps" for PTT.
* **Persistent Daemon:** Runs as a systemd user service so it survives crashes and restarts automatically.

## 📦 Installation

Clone the repository and run the included installation script. The script automatically detects your package manager (Arch/pacman, Debian/apt, or Fedora/dnf) to install the necessary Python dependencies.

```bash
git clone https://github.com/fativi/plasma-ptt.git
cd plasma-ptt
chmod +x install.sh
./install.sh
```

Note: The installer adds your user to the input group so the script can read hardware events without root privileges. If this is your first time being added to that group, you must completely log out of your desktop environment and log back in for the changes to take effect.

⚙️ Configuration

The installer will automatically launch a GUI configuration dialog where you can manage your list of Push-to-Talk devices.

* **Add Devices:** Select an input device from the dropdown, click **Capture Button**, and press the key/button you want to map. The device will be added to the list.
* **Remove Devices:** Highlight a device in the list and click **Remove Selected Device**.
* **Hotplugging:** You can configure wireless devices (like joysticks or DualSense controllers). If they are unplugged or turned off, the daemon remains active and waits for them to reconnect.

To configure your bindings:

* Right-click the microphone system tray icon and select **Setup**.

⌨️ Setting Up a Master Enable/Disable Toggle

You can configure a global shortcut to temporarily disable Push-to-Talk (leaving your mic open) without having to click the tray icon. We recommend using the built-in configuration:

**Method 1: Built-in Hardware Hotkey (Recommended)**
1. Right-click the system tray icon and open the **Setup** dialog.
2. In the **Master Enable/Disable Toggle** section, select your target device from the dropdown.
3. Click **Capture Toggle Button** and press your desired key or button (e.g., a spare mouse button or keyboard key).
4. Save your configuration. Pressing this hotkey will now instantly toggle PTT mode and play a custom dual-tone chime!

**Method 2: Advanced UNIX Signal Method (For KDE Key Combos)**
If you prefer to use a complex key combination (like `Ctrl + Shift + M`), you can rely on KDE's native shortcut system and send a UNIX signal to the daemon:
1. Open KDE System Settings > Keyboard > Shortcuts.
2. Add a new Command shortcut.
3. Set the Action/Command to: `pkill -SIGUSR1 -f plasma-ptt.py`
4. Set the Trigger to your preferred key combination.
5. Click Apply.

🔊 Custom Audio Feedback

The daemon provides built-in audio feedback:
* **PTT Mode Toggles**: By default, `ptt_enabled.wav` and `ptt_disabled.wav` are automatically generated and played when you toggle the PTT requirement on and off.
* **PTT Walkie-Talkie Chirps**: You can drop custom sounds into the config directory to play a chirp when you press and release your configured PTT button.

To customize these sounds, drop short `.wav` files into the `sounds` directory:

    Mic Open: ~/.config/plasma-ptt/sounds/ptt_open.wav
    Mic Close: ~/.config/plasma-ptt/sounds/ptt_close.wav
    Toggle On: ~/.config/plasma-ptt/sounds/ptt_enabled.wav
    Toggle Off: ~/.config/plasma-ptt/sounds/ptt_disabled.wav

*(Restart the background service after modifying sound files).*

📂 File Locations
If you need to manually edit or remove the tool, here is where everything lives:

    Executable: ~/.local/bin/plasma-ptt.py
    Systemd Service: ~/.config/systemd/user/plasma-ptt.service
    Configuration & Sounds: ~/.config/plasma-ptt/

Manual Service Management

You can manage the background daemon just like any other system service:
systemctl --user status plasma-ptt.service
systemctl --user restart plasma-ptt.service
systemctl --user stop plasma-ptt.service

To view the logs for troubleshooting:
journalctl --user -u plasma-ptt.service -f

