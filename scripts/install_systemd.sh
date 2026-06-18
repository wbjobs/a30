#!/bin/bash
# Install eink-dashboard systemd services
# Usage: sudo ./install_systemd.sh [username]

set -e

USERNAME=${1:-pi}
PROJECT_DIR=$(cd "$(dirname "$0")/.." && pwd)
SERVICE_DIR="/etc/systemd/system"

echo "Installing eink-dashboard systemd services..."
echo "Project directory: $PROJECT_DIR"
echo "User: $USERNAME"

# Create virtual environment if not exists
if [ ! -d "$PROJECT_DIR/.venv" ]; then
    echo "Creating virtual environment..."
    cd "$PROJECT_DIR"
    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt
fi

# Install device server service
echo "Installing eink-dashboard.service..."
sed "s|/home/pi/eink-dashboard|$PROJECT_DIR|g; s|User=pi|User=$USERNAME|g; s|Group=pi|Group=$USERNAME|g" \
    "$PROJECT_DIR/scripts/systemd/eink-dashboard.service" \
    | sudo tee "$SERVICE_DIR/eink-dashboard.service" > /dev/null

# Install watch service template
echo "Installing eink-watch@.service..."
sudo cp "$PROJECT_DIR/scripts/systemd/eink-watch@.service" "$SERVICE_DIR/"

# Reload systemd
sudo systemctl daemon-reload

echo ""
echo "Services installed successfully!"
echo ""
echo "Usage:"
echo "  # Start device server:"
echo "  sudo systemctl enable --now eink-dashboard"
echo ""
echo "  # Start watch daemon for a device:"
echo "  sudo systemctl enable --now eink-watch@http://device-ip:5000"
echo ""
echo "  # Check status:"
echo "  systemctl status eink-dashboard"
echo "  systemctl status eink-watch@http://device-ip:5000"
echo ""
echo "  # View logs:"
echo "  journalctl -u eink-dashboard -f"
echo "  journalctl -u eink-watch@http://device-ip:5000 -f"
