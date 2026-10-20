# PurrOS design

2026-10-20. Josh approved the look and the cat in chat ("nothing go for it") and handed the remaining calls to me. Every line marked **(my call)** is mine, not his.

## What it is

A small, mostly text operating system with the cozy feel of an old terminal computer, for people who have never used a terminal and for experts alike. You type plain words ("show all files") or any Windows, Linux or Mac command, and it does the thing. It makes pictures the way Jarvis does. It runs in a VM. Its mascot is a small pixel cat that acts out what the computer is doing. Terry Davis and TempleOS are the inspiration: one person's whole computer, everything on screen live and tappable.

## Josh's words (decided)

- "show all files" lists files and folders.
- Understands Windows, Linux and Mac commands alike.
- Generates images like Jarvis does.
- Runs in a VM.
- Cute name ending in OS, cute animated character like the Claude Code critter: **PurrOS**, the cat.
- Green by default, theme styler in the OS settings, very light scan lines and glow.
- Animated icon that changes with what you are doing, small and uninvasive.
- Minimalist UI but capable: opens pictures, videos, software.
- For both his own PC and other people ("Both maybe").
- On launch, logged into the user account, it lists the current directory and the cat says hello ("make sure it lists the current directory when launched and logged into user account and the cat says hello").
- Approved look: mockup 2 (https://claude.ai/artifact/74AwyH4SDdMzphHzoeMsr4), PurrOS cat, ten moods.

## Goals

1. Boots in a VM straight into the PurrOS screen. No login prompt, no boot text, no desktop.
2. Plain words and real commands from any of the three systems land in the same place. A dim line under each answer shows the real command it ran.
3. Every file and folder name on screen is tappable. Pictures, videos, music, text and PDFs open inline in the stream.
4. "draw ..." makes a picture with klein on the PC GPU and saves it to Pictures.
5. Interactive programs (nano, vim, htop, python) open in an inline terminal pane inside the stream.
6. The cat lives in the top left corner at 32 px with one status word, and moves through idle, listening, thinking, working, searching, drawing, playing, done, oops and sleeping.
7. Themes phosphor, amber, ice, paper; glow off, light, more; font pixel or clean. Saved across reboots.

## Non-goals (v1)

- A kernel or OS written from scratch. (my call: Linux underneath, our own everything on top. A from-scratch OS is years; this is the TempleOS feeling, not its code.)
- Windowed graphical apps (Firefox, GIMP). "Software" in v1 means terminal programs and the built-in viewers.
- Running on bare metal or as a Windows installer.
- Networking beyond what the VM gives (no Wi-Fi setup screens).

## Anti-goals

- Anything that looks like a normal Linux desktop or shows boot text.
- Deleting something without asking. Destroying data because the brain guessed.
- A mascot that gets in the way (pop-ups, speech bubbles over the text).
- Needing the internet or a paid service to work at home.

## How it gets made

All **(my call)** unless noted.

- **Base:** Alpine Linux 3.24 (small, boots in seconds), kernel linux-lts. Kernel and service messages go to the serial port so the screen stays black until PurrOS appears.
- **Screen:** user `purr` autologs in on tty1 and runs `cage` (a one-app Wayland kiosk) with Chromium in kiosk mode pointed at the local PurrOS page. Reason: the approved mockup is HTML and canvas, so what Josh saw is exactly what boots, and Chromium plays video, shows PDFs and renders the glow for free.
- **purrd:** a Python 3 + aiohttp service on 127.0.0.1:7777 inside the VM. Serves the page and a WebSocket. Runs commands, reads files, talks to the brain and the picture maker, keeps settings in `~/.config/purros/settings.json`.
- **Understanding input** goes in this order:
  1. PurrOS words: help, clear, settings, theme, glow, font, about.
  2. The phrasebook: a table of plain-English patterns and Windows cmd, PowerShell, Mac and Linux commands mapped to built-in actions (list, go to, open, play, copy, move, rename, delete, make folder, find, whoami, date, disk space, memory, network, processes, edit, shutdown, restart). No AI needed, works with the brain offline. A command from another system gets one dim line ("dir is the windows way. same list:").
  3. A real Linux command (first word is a program on PATH): run it.
  4. Anything else goes to the brain, which answers with JSON: something to say, a Linux command to run, or a picture to draw.
- **Safety:** delete always moves to a Trash folder, never `rm`; "empty trash" asks first. Brain-proposed commands run directly only when read-only (ls, cat, grep, du, df, ps, ...); anything that changes something shows the exact command with yes/no first. Typed commands from experts run directly except a short dangerous list (rm -rf, dd, mkfs, shutdown, ...), which asks.
- **Not found:** suggest the closest file name ("There's a taxes-2025.pdf in Documents. Want that one?").
- **Brain (swappable):** settings hold a kind (`ollama` or `openai`), URL, model and optional key. Default at home: Ollama on the PC at `http://10.0.2.2:11434` (QEMU's address for the host), model `jarvis-ornith-ctx131072`, the same tag `ai` and Jarvis use so they never evict each other. Thinking off for speed. Anyone else points it at their own OpenAI-compatible server or key. When the brain is down (the game gate kills Ollama), PurrOS says so and the phrasebook keeps working.
- **Pictures:** `purr-host`, a tiny helper in WSL on 127.0.0.1:7790, runs Jarvis's own `~/local-ai/bin/mockup.py ... --managed` (it swaps the text model out, starts ComfyUI, renders with FLUX.2 klein 4B, releases the GPU). The VM reaches it at 10.0.2.2:7790. Quality mode by default (Josh prefers quality), "quick" in settings. Other people can pick an OpenAI-compatible images endpoint instead.
- **VM:** QEMU with KVM inside WSL, window through WSLg, 4 cores, 4 GB RAM, virtio disk, net, GPU and tablet. A `purros` command starts purr-host and the VM. A Windows Start menu and desktop shortcut with a cat icon runs it.
- **Image build:** `vm/build.sh` (sudo, in WSL) builds a raw disk with apk.static, installs extlinux, copies the app to `/opt/purros`, converts to `purros.qcow2`. Reproducible from the repo.
- **Fonts and libraries** (VT323, IBM Plex Mono, xterm.js) are copied into the image at build time. Nothing loads from the internet at run time.
- **Home folder:** Documents, Downloads, Music, Pictures, Videos with a few samples (the Codex cabin, a short sunset video, notes.txt) so the first "show all files" has something to show.

## Moods (from the approved mockup)

| When | Mood | Status word |
|---|---|---|
| nothing happening | idle | ready |
| typing | listening | listening |
| waiting on the brain | thinking | thinking |
| running a command | working | working |
| listing or finding files | searching | looking |
| making a picture | drawing | drawing |
| video or music playing | playing | playing |
| picture saved, long job finished | done | done |
| error, not found | oops | hmm |
| 45 s with no input (my call; the mockup used 12 s for the demo) | sleeping | napping |
| boot, then about 2.6 s on the main screen (Josh's ask) | hello (waves a paw) | hello |

## Left to the builder

Exact phrasebook coverage beyond the list above, wording of messages (lowercase, short, dry, the mockup's voice), the boot animation, audio plumbing, how settings look inside the stream.

## Success

Josh double-clicks PurrOS on the PC, the cat appears in a few seconds, and "show all files", "dir", "open cabin", "play beach-sunset.mp4", "draw a cozy cabin in the snow at night", "edit notes.txt" and "delete grocery-list.txt" all work the way the mockup promised.
