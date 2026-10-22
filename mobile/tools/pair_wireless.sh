#!/usr/bin/env bash
# Put an attached phone onto wireless adb, so it can be updated over Wi-Fi.
#
#   make wireless                 # the only attached phone
#   make wireless DEVICE=SERIAL   # pick one when several are plugged in
#
# Why bother: `make install` picks the single attached phone automatically, and
# that is exactly how the wrong handset gets flashed. A phone that lives on
# Wi-Fi is always in `adb devices`, so the count is never one by accident and
# the script always makes you name a target.
#
# The address survives until the phone reboots or drops off the network. Re-run
# this then — pairing itself is one-time, this is only the connect step.
#
# First time on a given phone, pair it by hand instead (Android 11+):
#   Settings > Developer options > Wireless debugging > Pair device with code
#   adb pair <ip>:<pairing-port> <code>
# The pairing port differs from the connect port; that is not a typo.

set -euo pipefail

ADB="${ANDROID_HOME:-$HOME/Android/Sdk}/platform-tools/adb"
PORT=5555

if [ ! -x "$ADB" ]; then
  echo "adb not found at $ADB — set ANDROID_HOME" >&2
  exit 1
fi

HERE="$(cd "$(dirname "$0")" && pwd)"

# Already wireless? Then this is a no-op, and saying so beats sending someone
# for a cable. That is the bug this guards: the command named "wireless" demanded
# USB even when the phone was reachable over Wi-Fi at that moment, which reads as
# the setup having been lost when nothing was wrong.
if [ -n "${DEVICE:-}" ]; then
  # RESOLVE_AUTOPAIR=0: ask only whether it is already wireless. Without it the
  # resolver would try to set that up by calling back into this script.
  if addr=$(RESOLVE_AUTOPAIR=0 "$HERE/resolve_device.sh" --wireless "$DEVICE" 2>/dev/null); then
    echo "$DEVICE is already on wireless adb at $addr — nothing to do."
    echo "Install with: make install-app DEVICE=$addr"
    exit 0
  fi
fi

# USB-attached only: a phone already on Wi-Fi has a serial like 10.0.0.5:5555,
# and telling it to restart tcpip over its own tcpip link drops the connection.
mapfile -t SERIALS < <("$ADB" devices | awk '$2 == "device" && $1 !~ /:/ { print $1 }')

if [ "${#SERIALS[@]}" -eq 0 ]; then
  echo "No USB-attached phone. Plug one in — going wireless needs one cable first." >&2
  exit 1
fi

TARGET="${DEVICE:-}"
if [ -n "$TARGET" ]; then
  # Named but not on USB: going wireless needs the cable once, so say that
  # rather than failing later inside adb with something cryptic.
  if ! printf '%s\n' "${SERIALS[@]}" | grep -qx "$TARGET"; then
    echo "Device '$TARGET' is neither on wireless adb nor plugged in." >&2
    echo "Setting up wireless needs the cable once. USB right now:" >&2
    printf '    %s\n' "${SERIALS[@]}" >&2
    exit 1
  fi
elif [ -z "$TARGET" ]; then
  if [ "${#SERIALS[@]}" -gt 1 ]; then
    echo "More than one phone is attached — say which one:" >&2
    for serial in "${SERIALS[@]}"; do
      model=$("$ADB" -s "$serial" shell getprop ro.product.model 2>/dev/null | tr -d '\r')
      echo "    make wireless DEVICE=$serial      # $model" >&2
    done
    exit 1
  fi
  TARGET="${SERIALS[0]}"
fi

MODEL=$("$ADB" -s "$TARGET" shell getprop ro.product.model 2>/dev/null | tr -d '\r')

# Ask the phone for its own address rather than guessing the interface: a phone
# on a hotspot, a VPN or a second Wi-Fi has more than one, and the wrong one
# fails with a timeout that looks like the phone is off.
IP=$("$ADB" -s "$TARGET" shell ip -f inet addr show wlan0 2>/dev/null \
  | awk '/inet /{ sub("/.*","",$2); print $2; exit }')

if [ -z "$IP" ]; then
  echo "$MODEL has no wlan0 address — is it on Wi-Fi?" >&2
  exit 1
fi

echo "Putting $MODEL ($TARGET) on wireless adb at $IP:$PORT"
"$ADB" -s "$TARGET" tcpip "$PORT" >/dev/null
# The daemon needs a moment to come back up on the new transport; connecting
# immediately gets "connection refused" on a phone that is perfectly fine.
sleep 2
"$ADB" connect "$IP:$PORT"

echo "Unplug the cable — it stays reachable at $IP:$PORT until it reboots."
