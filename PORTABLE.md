# CarbonAgent Portable (Windows)

This folder contains the Windows **portable** build of CarbonAgent. It runs without an installer and is intended to live on a USB drive or any folder you can write to.

## What's in the ZIP

Extract `CarbonAgent-1.0.0-x64.zip` anywhere. You will see:

- `CarbonAgent.exe` — double-click to launch the app
- `resources/` — Electron runtime and embedded Python
- `data/` — created automatically on first run; holds your auth, sessions, database, uploads, and memory

## USB usage

1. Extract the ZIP to a folder on your USB drive.
2. Run `CarbonAgent.exe`.
3. The first run creates a `data/` folder next to `CarbonAgent.exe` and prints a temporary admin password to the built-in console.
4. Keep the `data/` folder with `CarbonAgent.exe`. That folder is your entire CarbonAgent state; if you copy or move the folder, your data moves with it.

## Switching back to an installed copy

The regular installer build (`app Setup 1.0.0.exe`) stores data in `%APPDATA%` / `%LOCALAPPDATA%` instead of next to the executable. The two editions do not share state; treat the portable `data/` folder as your portable workspace.

## Limitations on Windows

- Bash tools, background jobs, SSH commands, and Cookbook model serving still need **Git for Windows** (`bash.exe`) on the host. The portable bundle does not include Git.
- Node.js/npm and a Chromium-based browser are needed only for optional MCP servers such as the built-in browser agent; the core chat UI works without them.
- No administrator rights are required to run the portable edition, but UAC may prompt if you run it from a protected folder such as `C:\Program Files`.

## Building the portable edition

From a checkout with Node.js:

```bash
npm install
npm run embed-python   # prepares build/python/ for Windows
npm run build:win      # produces dist/CarbonAgent-1.0.0-x64.zip
```

If you only need a folder that can be zipped manually, build the unpacked target from `dist/win-unpacked/` instead.
