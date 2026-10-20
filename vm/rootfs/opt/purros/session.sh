#!/bin/sh
# The PurrOS screen: cage (a one-app Wayland kiosk) showing Chromium on purrd's
# page. Started from ~/.bash_profile on tty1; cage runs this same script again
# with "kiosk" to set the screen size and become Chromium. Output goes to
# ~/.cache/purros/session.log so nothing ever prints on the screen.

export XDG_RUNTIME_DIR=/tmp/purr-xdg
export LIBSEAT_BACKEND=seatd
export PURROS_SESSION=1
export XKB_DEFAULT_LAYOUT=us

URL=http://127.0.0.1:7777/
PROFILE=$HOME/.cache/purros-chrome
# Screen size. QEMU's window reports its own early size (often 640x506) as the
# preferred mode, so pin it. Empty means take whatever the display prefers.
SCREEN=1280x800
EXTRA_FLAGS=""
# Optional local overrides: SCREEN, EXTRA_FLAGS="--enable-gpu-rasterization".
[ -r /etc/purros/session.conf ] && . /etc/purros/session.conf

if [ "${1:-}" = kiosk ]; then
	if [ -n "$SCREEN" ]; then
		out=$(wlr-randr 2>/dev/null | awk 'NR == 1 {print $1}')
		[ -n "$out" ] && wlr-randr --output "$out" --custom-mode "$SCREEN"
	fi
	# shellcheck disable=SC2086
	exec chromium \
		--kiosk --app="$URL" \
		--ozone-platform=wayland \
		--user-data-dir="$PROFILE" \
		--no-first-run --no-default-browser-check \
		--noerrdialogs --disable-infobars \
		--disable-session-crashed-bubble --hide-crash-restore-bubble \
		--disable-features=Translate,MediaRouter,OptimizationHints,AutofillServerCommunication \
		--disable-background-networking --disable-component-update --disable-sync \
		--disable-breakpad --disable-pinch --password-store=basic \
		--check-for-update-interval=31536000 \
		--autoplay-policy=no-user-gesture-required \
		--overscroll-history-navigation=0 \
		$EXTRA_FLAGS
fi

mkdir -p "$XDG_RUNTIME_DIR" && chmod 0700 "$XDG_RUNTIME_DIR"
LOGDIR=$HOME/.cache/purros
mkdir -p "$LOGDIR"
[ -f "$LOGDIR/session.log" ] && mv -f "$LOGDIR/session.log" "$LOGDIR/session.log.old"
exec >"$LOGDIR/session.log" 2>&1

echo "session start $(date '+%F %T')"

# Wait for purrd, up to 30 s. After that Chromium starts anyway and its error
# page keeps retrying on its own.
n=0
until wget -q -T 1 -O /dev/null "${URL}health"; do
	n=$((n + 1))
	[ "$n" -ge 150 ] && { echo "purrd not answering, starting anyway"; break; }
	sleep 0.2
done
echo "purrd up after ${n} tries ($(cut -d' ' -f1 /proc/uptime)s since boot)"

while :; do
	# A hard power-off leaves Chromium thinking it crashed; clear that so no
	# "restore pages" bubble shows up.
	for p in "$PROFILE/Default/Preferences" "$PROFILE/Local State"; do
		[ -f "$p" ] && sed -i 's/"exit_type":"Crashed"/"exit_type":"Normal"/; s/"exited_cleanly":false/"exited_cleanly":true/' "$p"
	done
	dbus-run-session -- cage -s -- "$0" kiosk
	echo "cage exited ($?) at $(date '+%T'), restarting"
	sleep 1
done
