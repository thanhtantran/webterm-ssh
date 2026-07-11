#!/usr/bin/env bash
#
# install.sh — Cài đặt Browser SSH Terminal thành systemd service tự khởi
# động cùng hệ thống.
#
# Cách dùng:
#   git clone https://github.com/<your-repo>/webterm-ssh.git
#   cd webterm-ssh
#   sudo bash install.sh
#
# Script sẽ:
#   1. Tạo virtualenv trong ./venv và cài requirements.txt
#   2. Sinh file systemd unit với đúng đường dẫn + user hiện tại
#   3. Copy vào /etc/systemd/system/webterm-ssh.service
#   4. systemctl daemon-reload, enable, start
#
# Có thể tuỳ chỉnh tài khoản SSH tự động đăng nhập bằng biến môi trường
# trước khi chạy, ví dụ:
#   sudo WEBTERM_SSH_USER=orangepi WEBTERM_SSH_PASS=orangepi bash install.sh

set -euo pipefail

# --- Yêu cầu chạy bằng root/sudo (để ghi vào /etc/systemd/system) ---
if [ "$(id -u)" -ne 0 ]; then
    echo "Vui lòng chạy bằng sudo: sudo bash install.sh"
    exit 1
fi

# --- Xác định thư mục dự án (nơi chứa install.sh) ---
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- Xác định user thực sự sẽ chạy service (không phải root) ---
RUN_USER="${SUDO_USER:-$(whoami)}"
if [ "$RUN_USER" = "root" ]; then
    echo "Cảnh báo: đang cài để chạy bằng user 'root'."
    echo "Khuyến nghị chạy bằng: sudo -u <user thường> hoặc export SUDO_USER."
fi

echo "==> Thư mục dự án : $PROJECT_DIR"
echo "==> User chạy service : $RUN_USER"

# --- Cấu hình SSH tự động đăng nhập (có thể override qua biến môi trường) ---
SSH_HOST="${WEBTERM_SSH_HOST:-127.0.0.1}"
SSH_PORT="${WEBTERM_SSH_PORT:-22}"
SSH_USER="${WEBTERM_SSH_USER:-orangepi}"
SSH_PASS="${WEBTERM_SSH_PASS:-orangepi}"

echo "==> Tài khoản SSH tự động đăng nhập: ${SSH_USER}@${SSH_HOST}:${SSH_PORT}"

# --- 1. Tạo virtualenv + cài dependency ---
echo "==> Tạo virtualenv và cài thư viện Python..."
if ! command -v python3 >/dev/null 2>&1; then
    echo "Lỗi: chưa cài python3. Cài bằng: sudo apt install python3 python3-venv -y"
    exit 1
fi

sudo -u "$RUN_USER" python3 -m venv "$PROJECT_DIR/venv"
sudo -u "$RUN_USER" "$PROJECT_DIR/venv/bin/pip" install --upgrade pip -q
sudo -u "$RUN_USER" "$PROJECT_DIR/venv/bin/pip" install -r "$PROJECT_DIR/requirements.txt" -q

# --- 2. Sinh file systemd unit đúng đường dẫn ---
echo "==> Tạo file systemd service..."
SERVICE_FILE="/etc/systemd/system/webterm-ssh.service"

cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Browser SSH Terminal (xterm.js + WebSocket + Flask + Paramiko)
After=network.target sshd.service
Wants=network-online.target

[Service]
Type=simple
User=${RUN_USER}
WorkingDirectory=${PROJECT_DIR}
ExecStart=${PROJECT_DIR}/venv/bin/python3 ${PROJECT_DIR}/server.py

Environment=WEBTERM_SSH_HOST=${SSH_HOST}
Environment=WEBTERM_SSH_PORT=${SSH_PORT}
Environment=WEBTERM_SSH_USER=${SSH_USER}
Environment=WEBTERM_SSH_PASS=${SSH_PASS}

Restart=always
RestartSec=3

StandardOutput=journal
StandardError=journal

NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
EOF

echo "==> Đã ghi $SERVICE_FILE"

# --- 3. Kích hoạt service ---
echo "==> Bật service (systemctl daemon-reload, enable, start)..."
systemctl daemon-reload
systemctl enable webterm-ssh
systemctl restart webterm-ssh

sleep 1
echo ""
echo "=================================================================="
if systemctl is-active --quiet webterm-ssh; then
    IP_ADDR="$(hostname -I 2>/dev/null | awk '{print $1}')"
    echo "✅ Cài đặt thành công! Service đang chạy và sẽ tự khởi động cùng hệ thống."
    echo ""
    echo "   Truy cập: http://${IP_ADDR:-<ip-thiết-bị>}:7681"
    echo ""
    echo "   Xem log       : sudo journalctl -u webterm-ssh -f"
    echo "   Trạng thái    : sudo systemctl status webterm-ssh"
    echo "   Dừng          : sudo systemctl stop webterm-ssh"
    echo "   Khởi động lại : sudo systemctl restart webterm-ssh"
else
    echo "❌ Service không khởi động được. Xem log lỗi bằng:"
    echo "   sudo journalctl -u webterm-ssh -n 50 --no-pager"
fi
echo "=================================================================="
