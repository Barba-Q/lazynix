# LazyNix

> **Graphical System Configuration Editor for NixOS**  
> Manage system settings, hardware drivers, firewalls, and packages without editing raw Nix code. Built for simplicity, safety, and non-technical users.

<img width="651" height="606" alt="lazynix_01" src="https://github.com/user-attachments/assets/0ee27c12-8913-459f-a5bd-7937d138519a" />

## Features

- **Software & Services**
  - **Flatpak Toggle**: Enable Flatpak support with a single click.
  - **Auto Software Store Integration**: Automatically installs KDE Discover or GNOME Software depending on your desktop environment when Flatpak is enabled.
  - **Flatpak Cleanup**: Scheduled weekly systemd timer to purge orphaned Flatpak runtimes.
  - **Bluetooth Management**: Toggle Bluetooth support and set auto-power on boot.
  - **System Packages**: Easily manage and install system-packages.
  - **Automatic updates**: Enable automatic system updates.

- **Hardware & Drivers**
  - **NVIDIA Driver Manager**: Enable proprietary drivers with optional toggles for Open-Source Kernel Modules.
  - **CUPS Printing Support**: One-click printing stack enablement.

- **System & Maintenance**
  - **Generation Limit**: Limit system bootloader entries (e.g., maximum 10 generations) to prevent boot partition bloat.
  - **Automated Garbage Collection**: Weekly cleaning of older Nix store paths.

- **Firewall Configuration**
  - Toggle firewall status.
  - Easily specify allowed TCP/UDP ports and range rules without syntax errors.

- **User & Group Management**
  - Manage primary user accounts and extra security group assignments.

- **Safety & Rollbacks**
  - **Automatic Atomic Backups**: Every rebuild creates a timestamped backup in /etc/nixos/.
  - **Graphical Rollback Tab**: View all historical backups and restore your system to any previous state directly from the GUI.
  - **Non-Blocking Rebuilds**: Runs `nixos-rebuild switch` in a background thread, native Polkit authentication, and progress indicators.


---
## Quick Start (Without Installation)

You can run LazyNix directly without manually installing PyQt6 or Python dependencies:

```bash
git clone [https://github.com/Barba-Q/lazynix.git](https://github.com/Barba-Q/lazynix.git)
cd lazynix
chmod +x lazynix.py
./lazynix.py
```

## Installation

To install LazyNix into your local application menu (KDE Plasma, GNOME, XFCE, etc.):

```bash
chmod +x install.sh
./install.sh
