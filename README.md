# Plasma Push-to-Talk (PTT) Daemon

A lightweight, Wayland-compatible Push-to-Talk background daemon designed for KDE Plasma and PipeWire. 

Instead of relying on window focus or Wayland-restricted keyloggers, this tool reads raw hardware events directly from `/dev/input/` to provide flawless, system-wide microphone muting and unmuting. It includes a native PyQt6 system tray icon for visual feedback and supports custom audio chirps.

## ✨ Features
* **Wayland & X11 Compatible:** Intercepts mouse events at the hardware level using `evdev`.
* **Native PipeWire Integration:** Uses `wpctl` to mute/unmute the default audio source instantly.
* **System Tray Indicator:** A dynamic PyQt6 tray icon showing your current microphone state.
* **Global Hotkey Support:** Toggle the PTT requirement on/off mid-game using UNIX signals.
* **Audio Feedback:** Supports custom walkie-talkie "chirps" when opening and closing the mic, plus system chimes when toggling modes.
* **Persistent Daemon:** Runs as a systemd user service so it survives crashes and restarts automatically.

## 📦 Installation

Clone the repository and run the included installation script. The script automatically detects your package manager (Arch/pacman, Debian/apt, or Fedora/dnf) to install the necessary Python dependencies.

```bash
git clone https://github.com/fativi/plasma-ptt.git
cd plasma-ptt
chmod +x install.sh
./install.sh
```

Note: The installer adds your user to the input group so the script can read mouse events without root privileges. If this is your first time being added to that group, you must completely log out of your desktop environment and log back in for the changes to take effect.

⚙️ Configuration

The installer will automatically launch a GUI configuration dialog prompting you to select your device and press the button you want to map to Push-to-Talk.

If you ever change your mouse or want to remap the button, you can rerun the configuration prompt at any time:

* Right-click the microphone system tray icon and select **Setup**.
* OR, open your application launcher (e.g., Plasma Kickoff), search for **Push-to-Talk Setup** and launch it.

⌨️ Setting Up a Global Toggle Shortcut

You can temporarily disable Push-to-Talk (leaving your mic open) without clicking the tray icon by setting up a global keyboard shortcut.

    Open KDE System Settings > Keyboard > Shortcuts.
    Add a new Command shortcut.
    Set the Action/Command to: pkill -SIGUSR1 -f plasma-ptt.py
    Set the Trigger to your preferred key combination (e.g., Ctrl + Shift + M).
    Click Apply.

Pressing this hotkey will instantly toggle PTT mode and play a system chime.

🔊 Custom Audio Chirps

The daemon supports custom sound effects when you press and release your PTT button. By default, the installer uses ffmpeg to generate synthetic walkie-talkie chirps.

To use your own sounds, drop any short .wav files into the sounds directory:

    Mic Open: ~/.config/plasma-ptt/sounds/ptt_open.wav
    Mic Close: ~/.config/plasma-ptt/sounds/ptt_close.wav

(Restart the background service after adding new files).

📂 File Locations
If you need to manually edit or remove the tool, here is where everything lives:

    Executable: ~/.local/bin/plasma-ptt.py
    Systemd Service: ~/.config/systemd/user/plasma-ptt.service
    App Launcher: ~/.local/share/applications/plasma-ptt-setup.desktop
    Configuration & Sounds: ~/.config/plasma-ptt/

Manual Service Management

You can manage the background daemon just like any other system service:
systemctl --user status plasma-ptt.service
systemctl --user restart plasma-ptt.service
systemctl --user stop plasma-ptt.service

To view the logs for troubleshooting:
journalctl --user -u plasma-ptt.service -f

