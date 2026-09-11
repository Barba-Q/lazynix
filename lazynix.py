#!/usr/bin/env nix-shell
#!nix-shell -i python3 -p python3Packages.pyqt6 nix

import sys
import re
import os
import glob
import datetime
import subprocess
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QFormLayout, QLineEdit, QCheckBox, QPushButton, QLabel,
    QTextEdit, QTabWidget, QMessageBox, QProgressBar, QListWidget, QSpinBox
)

CONFIG_PATH = "/etc/nixos/configuration.nix"

class RebuildWorker(QThread):
    finished_signal = pyqtSignal(int, str)

    def __init__(self, cmd):
        super().__init__()
        self.cmd = cmd

    def run(self):
        res = subprocess.run(self.cmd, shell=True, capture_output=True, text=True)
        self.finished_signal.emit(res.returncode, res.stderr)

class NixOSConfigEditor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LazyNix - NixOS Configuration Editor")
        self.resize(650, 580)
        self.setWindowIcon(QIcon.fromTheme("nixos"))
        self.config_content = ""
        self.worker = None
        self.init_ui()
        self.load_config()

    def init_ui(self):
        central_widget = QWidget()
        layout = QVBoxLayout(central_widget)
        tabs = QTabWidget()

        # --- Tab 1: Software & Services ---
        tab_sw = QWidget()
        layout_sw = QFormLayout(tab_sw)
        self.flatpak_cb = QCheckBox("Enable Flatpak & Flathub repository (services.flatpak.enable)")
        self.flatpak_gc_cb = QCheckBox("Automatic Flatpak cleanup (Remove unused runtimes)")
        self.bluetooth_cb = QCheckBox("Enable Bluetooth & power on at boot")
        self.pkgs_edit = QTextEdit()
        self.pkgs_edit.setPlaceholderText("Detected packages will appear here...")

        layout_sw.addRow(self.flatpak_cb)
        layout_sw.addRow(self.flatpak_gc_cb)
        layout_sw.addRow(self.bluetooth_cb)
        layout_sw.addRow(QLabel("Installed system packages (one per line or space-separated):"))
        layout_sw.addRow(self.pkgs_edit)
        tabs.addTab(tab_sw, "Software & Services")

        # --- Tab 2: Hardware & Drivers ---
        tab_hw = QWidget()
        layout_hw = QFormLayout(tab_hw)
        self.nvidia_cb = QCheckBox("Enable proprietary NVIDIA driver")
        self.nvidia_open_cb = QCheckBox("Use open-source kernel modules for NVIDIA (hardware.nvidia.open)")
        self.printing_cb = QCheckBox("Enable printer support (CUPS / services.printing.enable)")

        layout_hw.addRow(self.nvidia_cb)
        layout_hw.addRow(self.nvidia_open_cb)
        layout_hw.addRow(self.printing_cb)
        tabs.addTab(tab_hw, "Hardware & Drivers")

        # --- Tab 3: System & Maintenance ---
        tab_sys = QWidget()
        layout_sys = QFormLayout(tab_sys)
        self.gen_limit = QSpinBox()
        self.gen_limit.setRange(1, 50)
        self.gen_limit.setValue(10)
        self.nix_gc_cb = QCheckBox("Automatic Nix garbage collection (Delete old packages weekly)")
        self.autoupgrade_cb = QCheckBox("Enable automatic system updates (system.autoUpgrade)")

        layout_sys.addRow("Maximum system generations to keep:", self.gen_limit)
        layout_sys.addRow(self.nix_gc_cb)
        layout_sys.addRow(self.autoupgrade_cb)
        tabs.addTab(tab_sys, "System & Maintenance")

        # --- Tab 4: Firewall ---
        tab_fw = QWidget()
        layout_fw = QFormLayout(tab_fw)
        self.fw_cb = QCheckBox("Enable firewall (networking.firewall.enable)")
        self.fw_tcp_ports = QLineEdit()
        self.fw_udp_ports = QLineEdit()
        self.fw_tcp_ranges = QLineEdit()
        self.fw_tcp_ports.setPlaceholderText("e.g. 80 443 22")
        self.fw_udp_ports.setPlaceholderText("e.g. 53 123")
        self.fw_tcp_ranges.setPlaceholderText("e.g. { from = 8000; to = 8010; }")

        layout_fw.addRow(self.fw_cb)
        layout_fw.addRow("Allowed TCP ports:", self.fw_tcp_ports)
        layout_fw.addRow("Allowed UDP ports:", self.fw_udp_ports)
        layout_fw.addRow("TCP port ranges:", self.fw_tcp_ranges)
        tabs.addTab(tab_fw, "Firewall")

        # --- Tab 5: Users & Groups ---
        tab_user = QWidget()
        layout_user = QFormLayout(tab_user)
        self.username_input = QLineEdit()
        self.groups_input = QLineEdit()
        self.groups_input.setPlaceholderText("e.g. wheel networkmanager video")
        layout_user.addRow("Main username:", self.username_input)
        layout_user.addRow("Assigned groups:", self.groups_input)
        tabs.addTab(tab_user, "Users & Groups")

        # --- Tab 6: Backups & Rollback ---
        tab_bak = QWidget()
        layout_bak = QVBoxLayout(tab_bak)
        layout_bak.addWidget(QLabel("Available automatic backups in /etc/nixos/:"))
        self.backup_list = QListWidget()
        layout_bak.addWidget(self.backup_list)

        btn_layout = QHBoxLayout()
        self.refresh_bak_btn = QPushButton("Refresh list")
        self.refresh_bak_btn.clicked.connect(self.load_backups)
        self.restore_bak_btn = QPushButton("Restore selected backup")
        self.restore_bak_btn.clicked.connect(self.restore_selected_backup)
        btn_layout.addWidget(self.refresh_bak_btn)
        btn_layout.addWidget(self.restore_bak_btn)
        layout_bak.addLayout(btn_layout)
        tabs.addTab(tab_bak, "Backups & Rollback")

        layout.addWidget(tabs)

        # Status & Progress bar
        self.status_label = QLabel("Ready")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.hide()

        layout.addWidget(self.status_label)
        layout.addWidget(self.progress_bar)

        # Save & Apply button
        self.save_btn = QPushButton("Create safe backup & execute NixOS rebuild")
        self.save_btn.clicked.connect(self.save_and_apply)
        layout.addWidget(self.save_btn)

        self.setCentralWidget(central_widget)

    def load_config(self):
        if not os.path.exists(CONFIG_PATH):
            QMessageBox.critical(self, "Error", f"{CONFIG_PATH} does not exist!")
            return

        with open(CONFIG_PATH, 'r') as f:
            self.config_content = f.read()

        active_content = "\n".join([line for line in self.config_content.splitlines() if not line.strip().startswith('#')])

        # 1. Software & Services
        self.flatpak_cb.setChecked("services.flatpak.enable = true;" in active_content)
        self.flatpak_gc_cb.setChecked("flatpak-cleanup" in active_content)
        self.bluetooth_cb.setChecked("hardware.bluetooth.enable = true;" in active_content)

        # 2. Hardware & Drivers
        self.nvidia_cb.setChecked('"nvidia"' in active_content or "'nvidia'" in active_content)
        self.nvidia_open_cb.setChecked("hardware.nvidia.open = true;" in active_content)
        self.printing_cb.setChecked("services.printing.enable = true;" in active_content)

        # 3. System & Maintenance
        gen_match = re.search(r'configurationLimit\s*=\s*(\d+);', active_content)
        if gen_match:
            self.gen_limit.setValue(int(gen_match.group(1)))
        self.nix_gc_cb.setChecked("nix.gc.automatic = true;" in active_content)
        self.autoupgrade_cb.setChecked("system.autoUpgrade.enable = true;" in active_content)

        # 4. Firewall
        self.fw_cb.setChecked("enable = false;" not in active_content and "networking.firewall.enable = false;" not in active_content)
        tcp_match = re.search(r'allowedTCPPorts\s*=\s*\[(.*?)\];', active_content, re.DOTALL)
        if tcp_match:
            self.fw_tcp_ports.setText(self._clean_list(tcp_match.group(1)))
        udp_match = re.search(r'allowedUDPPorts\s*=\s*\[(.*?)\];', active_content, re.DOTALL)
        if udp_match:
            self.fw_udp_ports.setText(self._clean_list(udp_match.group(1)))
        range_match = re.search(r'allowedUDPPortRanges\s*=\s*\[(.*?)\];', active_content, re.DOTALL) or re.search(r'allowedTCPPortRanges\s*=\s*\[(.*?)\];', active_content, re.DOTALL)
        if range_match:
            self.fw_tcp_ranges.setText(self._clean_list(range_match.group(1)))

        # 5. System Packages
        pkg_match = re.search(r'environment\.systemPackages\s*=\s*(?:with pkgs;\s*)?\[(.*?)\];', active_content, re.DOTALL)
        if pkg_match:
            self.pkgs_edit.setText(self._clean_list(pkg_match.group(1)))

        # 6. User & Groups
        user_name = None
        user_match_dot = re.search(r'users\.(?:users|extraUsers)\.["\']?([a-zA-Z0-9_-]+)["\']?\s*=\s*\{', active_content)
        user_match_nested = re.search(r'users\.(?:users|extraUsers)\s*=\s*\{\s*["\']?([a-zA-Z0-9_-]+)["\']?\s*=\s*\{', active_content, re.DOTALL)

        if user_match_dot:
            user_name = user_match_dot.group(1)
        elif user_match_nested:
            user_name = user_match_nested.group(1)

        if user_name and user_name != "root":
            self.username_input.setText(user_name)

            user_block_match = re.search(r'users\.(?:users|extraUsers)\.["\']?' + re.escape(user_name) + r'["\']?\s*=\s*\{(.*?)\};', active_content, re.DOTALL)
            if user_block_match:
                groups_match = re.search(r'extraGroups\s*=\s*\[(.*?)\];', user_block_match.group(1), re.DOTALL)
                if groups_match:
                    groups_raw = groups_match.group(1).replace('"', '').replace("'", "")
                    self.groups_input.setText(self._clean_list(groups_raw))
        else:
            env_user = os.environ.get("SUDO_USER") or os.environ.get("USER") or ""
            if env_user and env_user != "root":
                self.username_input.setText(env_user)
                self.groups_input.setText("wheel networkmanager video")

        self.load_backups()

    def load_backups(self):
        self.backup_list.clear()
        backups = sorted(glob.glob("/etc/nixos/configuration.nix.bak_*"), reverse=True)
        for b in backups:
            self.backup_list.addItem(os.path.basename(b))

    def restore_selected_backup(self):
        selected = self.backup_list.currentItem()
        if not selected:
            QMessageBox.warning(self, "Notice", "Please select a backup from the list first.")
            return

        bak_file = f"/etc/nixos/{selected.text()}"
        reply = QMessageBox.question(
            self, "Restore Backup",
            f"Are you sure you want to revert the system configuration to '{selected.text()}' and rebuild?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            cmd = f"/run/wrappers/bin/pkexec sh -c 'cp {bak_file} /etc/nixos/configuration.nix && nixos-rebuild switch'"
            self.run_execution(cmd, f"Restoring backup {selected.text()}...")

    def _clean_list(self, raw_str):
        raw_str = re.sub(r'#.*', '', raw_str)
        raw_str = raw_str.replace('...', '')
        return " ".join(raw_str.split())

    def clean_managed_sections(self, text, username):
        lines = text.splitlines()
        clean_lines = []
        i = 0
        while i < len(lines):
            line = lines[i]
            code_line = re.sub(r'#.*', '', line).strip()

            is_user_block = False
            if username:
                pattern = r'users\.(users|extraUsers)\.["\']?' + re.escape(username) + r'["\']?\b'
                if re.search(pattern, code_line):
                    is_user_block = True

            brace_block_starts = [
                r'^networking\.firewall\s*=\s*\{',
                r'^systemd\.services\.flatpak-cleanup\s*=\s*\{',
                r'^systemd\.timers\.flatpak-cleanup\s*=\s*\{',
                r'^systemd\.services\.flatpak-repo\s*=\s*\{',
                r'^hardware\.bluetooth\s*=\s*\{',
                r'^nix\.gc\s*=\s*\{',
                r'^system\.autoUpgrade\s*=\s*\{',
            ]

            if is_user_block or any(re.search(p, code_line) for p in brace_block_starts):
                brace_count = code_line.count('{') - code_line.count('}')
                i += 1
                while i < len(lines):
                    c_line = re.sub(r'#.*', '', lines[i])
                    brace_count += c_line.count('{') - c_line.count('}')
                    i += 1
                    if brace_count <= 0 and ('{' in line or '{' in c_line):
                        break
                continue

            if re.search(r'^environment\.systemPackages\s*=', code_line):
                bracket_count = code_line.count('[') - code_line.count(']')
                if bracket_count == 0 and ';' in code_line:
                    i += 1
                    continue
                i += 1
                while i < len(lines) and bracket_count > 0:
                    c_line = re.sub(r'#.*', '', lines[i])
                    bracket_count += c_line.count('[') - c_line.count(']')
                    i += 1
                continue

            single_line_patterns = [
                r'^services\.flatpak\.enable\s*=',
                r'^services\.printing\.enable\s*=',
                r'^boot\.loader\.systemd-boot\.configurationLimit\s*=',
                r'^services\.xserver\.videoDrivers\s*=',
                r'^hardware\.nvidia\.open\s*=',
                r'^hardware\.bluetooth\..*?=',
                r'^networking\.firewall\..*?=',
                r'^nix\.gc\..*?=',
                r'^system\.autoUpgrade\..*?=',
            ]
            if any(re.search(p, code_line) for p in single_line_patterns):
                i += 1
                continue

            clean_lines.append(line)
            i += 1

        return "\n".join(clean_lines)

    def update_config_string(self):
        user = self._clean_list(self.username_input.text())
        content = self.clean_managed_sections(self.config_content, user)

        new_blocks = []

        # 1. Unfree packages
        if self.nvidia_cb.isChecked() and "nixpkgs.config.allowUnfree" not in content:
            new_blocks.append("nixpkgs.config.allowUnfree = true;")

        # 2. Flatpak & Auto-Flathub Remote & Cleanup
        if self.flatpak_cb.isChecked():
            new_blocks.append("services.flatpak.enable = true;")

            new_blocks.append(
                'systemd.services.flatpak-repo = {\n'
                '    wantedBy = [ "multi-user.target" ];\n'
                '    path = [ pkgs.flatpak ];\n'
                '    script = "flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo";\n'
                '  };'
            )

            if self.flatpak_gc_cb.isChecked():
                new_blocks.append(
                    'systemd.services.flatpak-cleanup = {\n'
                    '    description = "Removes unused Flatpak runtimes";\n'
                    '    script = "${pkgs.flatpak}/bin/flatpak uninstall --unused -y";\n'
                    '    serviceConfig.Type = "oneshot";\n'
                    '  };\n'
                    '  systemd.timers.flatpak-cleanup = {\n'
                    '    wantedBy = [ "timers.target" ];\n'
                    '    timerConfig = { OnCalendar = "weekly"; Persistent = true; };\n'
                    '  };'
                )

        # 3. Bluetooth
        if self.bluetooth_cb.isChecked():
            new_blocks.append("hardware.bluetooth.enable = true;\n  hardware.bluetooth.powerOnBoot = true;")

        # 4. NVIDIA & Printing
        if self.nvidia_cb.isChecked():
            new_blocks.append('services.xserver.videoDrivers = [ "nvidia" ];')
            if self.nvidia_open_cb.isChecked():
                new_blocks.append("hardware.nvidia.open = true;")

        if self.printing_cb.isChecked():
            new_blocks.append("services.printing.enable = true;")

        # 5. Generation Limit, Nix GC & Auto Upgrade
        new_blocks.append(f"boot.loader.systemd-boot.configurationLimit = {self.gen_limit.value()};")

        if self.nix_gc_cb.isChecked():
            new_blocks.append(
                'nix.gc = {\n'
                '    automatic = true;\n'
                '    dates = "weekly";\n'
                '    options = "--delete-older-than 14d";\n'
                '  };'
            )

        if self.autoupgrade_cb.isChecked():
            new_blocks.append(
                'system.autoUpgrade = {\n'
                '    enable = true;\n'
                '    dates = "04:00";\n'
                '    randomizedDelaySec = "45min";\n'
                '    allowReboot = false;\n'
                '  };'
            )

        # 6. Firewall
        fw_enabled = 'true' if self.fw_cb.isChecked() else 'false'
        tcp_ports = self._clean_list(self.fw_tcp_ports.text())
        udp_ports = self._clean_list(self.fw_udp_ports.text())
        tcp_ranges = self._clean_list(self.fw_tcp_ranges.text())

        fw_lines = [f"networking.firewall.enable = {fw_enabled};"]
        if tcp_ports:
            fw_lines.append(f"networking.firewall.allowedTCPPorts = [ {tcp_ports} ];")
        if udp_ports:
            fw_lines.append(f"networking.firewall.allowedUDPPorts = [ {udp_ports} ];")
        if tcp_ranges:
            fw_lines.append(f"networking.firewall.allowedUDPPortRanges = [ {tcp_ranges} ];")
        new_blocks.append("\n  ".join(fw_lines))

        # 7. System Packages & Store Auto-Integration
        pkgs_list = self._clean_list(self.pkgs_edit.toPlainText()).split()

        if self.flatpak_cb.isChecked():
            is_kde = bool(re.search(r'desktopManager\.plasma.*\.enable\s*=\s*true', content))
            is_gnome = bool(re.search(r'desktopManager\.gnome\.enable\s*=\s*true', content))

            if is_kde and not any(p in pkgs_list for p in ["kdePackages.discover", "discover"]):
                pkgs_list.append("kdePackages.discover")
            if is_gnome and not any(p in pkgs_list for p in ["gnome-software", "gnome.gnome-software"]):
                pkgs_list.append("gnome-software")

        if pkgs_list:
            pkg_formatted = "\n    ".join(pkgs_list)
            new_blocks.append(f"environment.systemPackages = with pkgs; [\n    {pkg_formatted}\n  ];")

        # 8. User & Groups
        groups = self._clean_list(self.groups_input.text()).split()
        if user:
            groups_formatted = " ".join([f'"{g}"' for g in groups])
            new_blocks.append(
                f'users.users.{user} = {{\n'
                f'    isNormalUser = true;\n'
                f'    extraGroups = [ {groups_formatted} ];\n'
                f'  }};'
            )

        formatted_addition = "\n\n  ".join(new_blocks)
        idx = content.rfind("}")
        if idx != -1:
            return content[:idx] + f"  {formatted_addition}\n" + content[idx:]
        else:
            return content + f"\n  {formatted_addition}\n"

    def save_and_apply(self):
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        new_config = self.update_config_string()

        if not new_config:
            QMessageBox.critical(self, "Error", "Could not generate configuration.")
            return

        try:
            with open("/tmp/configuration.nix.tmp", "w") as f:
                f.write(new_config)

            cmd = (
                f"/run/wrappers/bin/pkexec sh -c '"
                f"cp /etc/nixos/configuration.nix /etc/nixos/configuration.nix.bak_{timestamp} && "
                f"cp /tmp/configuration.nix.tmp /etc/nixos/configuration.nix && "
                f"nixos-rebuild switch'"
            )
            self.run_execution(cmd, "NixOS rebuild in progress... Please enter your password if prompted.")

        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
            self.reset_ui()

    def run_execution(self, cmd, status_msg):
        self.save_btn.setEnabled(False)
        self.restore_bak_btn.setEnabled(False)
        self.status_label.setText(status_msg)
        self.progress_bar.show()

        self.worker = RebuildWorker(cmd)
        self.worker.finished_signal.connect(self.on_rebuild_finished)
        self.worker.start()

    def on_rebuild_finished(self, returncode, stderr):
        self.reset_ui()
        if returncode == 0:
            QMessageBox.information(self, "Success", "Action completed successfully!")
            self.load_config()
        else:
            QMessageBox.critical(self, "Rebuild Error", f"NixOS build failed:\n\n{stderr}")

    def reset_ui(self):
        self.save_btn.setEnabled(True)
        self.restore_bak_btn.setEnabled(True)
        self.progress_bar.hide()
        self.status_label.setText("Ready")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setDesktopFileName("LazyNix.desktop")
    editor = NixOSConfigEditor()
    editor.show()
    sys.exit(app.exec())
