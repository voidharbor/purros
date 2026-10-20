#!/usr/bin/env bash
# Fonts and xterm.js for static/vendor, so PurrOS never needs the internet at run time.
set -euo pipefail
cd "$(dirname "$0")"
V=static/vendor
mkdir -p "$V"
get() { [ -s "$V/$2" ] || curl -fsSL "$1" -o "$V/$2"; }
get https://github.com/google/fonts/raw/main/ofl/vt323/VT323-Regular.ttf VT323-Regular.ttf
get https://github.com/google/fonts/raw/main/ofl/ibmplexmono/IBMPlexMono-Regular.ttf IBMPlexMono-Regular.ttf
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
if [ ! -s "$V/xterm.js" ]; then
  curl -fsSL https://registry.npmjs.org/@xterm/xterm/-/xterm-5.5.0.tgz | tar -xz -C "$tmp"
  cp "$tmp/package/lib/xterm.js" "$tmp/package/css/xterm.css" "$V/"
fi
if [ ! -s "$V/addon-fit.js" ]; then
  curl -fsSL https://registry.npmjs.org/@xterm/addon-fit/-/addon-fit-0.10.0.tgz | tar -xz -C "$tmp"
  cp "$tmp/package/lib/addon-fit.js" "$V/"
fi
ls -la "$V"
