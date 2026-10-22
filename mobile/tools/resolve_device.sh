#!/usr/bin/env bash
# Turn a hardware serial into whatever adb transport currently reaches it.
#
#   tools/resolve_device.sh 5B280DLCH000C7              # USB if plugged in, else Wi-Fi
#   tools/resolve_device.sh --wireless 5B280DLCH000C7   # Wi-Fi only, fail if not there
#   tools/resolve_device.sh --usb 43180DLJH002B4        # cable only, fail if not there
#
# A wireless phone's adb serial is its address — 192.168.1.42:5555 — and that
# changes on every DHCP lease and every reboot. Hardcoding one gives you a
# Makefile that works until the router disagrees. So the phone is identified by
# `ro.serialno`, which is the same number over USB and over Wi-Fi and never
# changes, and the address is looked up fresh each time.
#
# Prints the transport on stdout and nothing else, so it can be substituted
# straight into DEVICE=.

set -euo pipefail

ADB="${ANDROID_HOME:-$HOME/Android/Sdk}/platform-tools/adb"
WIRELESS_ONLY=0
USB_ONLY=0

case "${1:-}" in
  --wireless) WIRELESS_ONLY=1; shift ;;
  --usb)      USB_ONLY=1; shift ;;
esac

WANT="${1:-}"
if [ -z "$WANT" ]; then
  echo "usage: resolve_device.sh [--wireless|--usb] <hardware-serial>" >&2
  exit 2
fi

if [ ! -x "$ADB" ]; then
  echo "adb not found at $ADB — set ANDROID_HOME" >&2
  exit 1
fi

usb=""
wifi=""

find_transports() {
  usb=""
  wifi=""
  while read -r transport; do
    [ -n "$transport" ] || continue
    # </dev/null matters: `adb shell` reads stdin, and stdin here is the device
    # list feeding this loop. Without it the first phone swallows the rest and
    # every device after the first is invisible.
    local actual
    actual=$("$ADB" -s "$transport" shell getprop ro.serialno </dev/null 2>/dev/null | tr -d '\r')
    [ "$actual" = "$WANT" ] || continue
    case "$transport" in
      *:*) wifi="$transport" ;;
      *)   usb="$transport" ;;
    esac
  done < <("$ADB" devices | awk '$2 == "device" { print $1 }')
}

# Where mDNS says this phone is, if it is advertising.
advertised_address() {
  timeout 5 "$ADB" mdns services 2>/dev/null \
    | awk -v want="adb-$WANT" '$1 == want { print $3; exit }'
}

# Whatever state adb currently has that address in: device, offline,
# unauthorized, or empty for "not listed".
transport_state() {
  "$ADB" devices | awk -v addr="$1" '$1 == addr { print $2; exit }'
}

# Ask mDNS where this phone is, and reconnect to it.
#
# A phone in tcpip mode advertises itself as adb-<serial> for as long as it is
# awake and on the network. So a dropped connection — an adb server restart, a
# new DHCP lease, a walk out of Wi-Fi range and back — costs nothing but this
# lookup. Only a reboot needs the cable again, because that is what resets
# tcpip mode itself.
#
# A transport can also go *offline* rather than vanish, which is what a sleeping
# phone looks like. `adb connect` on an address it already holds offline is a
# no-op and reports success, so the stale entry has to be dropped first — that
# is the difference between healing and reporting "connected" to something that
# answers nothing.
reconnect_via_mdns() {
  local found state
  found=$(advertised_address)
  [ -n "$found" ] || return 1
  state=$(transport_state "$found")
  if [ -n "$state" ] && [ "$state" != "device" ]; then
    "$ADB" disconnect "$found" >/dev/null 2>&1 || true
  fi
  "$ADB" connect "$found" >/dev/null 2>&1 || return 1
  return 0
}

# Any address adb is holding in a state other than `device` — a sleeping phone
# looks exactly like this. The serial cannot be confirmed while it is offline
# (`adb shell` needs a live transport), so every stale address is revived and
# the re-scan sorts out which one was wanted. Reconnecting an address that
# belongs to some other phone costs nothing.
revive_offline() {
  local revived=1
  while read -r addr state; do
    [ -n "$addr" ] || continue
    case "$addr" in *:*) ;; *) continue ;; esac
    [ "$state" != "device" ] || continue
    "$ADB" disconnect "$addr" >/dev/null 2>&1 || true
    "$ADB" connect "$addr" >/dev/null 2>&1 && revived=0
  done < <("$ADB" devices | awk 'NR>1 && NF==2 { print $1, $2 }')
  return $revived
}

