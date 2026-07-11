# webterm-ssh

Terminal SSH ngay trên trình duyệt — mở một địa chỉ IP là có ngay dòng lệnh
của thiết bị (Orange Pi, Raspberry Pi, server Linux bất kỳ), không cần cài
PuTTY/Termius, không cần app, chạy được cả trên điện thoại.

Tự động đăng nhập SSH sẵn (mặc định `orangepi` / `orangepi`), không cần
form nhập tài khoản — mở trang là vào thẳng terminal.

## Kiến trúc

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

Khác với việc fork PTY chạy `bash` trực tiếp trên server, `webterm-ssh` thật
sự **SSH vào chính thiết bị** (giống cách aaPanel/1Panel làm) — nên vẫn giữ
nguyên toàn bộ cơ chế xác thực, quyền hạn, và log của SSH thông thường.

## Demo nhanh

Mở trình duyệt: `http://<ip-thiết-bị>:7681` → vào thẳng terminal, gõ lệnh
như SSH bình thường, resize cửa sổ trình duyệt terminal cũng tự resize theo
(hỗ trợ đầy đủ `vim`, `htop`, `less`, ...).

## Cài đặt

### Cách 1 — Cài tự động, chạy nền cùng hệ thống (khuyến nghị)

```bash
git clone https://github.com/<your-username>/webterm-ssh.git
cd webterm-ssh
sudo bash install.sh
```

Script `install.sh` sẽ tự động:
1. Tạo virtualenv (`./venv`) và cài các thư viện cần thiết
2. Sinh file `systemd` service với đúng đường dẫn + user hiện tại của bạn
3. Bật service, cấu hình tự khởi động cùng hệ thống (boot)

Sau khi chạy xong, script in ra địa chỉ truy cập, ví dụ:
```
✅ Cài đặt thành công!
   Truy cập: http://192.168.88.5:7681
```

Muốn đổi tài khoản SSH tự động đăng nhập khác `orangepi/orangepi`:
```bash
sudo WEBTERM_SSH_USER=myuser WEBTERM_SSH_PASS=mypass bash install.sh
```

### Cách 2 — Cài thủ công, chạy tay (để test/dev)

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 server.py
```

Mặc định lắng nghe `0.0.0.0:7681`, tự SSH vào `127.0.0.1:22` bằng
`orangepi/orangepi`. Đổi cấu hình bằng biến môi trường:

```bash
WEBTERM_SSH_HOST=127.0.0.1 \
WEBTERM_SSH_PORT=22 \
WEBTERM_SSH_USER=orangepi \
WEBTERM_SSH_PASS=orangepi \
python3 server.py
```

## Cấu trúc dự án

```
webterm-ssh/
├── server.py                  # Flask app + WebSocket route /ws + route /health
├── class_v2/
│   ├── __init__.py
│   └── ssh_terminal.py        # class SSHTerminal — Paramiko SSH client
├── static/
│   ├── index.html             # Giao diện xterm.js
│   └── vendor/                # xterm.js đóng gói sẵn (KHÔNG phụ thuộc CDN)
│       ├── xterm.js
│       ├── xterm.css
│       └── xterm-addon-fit.js
├── requirements.txt
├── install.sh                 # Script cài đặt tự động + tạo systemd service
├── webterm-ssh.service        # File systemd mẫu (tham khảo/cài thủ công)
└── README.md
```

## Quản lý service (sau khi cài bằng `install.sh`)

```bash
sudo systemctl status webterm-ssh     # xem trạng thái
sudo systemctl restart webterm-ssh    # khởi động lại
sudo systemctl stop webterm-ssh       # dừng
sudo journalctl -u webterm-ssh -f     # xem log realtime
```

### Cài thủ công file service (không dùng install.sh)

```bash
sudo cp webterm-ssh.service /etc/systemd/system/webterm-ssh.service
sudo nano /etc/systemd/system/webterm-ssh.service   # sửa User + đường dẫn cho đúng máy bạn
sudo systemctl daemon-reload
sudo systemctl enable --now webterm-ssh
```

## Giao thức WebSocket

Endpoint: `ws://<ip>:7681/ws` — mỗi message là JSON.

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

