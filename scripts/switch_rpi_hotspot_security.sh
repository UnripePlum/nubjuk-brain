#!/usr/bin/env bash
set -euo pipefail

CON_NAME="${HOTSPOT_CON_NAME:-nubjuk-hotspot}"
IFACE="${HOTSPOT_INTERFACE:-wlan0}"
ROLLBACK_SECONDS="${HOTSPOT_ROLLBACK_SECONDS:-180}"
CONFIRM_FILE="${HOTSPOT_CONFIRM_FILE:-/tmp/nubjuk-hotspot-switch.confirm}"
LOG="${HOTSPOT_SWITCH_LOG:-/tmp/nubjuk-hotspot-switch.log}"
ACTION="${1:-}"

usage() {
  cat <<EOF
Usage:
  sudo $0 wpa3      # switch to WPA3-SAE, rollback unless confirmed
  sudo $0 wpa2      # switch to WPA2-PSK, rollback unless confirmed
  $0 confirm        # confirm the new mode after reconnecting
  $0 status         # show current hotspot security

Environment:
  HOTSPOT_CON_NAME=nubjuk-hotspot
  HOTSPOT_INTERFACE=wlan0
  HOTSPOT_ROLLBACK_SECONDS=180
EOF
}

require_nmcli() {
  if ! command -v nmcli >/dev/null 2>&1; then
    echo "ERROR: nmcli is required." >&2
    exit 1
  fi
}

show_status() {
  require_nmcli
  nmcli -f 802-11-wireless-security.key-mgmt,802-11-wireless-security.pmf con show "$CON_NAME"
  nmcli -f DEVICE,TYPE,STATE,CONNECTION dev status
  ip -br addr show "$IFACE" || true
}

case "$ACTION" in
  confirm)
    : > "$CONFIRM_FILE"
    echo "Confirmed hotspot security switch."
    exit 0
    ;;
  status)
    show_status
    exit 0
    ;;
  wpa2|wpa3)
    ;;
  -h|--help|"")
    usage
    exit 0
    ;;
  *)
    echo "ERROR: unknown action '$ACTION'." >&2
    usage >&2
    exit 1
    ;;
esac

if [ "${EUID:-$(id -u)}" -ne 0 ]; then
  echo "ERROR: run switch actions with sudo." >&2
  echo "  sudo $0 $ACTION" >&2
  exit 1
fi

if [ "${HOTSPOT_SWITCH_DETACHED:-0}" != "1" ]; then
  rm -f "$CONFIRM_FILE"
  nohup env \
    HOTSPOT_SWITCH_DETACHED=1 \
    HOTSPOT_CON_NAME="$CON_NAME" \
    HOTSPOT_INTERFACE="$IFACE" \
    HOTSPOT_ROLLBACK_SECONDS="$ROLLBACK_SECONDS" \
    HOTSPOT_CONFIRM_FILE="$CONFIRM_FILE" \
    "$0" "$ACTION" > "$LOG" 2>&1 &
  echo "Hotspot security switch started in background."
  echo "Target: $ACTION"
  echo "Log: $LOG"
  echo "Reconnect to SSID Nubjuk-RPi, then confirm:"
  echo "  ssh nubjuk-rpi 'cd ~/projects/nubjuk/brain && scripts/switch_rpi_hotspot_security.sh confirm'"
  echo "If not confirmed within ${ROLLBACK_SECONDS}s, it will roll back automatically."
  exit 0
fi

require_nmcli
if ! nmcli con show "$CON_NAME" >/dev/null 2>&1; then
  echo "ERROR: connection '$CON_NAME' not found." >&2
  exit 1
fi

apply_wpa3() {
  nmcli con modify "$CON_NAME" \
    wifi-sec.key-mgmt sae \
    802-11-wireless-security.pmf 3 \
    802-11-wireless-security.proto rsn \
    802-11-wireless-security.pairwise ccmp \
    802-11-wireless-security.group ccmp
}

apply_wpa2() {
  nmcli con modify "$CON_NAME" \
    wifi-sec.key-mgmt wpa-psk \
    802-11-wireless-security.pmf 0 \
    802-11-wireless-security.proto rsn \
    802-11-wireless-security.pairwise ccmp \
    802-11-wireless-security.group ccmp
}

restart_hotspot() {
  nmcli con down "$CON_NAME" || true
  sleep 2
  nmcli con up "$CON_NAME"
}

rollback_action="wpa2"
if [ "$ACTION" = "wpa2" ]; then
  rollback_action="wpa3"
fi

echo "Switching hotspot '$CON_NAME' to $ACTION at $(date -Is)."
if [ "$ACTION" = "wpa3" ]; then
  apply_wpa3
else
  apply_wpa2
fi
restart_hotspot
show_status

echo "Waiting ${ROLLBACK_SECONDS}s for confirmation file: $CONFIRM_FILE"
for ((second = 1; second <= ROLLBACK_SECONDS; second++)); do
  if [ -f "$CONFIRM_FILE" ]; then
    rm -f "$CONFIRM_FILE"
    echo "Confirmed. Keeping $ACTION."
    exit 0
  fi
  sleep 1
done

echo "No confirmation received. Rolling back to $rollback_action at $(date -Is)."
if [ "$rollback_action" = "wpa3" ]; then
  apply_wpa3
else
  apply_wpa2
fi
restart_hotspot
show_status
echo "Rollback complete."