find_transports

# Advertising but not connected: reconnect rather than sending someone for a
# cable they do not need.
if [ -z "$wifi" ] && reconnect_via_mdns; then
  find_transports
fi

# Still nothing, but adb is holding a stale address: a phone that went to sleep
# stops advertising over mDNS while staying listed as offline, so the lookup
# above finds nothing and the address is sitting right there.
if [ -z "$wifi" ] && [ -z "$usb" ] && revive_offline; then
  find_transports
fi

if [ "$USB_ONLY" -eq 1 ]; then
  if [ -z "$usb" ]; then
    echo "$WANT is not plugged in." >&2
    if [ -n "$wifi" ]; then
      echo "It is on wireless adb at $wifi, but this target wants the cable." >&2
    fi
    exit 1
  fi
  echo "$usb"
  exit 0
fi

# Plugged in but not yet on Wi-Fi: set it up rather than printing the command
# that would. Going wireless needs one cable *once*, and if the cable is already
# there this is a step nobody should have to take by hand.
#
# Chatter goes to stderr — stdout carries the transport and nothing else, since
# the caller substitutes it straight into DEVICE=.
# AUTOPAIR guards against recursion: pair_wireless.sh asks *this* script whether
# the phone is already wireless, so without it the two call each other forever.
if [ "$WIRELESS_ONLY" -eq 1 ] && [ -z "$wifi" ] && [ -n "$usb" ] \
   && [ "${RESOLVE_AUTOPAIR:-1}" = "1" ]; then
  HERE="$(cd "$(dirname "$0")" && pwd)"
  DEVICE="$WANT" RESOLVE_AUTOPAIR=0 bash "$HERE/pair_wireless.sh" >&2 || true
  # `adb tcpip` restarts the daemon on the phone, so for a second or two the
  # device is listed as neither USB nor Wi-Fi. Re-scanning immediately catches
  # that gap and reports a phone that is plugged in as unreachable.
  for _ in 1 2 3 4 5; do
    find_transports
    [ -z "$wifi" ] || break
    sleep 1
  done
fi

if [ "$WIRELESS_ONLY" -eq 1 ]; then
  if [ -z "$wifi" ]; then
    # Distinguish the three ways this fails, because they need three different
    # things from a person and "it broke again" is what one message for all of
    # them produces.
    addr=$(advertised_address)
    state=$([ -n "$addr" ] && transport_state "$addr" || echo "")
    if [ -n "$addr" ] && [ -n "$state" ] && [ "$state" != "device" ]; then
      echo "$WANT is at $addr but adb says '$state'." >&2
      echo "That is usually a sleeping phone — wake the screen and try again." >&2
    elif [ -n "$addr" ]; then
      echo "$WANT advertises at $addr but would not connect. Try again, or" >&2
      echo "wake the screen if it has been idle a while." >&2
    elif [ -n "$usb" ]; then
      echo "$WANT is plugged in, but going wireless failed. Check the phone" >&2
      echo "is on the same Wi-Fi as this machine." >&2
    else
      stale=$("$ADB" devices | awk 'NR>1 && NF==2 && $2 != "device" { print $1; exit }')
      if [ -n "$stale" ]; then
        echo "$WANT is not reachable. adb is holding $stale offline and could" >&2
        echo "not revive it — that is usually a phone asleep or off the network." >&2
        echo "Wake the screen and try again." >&2
      else
        echo "$WANT is not reachable and is not advertising itself." >&2
        echo "Wireless adb survives unplugging but not a reboot. If it has" >&2
        echo "restarted, plug it in once and run: make wireless DEVICE=$WANT" >&2
      fi
    fi
    exit 1
  fi
  echo "$wifi"
  exit 0
fi

# USB first when both exist: same phone either way, and the cable is faster for
# a 100 MB APK than a home network.
if [ -n "$usb" ]; then
  echo "$usb"
elif [ -n "$wifi" ]; then
  echo "$wifi"
else
  echo "$WANT is not reachable — not plugged in, not on wireless adb." >&2
  exit 1
fi
