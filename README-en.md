# webterm-ssh

[Tiếng Việt](README.md)

Terminal SSH right in your browser — open the device's IP and you get a command line
for the device (Orange Pi, Raspberry Pi, any Linux server) without installing
PuTTY/Termius or an app. It also runs on mobile.

Automatically logs in via SSH (default `orangepi` / `orangepi`), no login form —
open the page and you are taken straight to the terminal.

## Architecture

```
Chrome / Edge / Safari (xterm.js)
        │  WebSocket
        ▼
   Flask + flask-sock
        │  Paramiko (SSH client)
        ▼
   sshd (127.0.0.1:22)
        │
        ▼
    /bin/bash
```

Unlike forking a PTY and running `bash` directly on the server, `webterm-ssh` truly
SSHs into the device itself (similar to how aaPanel/1Panel does) — so it preserves
all the usual SSH authentication, permissions, and logs.

## Quick demo

Open a browser: `http://<device-ip>:7681` → you go straight into the terminal, run
commands as with a normal SSH session, and resizing the browser terminal window
will resize the remote terminal accordingly (fully supports `vim`, `htop`, `less`, ...).

## Installation

### Option 1 — Automatic install, run as a system service (recommended)

```bash
git clone https://github.com/<your-username>/webterm-ssh.git
cd webterm-ssh
sudo bash install.sh
```

The `install.sh` script will automatically:
1. Create a virtualenv (`./venv`) and install required packages
2. Generate a `systemd` service file with correct paths + your current user
3. Enable the service and configure it to start at boot

After the script finishes it prints the access URL, for example:
```
✅ Installation successful!
   Access: http://192.168.88.5:7681
```

To change the default automatic SSH login credentials `orangepi/orangepi`:
```bash
sudo WEBTERM_SSH_USER=myuser WEBTERM_SSH_PASS=mypass bash install.sh
```

### Option 2 — Manual install, run by hand (for testing/development)

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 server.py
```

By default the server listens on `0.0.0.0:7681` and automatically SSHs to
`127.0.0.1:22` using `orangepi/orangepi`. Change configuration using environment variables:

```bash
WEBTERM_SSH_HOST=127.0.0.1 \
WEBTERM_SSH_PORT=22 \
WEBTERM_SSH_USER=orangepi \
WEBTERM_SSH_PASS=orangepi \
python3 server.py
```

## Project structure

```
webterm-ssh/
├── server.py                  # Flask app + WebSocket route /ws + route /health
├── class_v2/
│   ├── __init__.py
│   └── ssh_terminal.py        # class SSHTerminal — Paramiko SSH client
├── static/
│   ├── index.html             # xterm.js UI
│   └── vendor/                # xterm.js bundled locally (NO CDN dependency)
│       ├── xterm.js
│       ├── xterm.css
│       └── xterm-addon-fit.js
├── requirements.txt
├── install.sh                 # Automatic install script + create systemd service
├── webterm-ssh.service        # Sample systemd file (reference/manual install)
└── README.md
```

## Service management (after installing with `install.sh`)

```bash
sudo systemctl status webterm-ssh     # check status
sudo systemctl restart webterm-ssh    # restart
sudo systemctl stop webterm-ssh       # stop
sudo journalctl -u webterm-ssh -f     # follow logs in real time
```

### Manually install the service file (if not using install.sh)

```bash
sudo cp webterm-ssh.service /etc/systemd/system/webterm-ssh.service
sudo nano /etc/systemd/system/webterm-ssh.service   # edit User + paths for your machine
sudo systemctl daemon-reload
sudo systemctl enable --now webterm-ssh
```

## WebSocket protocol

Endpoint: `ws://<ip>:7681/ws` — each message is JSON.

**Client → Server:**
```json
{"type": "input", "data": "ls -la\n"}
{"type": "resize", "cols": 120, "rows": 32}
```

**Server → Client:**
```json
{"type": "status", "status": "connected"}
{"type": "status", "status": "error", "msg": "..."}
{"type": "output", "data": "..."}
```

The server automatically SSHs as soon as the WebSocket opens — there is no
separate `connect` step from the client.

## Troubleshooting

### The page only shows "Connecting to SSH..." and never changes

This indicates the WebSocket never reached the server — the most common cause
is the browser failing to load `xterm.js` (for example if you changed the code
and pointed it to a CDN but the device has no Internet). Check:

1. Open DevTools (F12) → **Console**: any red errors (for example
   `Terminal is not defined`)?
2. **Network** tab → filter **JS**: did `xterm.js`, `xterm-addon-fit.js` load with
   status 200? This repo bundles the files locally in `static/vendor/`, so no
   Internet is required — if you see those files loading from a CDN it means
   `index.html` was modified and needs to be changed back to `/static/vendor/...`.
3. Test plain HTTP first, separate from WebSocket:
   `http://<ip>:7681/health` — it should return JSON like `{"status":"ok",...}`.
   If this route also doesn't load, it's a network/firewall problem, not code.

### "Wrong username or password" error

- Check whether sshd allows password authentication:
  ```bash
  grep -i PasswordAuthentication /etc/ssh/sshd_config
  ```
  If it says `PasswordAuthentication no`, change it to `yes` and then:
  ```bash
  sudo systemctl restart ssh
  ```
- Verify the account/password by SSHing manually:
  ```bash
  ssh orangepi@127.0.0.1
  ```

### Port 7681 is already in use

```bash
sudo ss -tlnp | grep 7681
```
If an old process holds the port, stop it or change `PORT` in `server.py`.

### No logs on console

`server.py` prints logs with `print(..., flush=True)` so output is unbuffered when
run via `nohup`/`systemd`. If `journalctl -u webterm-ssh -f` shows nothing, check
whether the service is actually running:
```bash
sudo systemctl status webterm-ssh
```

## Security — read before exposing to the Internet

⚠️ This application gives full shell access to your device from the browser.
Before exposing it outside your LAN, consider:

- **Do not expose directly to the Internet** without HTTPS/WSS + authentication.
  This is equivalent to opening passwordless SSH over HTTP to anyone who can
  reach port 7681.
- Change the default password `orangepi/orangepi` — this is a common default
  account for Orange Pi boards and should not be left unchanged when exposed.
- If remote access is required, put it behind a reverse proxy (Nginx/Caddy) with
  HTTPS and limit by IP or add authentication (Basic Auth, VPN, Tailscale...),
  instead of exposing port 7681 directly to the WAN.
- Flask's dev server (`app.run()`) is only suitable for local LAN/dev use. For a
  production setup, consider running under `gunicorn` with a WebSocket-capable
  worker (e.g., `gevent-websocket`).

## License

MIT
