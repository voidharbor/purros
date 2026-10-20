#!/bin/bash
# Sets up the purros command on this WSL machine:
#   - installs QEMU if it is missing
#   - adds you to the kvm group so QEMU can use /dev/kvm without sudo
#   - links host/purros to ~/.local/bin/purros
set -euo pipefail

HOST_DIR=$(cd "$(dirname "$(readlink -f "$0")")" && pwd)
BIN=$HOME/.local/bin

if ! command -v qemu-system-x86_64 >/dev/null || ! command -v qemu-img >/dev/null; then
	echo "installing QEMU"
	sudo apt-get install -y qemu-system-x86 qemu-utils
fi

if [ -e /dev/kvm ] && ! { [ -r /dev/kvm ] && [ -w /dev/kvm ]; }; then
	if ! id -nG "$USER" | tr ' ' '\n' | grep -qx kvm; then
		echo "adding $USER to the kvm group"
		sudo usermod -aG kvm "$USER"
	fi
fi

mkdir -p "$BIN"
chmod +x "$HOST_DIR/purros" "$HOST_DIR/vmshot.py"
ln -sfn "$HOST_DIR/purros" "$BIN/purros"
echo "linked $BIN/purros -> $HOST_DIR/purros"

case ":$PATH:" in
	*":$BIN:"*) ;;
	*) echo "note: $BIN is not on your PATH; add it in ~/.bashrc or ~/.zshrc" ;;
esac
