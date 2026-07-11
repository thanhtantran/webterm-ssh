"""
server.py

Backend Flask phục vụ trang xterm.js và xử lý WebSocket, cầu nối tới
class_v2.ssh_terminal.SSHTerminal (Paramiko SSH client).

Chạy:
    pip install -r requirements.txt
    python3 server.py

Mặc định lắng nghe tại 0.0.0.0:7681
"""

import json
import os
import sys
import threading
import traceback

from flask import Flask, send_from_directory
from flask_sock import Sock
from simple_websocket import ConnectionClosed

from class_v2.ssh_terminal import SSHTerminal

HOST = "0.0.0.0"
PORT = 7681

# --- Thông tin SSH cố định để tự động đăng nhập (không qua form web) ---
SSH_HOST = os.environ.get("WEBTERM_SSH_HOST", "127.0.0.1")
SSH_PORT = int(os.environ.get("WEBTERM_SSH_PORT", "22"))
SSH_USER = os.environ.get("WEBTERM_SSH_USER", "orangepi")
SSH_PASS = os.environ.get("WEBTERM_SSH_PASS", "orangepi")


def log(msg: str) -> None:
    """In log ngay lập tức (không bị buffer khi chạy qua nohup/systemd)."""
    print(msg, flush=True)


app = Flask(__name__, static_folder="static")
app.config["SOCK_SERVER_OPTIONS"] = {"ping_interval": 25}
sock = Sock(app)


@app.route("/")
def index():
    log("[HTTP] GET /  -- client đang tải trang index.html")
    return send_from_directory(app.static_folder, "index.html")


@app.route("/health")
def health():
    """Route kiểm tra nhanh: mở http://<ip>:7681/health trên trình duyệt
    máy khác để xác nhận server có nhận được request qua mạng LAN hay không,
    tách biệt hẳn khỏi WebSocket."""
    log("[HTTP] GET /health -- OK, server đang chạy và nhận được request")
    return {"status": "ok", "ssh_target": f"{SSH_USER}@{SSH_HOST}:{SSH_PORT}"}


@sock.route("/ws")
def ws_handler(ws):
    log("[WS] Có client mở kết nối WebSocket tới /ws")

    terminal = SSHTerminal()
    terminal._ws = ws
    connected = False

    try:
        log(f"[WS] Đang thử SSH tới {SSH_USER}@{SSH_HOST}:{SSH_PORT} ...")
        result = terminal.set_attr({
            "host": SSH_HOST,
            "port": SSH_PORT,
            "username": SSH_USER,
            "password": SSH_PASS,
        })
        log(f"[WS] Kết quả SSH connect: {result}")

        if result["status"] == 0:
            connected = True
            ws.send(json.dumps({"type": "status", "status": "connected"}))
            log("[WS] Đã gửi status=connected cho client")
            threading.Thread(target=terminal.recv_loop, daemon=True).start()
            threading.Thread(target=terminal.heartbeat_loop, daemon=True).start()
        else:
            ws.send(json.dumps(
                {"type": "status", "status": "error", "msg": result["msg"]}
            ))
            log(f"[WS] SSH lỗi, đã báo cho client: {result['msg']}")
            terminal.close()
            return

        while True:
            message = ws.receive()
            if message is None:
                log("[WS] Client đóng kết nối (receive() trả None)")
                break

            try:
                payload = json.loads(message)
            except json.JSONDecodeError:
                continue

            msg_type = payload.get("type")

            if msg_type == "input" and connected:
                terminal.send_data(payload.get("data", ""))

            elif msg_type == "resize" and connected:
                terminal.resize(payload.get("cols", 80), payload.get("rows", 24))

    except ConnectionClosed:
        # Bình thường: xảy ra khi người dùng đóng tab / tắt trình duyệt /
        # mất mạng. Không phải lỗi của server, không cần in traceback.
        log("[WS] Client đã ngắt kết nối (đóng tab/trình duyệt) — bình thường")
    except Exception:
        log("[WS] LỖI THỰC SỰ trong ws_handler:")
        log(traceback.format_exc())
    finally:
        terminal.close()
        log("[WS] Đã đóng phiên terminal")


if __name__ == "__main__":
    log(f"Browser Terminal (SSH/Paramiko) đang chạy tại: http://{HOST}:{PORT}")
    log(f"Tự động đăng nhập SSH: {SSH_USER}@{SSH_HOST}:{SSH_PORT}")
    log(f"Kiểm tra nhanh: http://{HOST}:{PORT}/health")
    try:
        app.run(host=HOST, port=PORT, threaded=True)
    except OSError as e:
        log(f"KHÔNG THỂ khởi động server: {e}")
        log("Có thể cổng 7681 đã bị chiếm bởi tiến trình khác "
            "(kiểm tra bằng: sudo ss -tlnp | grep 7681)")
        sys.exit(1)
