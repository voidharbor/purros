#!/bin/bash
# Builds the PurrOS VM disk: Alpine Linux, cage + Chromium, and the PurrOS app.
#
#   sudo vm/build.sh              full build from scratch -> vm/out/purros.qcow2
#   sudo vm/build.sh --app-only   refresh /opt/purros inside the existing disk
#
# Downloads are cached in vm/cache. A full build replaces the disk, including
# anything saved inside it. --app-only patches the disk in place (the home
# folder and settings survive) and takes a few seconds; the VM must be off.
#
# Environment: PURROS_DISK (default vm/out/purros.qcow2), ALPINE_MIRROR.
set -euo pipefail

HERE=$(cd "$(dirname "$(readlink -f "$0")")" && pwd)
REPO=$(dirname "$HERE")
CACHE=$HERE/cache
OUT=$HERE/out
WORK=$OUT/.work
MNT=$WORK/root
DISK=${PURROS_DISK:-$OUT/purros.qcow2}

ALPINE=v3.24
MIRROR=${ALPINE_MIRROR:-https://dl-cdn.alpinelinux.org/alpine}
ARCH=x86_64
SIZE=6G

PACKAGES=(
	alpine-base linux-lts linux-firmware-none mkinitfs syslinux e2fsprogs
	eudev eudev-openrc udev-init-scripts udev-init-scripts-openrc
	seatd seatd-openrc cage wlr-randr libinput xkeyboard-config
	chromium mesa-dri-gallium mesa-egl mesa-gbm mesa-gles font-dejavu
	python3 py3-aiohttp
	bash nano vim htop less file coreutils findutils grep util-linux procps-ng
	iproute2 iputils tzdata ca-certificates dbus dbus-openrc doas doas-sudo-shim
	zip unzip curl wget
	alsa-utils alsa-lib agetty socat qemu-guest-agent qemu-guest-agent-openrc
)

# OpenRC runlevels. udev replaces Alpine's default mdev.
RUNLEVEL_SYSINIT=(devfs dmesg udev udev-trigger)
RUNLEVEL_BOOT=(root fsck localmount hwclock modules sysctl hostname bootmisc networking)
RUNLEVEL_DEFAULT=(seatd dbus local purrd purrfwd qemu-guest-agent)
RUNLEVEL_SHUTDOWN=(killprocs savecache mount-ro)

CMDLINE="rootfstype=ext4 modules=ext4 console=ttyS0,115200 quiet loglevel=3 vt.global_cursor_default=0 net.ifnames=0"

log() { printf '\033[1;32m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" = 0 ] || die "run as root: sudo $0 $*"
OWNER="${SUDO_UID:-0}:${SUDO_GID:-0}"

LOOP=""
QSD_PID=""
RAW=""
cleanup() {
	set +e
	if mountpoint -q "$MNT" 2>/dev/null; then
		umount -R "$MNT" 2>/dev/null || umount -R -l "$MNT"
	fi
	if [ -n "$LOOP" ]; then
		losetup -d "$LOOP" 2>/dev/null
		LOOP=""
	fi
	if [ -n "$QSD_PID" ] && kill -0 "$QSD_PID" 2>/dev/null; then
		kill "$QSD_PID"
		for _ in $(seq 50); do kill -0 "$QSD_PID" 2>/dev/null || break; sleep 0.1; done
	fi
	QSD_PID=""
	[ -n "$RAW" ] && rm -f "$RAW"
	rm -f "$WORK/disk.fuse" "$WORK/qsd.pid"
}
trap cleanup EXIT
trap 'exit 130' INT TERM

need_host_tools() {
	local missing=()
	command -v qemu-img >/dev/null || missing+=(qemu-utils)
	command -v qemu-storage-daemon >/dev/null || missing+=(qemu-utils)
	command -v mkfs.ext4 >/dev/null || missing+=(e2fsprogs)
	command -v sfdisk >/dev/null || missing+=(fdisk)
	command -v losetup >/dev/null || missing+=(mount)
	command -v curl >/dev/null || missing+=(curl)
	command -v rsync >/dev/null || missing+=(rsync)
	if [ ${#missing[@]} -gt 0 ]; then
		log "installing host tools: ${missing[*]}"
		DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "${missing[@]}"
	fi
}

chroot_run() {
	chroot "$MNT" /usr/bin/env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin HOME=/root /bin/sh -c "$1"
}

attach() { # attach <image file>: loop device with partitions, sets LOOP
	LOOP=$(losetup -P --show -f "$1")
	for _ in $(seq 50); do [ -b "${LOOP}p1" ] && return 0; sleep 0.1; done
	die "partition ${LOOP}p1 never showed up"
}

mount_root() {
	mkdir -p "$MNT"
	mount "${LOOP}p1" "$MNT"
	mount --make-private "$MNT"
}

# /opt/purros: the app plus the session script, owned by root, readable by all.
install_app() {
	local d
	mkdir -p "$MNT/opt/purros"
	for d in purrd static; do
		if [ -d "$REPO/app/$d" ]; then
			rsync -rlt --delete --chown=0:0 --chmod=u+rwX,go+rX,go-w \
				--exclude __pycache__ --exclude '*.pyc' \
				"$REPO/app/$d/" "$MNT/opt/purros/$d/"
		fi
	done
	install -o 0 -g 0 -m 0755 "$HERE/rootfs/opt/purros/session.sh" "$MNT/opt/purros/session.sh"
	{
		echo "built $(date '+%F %T %Z')"
		git -C "$REPO" rev-parse --short HEAD 2>/dev/null || echo "no commit"
	} >"$MNT/opt/purros/BUILD"
	chroot_run "python3 -m compileall -q /opt/purros/purrd" >/dev/null || log "warning: app has Python syntax errors"
}

# System files from vm/rootfs (everything except the home folder).
install_overlay() {
	rsync -rlt --chown=0:0 --chmod=u+rwX,go+rX,go-w --exclude /home \
		"$HERE/rootfs/" "$MNT/"
	chmod 0600 "$MNT/etc/doas.d/purr.conf"
}

app_only() {
	[ -f "$DISK" ] || die "no disk at $DISK, run a full build first: sudo $0"
	mkdir -p "$WORK"
	: >"$WORK/disk.fuse"
	log "opening $DISK"
	# qemu-storage-daemon shows the qcow2 as a raw file over FUSE, so it can be
	# loop-mounted and edited in place. It refuses if the VM has the disk open.
	if ! qemu-storage-daemon \
		--blockdev "driver=file,node-name=file0,filename=$DISK" \
		--blockdev "driver=qcow2,node-name=disk0,file=file0" \
		--export "type=fuse,id=exp0,node-name=disk0,mountpoint=$WORK/disk.fuse,writable=on" \
		--pidfile "$WORK/qsd.pid" --daemonize; then
		die "could not open the disk (is PurrOS running? stop it with: purros --stop)"
	fi
	QSD_PID=$(cat "$WORK/qsd.pid")
	attach "$WORK/disk.fuse"
	mount_root
	log "refreshing /opt/purros"
	install_overlay
	install_app
	local stamp
	stamp=$(head -1 "$MNT/opt/purros/BUILD")
	sync
	umount "$MNT"
	losetup -d "$LOOP"; LOOP=""
	kill "$QSD_PID"
	for _ in $(seq 100); do kill -0 "$QSD_PID" 2>/dev/null || break; sleep 0.1; done
	QSD_PID=""
	log "app refreshed in $DISK ($stamp)"
}

fetch_apk_static() {
	local f=$CACHE/apk.static ver tmp
	[ -x "$f" ] && return 0
	log "downloading apk-tools-static"
	tmp=$(mktemp -d "$WORK/apk.XXXXXX")
	curl -fsSL "$MIRROR/$ALPINE/main/$ARCH/APKINDEX.tar.gz" | tar -xzO APKINDEX >"$tmp/APKINDEX"
	ver=$(awk '/^P:apk-tools-static$/ {f=1; next} f && /^V:/ {print substr($0, 3); exit}' "$tmp/APKINDEX")
	[ -n "$ver" ] || die "apk-tools-static not found in the Alpine index"
	curl -fsSL -o "$tmp/apk.apk" "$MIRROR/$ALPINE/main/$ARCH/apk-tools-static-$ver.apk"
	tar -xzf "$tmp/apk.apk" -C "$tmp" sbin/apk.static 2>/dev/null
	install -m 0755 "$tmp/sbin/apk.static" "$f"
	rm -rf "$tmp"
}

full_build() {
	local t0=$SECONDS uuid kver svc lvl
	mkdir -p "$CACHE/apk" "$OUT" "$WORK"
	chown "$OWNER" "$CACHE" "$OUT"
	fetch_apk_static

	log "creating a $SIZE disk"
	RAW=$WORK/purros.raw
	rm -f "$RAW"
	truncate -s "$SIZE" "$RAW"
	printf 'label: dos\nstart=2048, type=83, bootable\n' | sfdisk -q "$RAW"
	attach "$RAW"
	uuid=$(cat /proc/sys/kernel/random/uuid)
	# No 64bit: extlinux cannot boot from 64bit ext4.
	mkfs.ext4 -q -F -L purros -U "$uuid" -O ^64bit "${LOOP}p1"
	mount_root

	log "installing Alpine $ALPINE"
	mkdir -p "$MNT/etc/apk" "$MNT/etc/mkinitfs"
	printf '%s\n' "$MIRROR/$ALPINE/main" "$MIRROR/$ALPINE/community" >"$MNT/etc/apk/repositories"
	echo 'features="base ext4 kms virtio"' >"$MNT/etc/mkinitfs/mkinitfs.conf"
	local apk=("$CACHE/apk.static" --root "$MNT" --arch "$ARCH" --cache-dir "$CACHE/apk" --cache-packages --no-progress)
	# Keys come over HTTPS first; every package after that is signature-checked.
	"${apk[@]}" --initdb -U --allow-untrusted add alpine-keys >/dev/null
	mkdir -p "$MNT/proc" "$MNT/sys" "$MNT/dev"
	mount -t proc proc "$MNT/proc"
	mount -t sysfs sys "$MNT/sys"
	mount --bind /dev "$MNT/dev"
	"${apk[@]}" add "${PACKAGES[@]}" | grep -vE '^\( *[0-9]+/[0-9]+\) (Installing|Purging)' || true
	[ -f "$MNT/boot/vmlinuz-lts" ] || die "kernel missing after apk add"
	chown -R "$OWNER" "$CACHE"

	log "configuring the system"
	echo purros >"$MNT/etc/hostname"
	cat >"$MNT/etc/hosts" <<-'EOF'
		127.0.0.1	localhost localhost.localdomain
		127.0.1.1	purros
		::1		localhost localhost.localdomain
	EOF
	cat >"$MNT/etc/fstab" <<-EOF
		UUID=$uuid	/	ext4	rw,relatime	0 1
		tmpfs	/tmp	tmpfs	nosuid,nodev,mode=1777	0 0
	EOF
	ln -sf /usr/share/zoneinfo/America/New_York "$MNT/etc/localtime"
	echo America/New_York >"$MNT/etc/timezone"
	: >"$MNT/etc/motd"
	sed -i 's/^root:[^:]*:/root:*:/' "$MNT/etc/shadow"
	install_overlay

	chroot_run "addgroup -S seat 2>/dev/null; adduser -D -u 1000 -h /home/purr -s /bin/bash -g PurrOS purr" >/dev/null
	for g in video input audio seat wheel; do chroot_run "addgroup purr $g"; done

	for lvl in sysinit boot default shutdown; do
		local -n list="RUNLEVEL_${lvl^^}"
		mkdir -p "$MNT/etc/runlevels/$lvl"
		for svc in "${list[@]}"; do
			[ -x "$MNT/etc/init.d/$svc" ] || die "no init script for $svc"
			ln -sf "/etc/init.d/$svc" "$MNT/etc/runlevels/$lvl/$svc"
		done
		unset -n list
	done

	log "home folder"
	mkdir -p "$MNT/home/purr"/{Documents,Downloads,Music,Pictures,Videos}
	rsync -rlt "$HERE/rootfs/home/purr/" "$MNT/home/purr/"
	[ -d "$HERE/samples" ] && rsync -rlt "$HERE/samples/" "$MNT/home/purr/"
	chown -R 1000:1000 "$MNT/home/purr"
	find "$MNT/home/purr" -type d -exec chmod g-s {} +
	chmod 0750 "$MNT/home/purr"

	log "installing PurrOS"
	install_app

	log "boot loader"
	kver=$(basename "$(ls -d "$MNT"/lib/modules/*-lts | head -1)")
	chroot_run "mkinitfs -c /etc/mkinitfs/mkinitfs.conf $kver" >/dev/null
	cat >"$MNT/boot/extlinux.conf" <<-EOF
		DEFAULT purros
		PROMPT 0
		TIMEOUT 0
		LABEL purros
		  LINUX /boot/vmlinuz-lts
		  INITRD /boot/initramfs-lts
		  APPEND root=UUID=$uuid $CMDLINE
	EOF
	# Keep apk upgrades inside the VM from rewriting our extlinux.conf.
	sed -i 's/^disable_trigger=.*/disable_trigger=1/' "$MNT/etc/update-extlinux.conf"
	chroot_run "extlinux --install /boot" >/dev/null 2>&1 || die "extlinux --install failed"
	dd if="$MNT/usr/share/syslinux/mbr.bin" of="$LOOP" bs=440 count=1 conv=notrunc status=none

	df -h "$MNT" | awk 'NR==2 {print "    root filesystem: " $3 " used of " $2}'
	sync
	umount -R "$MNT"
	losetup -d "$LOOP"; LOOP=""

	log "converting to qcow2"
	qemu-img convert -c -O qcow2 -o compression_type=zstd -m 16 -W "$RAW" "$DISK.tmp"
	mv -f "$DISK.tmp" "$DISK"
	chown "$OWNER" "$DISK"
	rm -f "$RAW"; RAW=""
	log "built $DISK ($(du -h "$DISK" | cut -f1)) in $((SECONDS - t0)) s"
}

need_host_tools
case "${1:-}" in
	"") full_build ;;
	--app-only) app_only ;;
	-h|--help) sed -n '2,11p' "$0" | sed 's/^# \{0,1\}//' ;;
	*) die "unknown option $1 (try --help)" ;;
esac
