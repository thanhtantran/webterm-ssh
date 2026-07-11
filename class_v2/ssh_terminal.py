"""
class_v2/ssh_terminal.py

Class SSHTerminal: kết nối SSH tới local server bằng Paramiko,
đọc/ghi dữ liệu giữa SSH channel và WebSocket client.

Kiến trúc:
    Browser (xterm.js)
        │ WebSocket
        ▼
    SSHTerminal.run()
        │ Paramiko (SSH)
        ▼
    sshd (mặc định 127.0.0.1:22)
        │
        ▼
    /bin/bash (shell channel)
"""

import io
import json
import select
import socket
import threading
import time

import paramiko


class SSHTerminal:
    """
    Quản lý một phiên SSH gắn với một WebSocket client.
    Mỗi client kết nối WebSocket sẽ tạo một instance riêng của class này.
    """

    def __init__(self):
        self._host = "127.0.0.1"
        self._port = 22
        self._user = None
        self._pass = None
        self._pkey = None
        self._key_passwd = ""

        self._tp = None          # paramiko.Transport
        self._ssh = None         # paramiko channel (shell)
        self._ws = None          # WebSocket handler (đối tượng có .send()/.receive())

        self._connected = False
        self._closed = False

        # Lock để tránh 2 thread (recv_loop và main handler) cùng gọi
        # ws.send() một lúc gây lỗi giao thức WebSocket.
        self._send_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Kết nối SSH
    # ------------------------------------------------------------------
    def set_attr(self, ssh_info: dict) -> dict:
        """
        ssh_info = {
            'host': '127.0.0.1',
            'port': 22,
            'username': 'root',
            'password': 'pass123',
            'pkey': None,          # nội dung private key dạng string, nếu dùng key auth
        }
        Return: {'status': 0, 'msg': 'ok'}  hoặc  {'status': -1, 'msg': '...'}
        """
        self._host = ssh_info.get("host", "127.0.0.1") or "127.0.0.1"
        self._port = int(ssh_info.get("port") or 22)
        self._user = ssh_info.get("username")
        self._pass = ssh_info.get("password")
        self._pkey = ssh_info.get("pkey")
        self._key_passwd = ssh_info.get("key_passwd", "")

        if not self._user:
            return {"status": -1, "msg": "Thiếu username"}

        return self.connect()

    def connect(self) -> dict:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(7)
            sock.connect((self._host, self._port))
            sock.settimeout(None)

            self._tp = paramiko.Transport(sock)
            self._tp.banner_timeout = 60
            self._tp.start_client(timeout=10)

            if self._pkey:
                key_file = io.StringIO(self._pkey)
                pkey = paramiko.RSAKey.from_private_key(
                    key_file, password=self._key_passwd or None
                )
                self._tp.auth_publickey(username=self._user, key=pkey)
            else:
                self._tp.auth_password(username=self._user, password=self._pass)

            self._ssh = self._tp.open_session()
            self._ssh.get_pty(term="xterm", width=100, height=34)
            self._ssh.invoke_shell()

            self._connected = True
            self._closed = False
            return {"status": 0, "msg": "ok"}

        except paramiko.AuthenticationException:
            self.close()
            return {"status": -1, "msg": "Sai username hoặc password"}
        except socket.timeout:
            self.close()
            return {"status": -1, "msg": "Kết nối SSH bị timeout (host/port sai?)"}
        except (paramiko.SSHException, socket.error, OSError) as e:
            self.close()
            return {"status": -1, "msg": f"Không thể kết nối SSH: {e}"}
        except Exception as e:  # noqa: BLE001 - báo lỗi rõ ràng cho client
            self.close()
            return {"status": -1, "msg": f"Lỗi không xác định: {e}"}

    # ------------------------------------------------------------------
    # Resize terminal (khi trình duyệt thay đổi kích thước)
    # ------------------------------------------------------------------
    def resize(self, cols: int, rows: int) -> None:
        try:
            if self._ssh and self._connected:
                self._ssh.resize_pty(width=int(cols), height=int(rows))
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Gửi dữ liệu WebSocket an toàn (dùng lock chung)
    # ------------------------------------------------------------------
    def _ws_send(self, payload: str) -> None:
        if not self._ws:
            return
        try:
            with self._send_lock:
                self._ws.send(payload)
        except Exception:
            self.close()

    # ------------------------------------------------------------------
    # recv: đọc output từ SSH channel, đẩy sang WebSocket
    # ------------------------------------------------------------------
    def recv_loop(self) -> None:
        while self._connected and not self._closed:
            try:
                r, _, _ = select.select([self._ssh], [], [], 1.0)
                if self._ssh in r:
                    data = self._ssh.recv(1024)
                    if not data:
                        break
                    text = data.decode("utf-8", "ignore")
                    self._ws_send(json.dumps({"type": "output", "data": text}))
            except Exception:
                break
        self.close()

    # ------------------------------------------------------------------
    # send: nhận input từ WebSocket, ghi vào SSH channel
    # ------------------------------------------------------------------
    def send_data(self, data: str) -> None:
        if self._ssh and self._connected:
            try:
                self._ssh.send(data)
            except Exception:
                self.close()

    # ------------------------------------------------------------------
    # heartbeat: giữ kết nối SSH sống (mỗi 30s)
    # ------------------------------------------------------------------
    def heartbeat_loop(self) -> None:
        while self._connected and not self._closed:
            time.sleep(30)
            try:
                if self._tp and self._tp.is_active():
                    self._tp.send_ignore()
                else:
                    break
            except Exception:
                break

    # ------------------------------------------------------------------
    # Dọn dẹp
    # ------------------------------------------------------------------
    def close(self) -> None:
        self._connected = False
        self._closed = True
        try:
            if self._ssh:
                self._ssh.close()
        except Exception:
            pass
        try:
            if self._tp:
                self._tp.close()
        except Exception:
            pass
