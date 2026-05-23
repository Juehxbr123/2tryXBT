#!/bin/bash
BOT_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVICE_NAME="xbt-tracker"

cat > /etc/systemd/system/${SERVICE_NAME}.service << EOF
[Unit]
Description=Twitter Tracker Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=${BOT_DIR}
ExecStart=${BOT_DIR}/venv/bin/python bot.py
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable ${SERVICE_NAME}
echo "✅ Сервис установлен!"
echo "  systemctl start ${SERVICE_NAME}"
echo "  systemctl restart ${SERVICE_NAME}"
echo "  journalctl -u ${SERVICE_NAME} -f"