Server tự động SSH ngay khi WebSocket vừa mở — không có bước `connect` từ
phía client.

## Khắc phục sự cố

### Trang chỉ hiện "Đang kết nối SSH..." mãi không đổi

Đây là dấu hiệu **WebSocket chưa từng chạm tới server** — nguyên nhân
thường gặp nhất là trình duyệt không tải được `xterm.js` (ví dụ nếu bạn
sửa code và trỏ lại về CDN mà thiết bị đó không có Internet). Kiểm tra:

1. Mở DevTools (F12) → tab **Console**: có lỗi đỏ nào không (ví dụ
   `Terminal is not defined`)?
2. Tab **Network** → filter **JS**: `xterm.js`, `xterm-addon-fit.js` có tải
   thành công (status 200) không? Bản repo này đã đóng gói local trong
   `static/vendor/`, không cần Internet — nếu bạn thấy các file đó tải từ
   CDN nghĩa là `index.html` đã bị chỉnh sửa, cần đổi lại về đường dẫn
   `/static/vendor/...`.
3. Test HTTP thuần trước, tách khỏi WebSocket:
   `http://<ip>:7681/health` — phải trả về JSON `{"status":"ok",...}`.
   Nếu route này cũng không load được thì là vấn đề mạng/tường lửa,
   chưa liên quan tới code.

### Lỗi "Sai username hoặc password"

- Kiểm tra sshd có cho phép đăng nhập bằng password không:
  ```bash
  grep -i PasswordAuthentication /etc/ssh/sshd_config
  ```
  Nếu là `PasswordAuthentication no`, sửa thành `yes` rồi:
  ```bash
  sudo systemctl restart ssh
  ```
- Kiểm tra tài khoản/mật khẩu đúng bằng cách SSH tay thử:
  ```bash
  ssh orangepi@127.0.0.1
  ```

### Cổng 7681 đã bị chiếm

```bash
sudo ss -tlnp | grep 7681
```
Nếu có tiến trình cũ đang giữ cổng, dừng nó hoặc đổi `PORT` trong
`server.py`.

### Không thấy log gì trên console

`server.py` in log bằng `print(..., flush=True)` nên không bị buffer khi
chạy qua `nohup`/`systemd`. Nếu dùng `journalctl -u webterm-ssh -f` mà
không thấy gì, kiểm tra service có thật sự đang chạy:
```bash
sudo systemctl status webterm-ssh
```

## Bảo mật — đọc trước khi expose ra ngoài Internet

⚠️ Ứng dụng này cấp quyền truy cập shell đầy đủ tới thiết bị của bạn thông
qua trình duyệt. Trước khi mở ra ngoài mạng LAN, cân nhắc:

- **Không expose thẳng ra Internet** nếu chưa có HTTPS/WSS + xác thực. Đây
  tương đương mở SSH không mật khẩu qua HTTP cho bất kỳ ai vào được cổng
  7681.
- Đổi mật khẩu `orangepi/orangepi` mặc định — đây là tài khoản mặc định
  phổ biến của board Orange Pi, không nên giữ nguyên nếu thiết bị lộ ra
  mạng ngoài.
- Nếu cần truy cập từ xa, nên đặt sau reverse proxy (Nginx/Caddy) có HTTPS
  và giới hạn theo IP hoặc thêm xác thực (Basic Auth, VPN, Tailscale...),
  thay vì mở thẳng cổng 7681 ra WAN.
- `Flask` dev server (`app.run()`) chỉ phù hợp cho LAN nội bộ/dev. Muốn
  triển khai nghiêm túc hơn, cân nhắc chạy qua `gunicorn` với worker hỗ trợ
  WebSocket (`gevent-websocket`).

## License

MIT
