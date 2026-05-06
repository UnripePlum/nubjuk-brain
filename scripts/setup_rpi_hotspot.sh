#!/usr/bin/env bash
set -euo pipefail

IFACE="${HOTSPOT_INTERFACE:-wlan0}"
CON_NAME="${HOTSPOT_CON_NAME:-nubjuk-hotspot}"
SSID="${HOTSPOT_SSID:-Nubjuk-RPi}"
PASSWORD="${HOTSPOT_PASSWORD:-nubjuk2026}"
ADDRESS="${HOTSPOT_ADDRESS:-10.42.0.1/24}"

if [ "${EUID:-$(id -u)}" -ne 0 ]; then
  echo "ERROR: run with sudo." >&2
  echo "  sudo HOTSPOT_PASSWORD='your-password' $0" >&2
  exit 1
fi

if [ "${#PASSWORD}" -lt 8 ] || [ "${#PASSWORD}" -gt 63 ]; then
  echo "ERROR: HOTSPOT_PASSWORD must be 8-63 characters for WPA-PSK." >&2
  exit 1
fi

if ! command -v nmcli >/dev/null 2>&1; then
  echo "ERROR: nmcli is required. Install/enable NetworkManager first." >&2
  exit 1
fi

if ! nmcli -t -f RUNNING general | grep -qx running; then
  echo "ERROR: NetworkManager is not running." >&2
  exit 1
fi

if ! nmcli -t -f DEVICE dev status | grep -qx "$IFACE"; then
  echo "ERROR: Wi-Fi interface '$IFACE' not found." >&2
  nmcli dev status >&2
  exit 1
fi

if command -v rfkill >/dev/null 2>&1; then
  rfkill unblock wifi || true
fi
nmcli radio wifi on

nmcli con delete "$CON_NAME" >/dev/null 2>&1 || true
nmcli con add type wifi ifname "$IFACE" con-name "$CON_NAME" ssid "$SSID" >/dev/null
nmcli con modify "$CON_NAME" \
  connection.autoconnect yes \
  connection.autoconnect-priority 20 \
  802-11-wireless.mode ap \
  802-11-wireless.band bg \
  ipv4.method shared \
  ipv4.addresses "$ADDRESS" \
  ipv6.method disabled \
  wifi-sec.key-mgmt wpa-psk \
  wifi-sec.psk "$PASSWORD"

nmcli con up "$CON_NAME"

echo
echo "RPi hotspot is up."
echo "SSID: $SSID"
echo "RPi hotspot IP: ${ADDRESS%/*}"
echo "Mac SSH: ssh ${SUDO_USER:-unripeplum}@${ADDRESS%/*}"
echo "ESP brain URL: ws://${ADDRESS%/*}:8080/sti"
echo
nmcli -f DEVICE,TYPE,STATE,CONNECTION dev status
ip -br addr show "$IFACE"
