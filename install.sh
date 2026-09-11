#!/usr/bin/env bash
set -e

BIN_DIR="$HOME/.local/bin"
APP_DIR="$HOME/.local/share/applications"
ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"

mkdir -p "$BIN_DIR" "$APP_DIR"
mkdir -p "$ICON_DIR"
cp icon.svg "$ICON_DIR/lazynix.svg"

cp lazynix.py "$BIN_DIR/lazynix.py"
chmod +x "$BIN_DIR/lazynix.py"

cat <<EOF > "$APP_DIR/LazyNix.desktop"
[Desktop Entry]
Type=Application
Name=LazyNix Config Editor
Comment=Set NixOS Configuration
Exec=$BIN_DIR/lazynix.py
Icon=nixos
Terminal=false
Categories=System;Settings;
EOF

chmod +x "$APP_DIR/LazyNix.desktop"

echo "Done! LazyNix is installed and ready"
