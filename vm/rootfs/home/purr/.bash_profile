# tty1 is the PurrOS screen; every other terminal gets a normal shell.
if [ "$(tty)" = /dev/tty1 ] && [ -z "${PURROS_SESSION:-}" ]; then
	exec /opt/purros/session.sh
fi

[ -f ~/.bashrc ] && . ~/.bashrc
