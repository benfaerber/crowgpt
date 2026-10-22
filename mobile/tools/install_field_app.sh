#!/usr/bin/env bash
# Build and install the field app as a STANDALONE release APK.
#
# `make android` builds a dev client, which fetches its JavaScript from Metro on
# a laptop. That is fine at a desk and useless in a field: with no Metro reachable
# the app cannot start, which is exactly how a recording session gets lost. A
# release build has the bundle compiled in and needs nothing but the phone.
#
#   make install                 # the only attached phone
#   make install DEVICE=SERIAL   # pick one when several are plugged in
#   make devices                 # list what's attached
#
# Re-running it updates an already-installed app in place; captures already on
# the phone survive, because the package and signing key don't change.

set -euo pipefail

ADB="${ANDROID_HOME:-$HOME/Android/Sdk}/platform-tools/adb"
PACKAGE="com.cawtalker.field"

if [ ! -x "$ADB" ]; then
  echo "adb not found at $ADB — set ANDROID_HOME" >&2
  exit 1
fi

mapfile -t SERIALS < <("$ADB" devices | awk '$2 == "device" { print $1 }')

if [ "${#SERIALS[@]}" -eq 0 ]; then
  echo "No phone attached." >&2
  echo "Plug it in, unlock it, and confirm the USB debugging prompt." >&2
  exit 1
fi

TARGET="${DEVICE:-}"
if [ -z "$TARGET" ]; then
  if [ "${#SERIALS[@]}" -gt 1 ]; then
    echo "More than one transport is attached — say which one:" >&2
    for serial in "${SERIALS[@]}"; do
      # </dev/null: `adb shell` reads stdin, and swallowing it here would eat
      # the rest of the loop.
      model=$("$ADB" -s "$serial" shell getprop ro.product.model </dev/null 2>/dev/null | tr -d '\r')
      hw=$("$ADB" -s "$serial" shell getprop ro.serialno </dev/null 2>/dev/null | tr -d '\r')
      # One phone on both USB and Wi-Fi appears twice, and two identical model
      # lines read as two identical phones. Say which link each one is.
      case "$serial" in
        *:*) link="Wi-Fi" ;;
        *)   link="USB" ;;
      esac
      echo "    make install DEVICE=$serial      # $model over $link ($hw)" >&2
    done
    exit 1
  fi
  TARGET="${SERIALS[0]}"
else
  if ! printf '%s\n' "${SERIALS[@]}" | grep -qx "$TARGET"; then
    echo "Device '$TARGET' is not attached. Attached:" >&2
    printf '    %s\n' "${SERIALS[@]}" >&2
    exit 1
  fi
fi

MODEL=$("$ADB" -s "$TARGET" shell getprop ro.product.model 2>/dev/null | tr -d '\r')
echo "Installing the field app on $MODEL ($TARGET)"
echo "Building a release APK — the JavaScript is bundled in, so the app runs"
echo "with no laptop, no Metro and no network."
echo

# Gradle directly rather than `expo run:android --device`, which matches on a
# device *name* and cannot be handed a serial — the only unambiguous way to say
# which phone when two are plugged in.
echo "Syncing app.json into the native project…"
npx expo prebuild --platform android >/dev/null

echo "Compiling (this takes a few minutes the first time)…"
./android/gradlew -p android --quiet assembleRelease

APK=android/app/build/outputs/apk/release/app-release.apk
if [ ! -f "$APK" ]; then
  echo "Expected an APK at $APK but it isn't there." >&2
  exit 1
fi

# adb prints "Performing Streamed Install" and then nothing for the best part of
# a minute over Wi-Fi, which is indistinguishable from a hang — and the honest
# response to a hang is to unplug something, which is how an install gets
# interrupted halfway.
#
# adb gives no progress to report, so this reports elapsed time against a rough
# expectation instead. Not a real percentage, and it does not pretend to be one:
# a number that moves is the difference between waiting and giving up.
SIZE_MB=$(( $(stat -c%s "$APK") / 1000000 ))
case "$TARGET" in
  *:*) LINK="Wi-Fi"; RATE=3 ;;   # ~3 MB/s over a home network
  # Measured, not the cable's rating: the install also verifies and optimises on
  # the device, and an estimate that is always beaten reads as a stall.
  *)   LINK="USB";   RATE=8 ;;
esac
EXPECT=$(( SIZE_MB / RATE + 2 ))
echo "Installing ${SIZE_MB} MB APK over $LINK (about ${EXPECT}s)…"

# adb's own output is held until the end rather than left to interleave with
# the progress line, which produced "Success" printed above a counter still
# counting.
INSTALL_LOG=$(mktemp)
"$ADB" -s "$TARGET" install -r "$APK" >"$INSTALL_LOG" 2>&1 &
INSTALL_PID=$!
START=$SECONDS
while kill -0 "$INSTALL_PID" 2>/dev/null; do
  sleep 2
  ELAPSED=$(( SECONDS - START ))
  if [ "$ELAPSED" -gt "$EXPECT" ]; then
    printf "\r  %ds elapsed — longer than expected, still going…   " "$ELAPSED"
  else
    printf "\r  %ds / ~%ds   " "$ELAPSED" "$EXPECT"
  fi
done
printf "\r%*s\r" 48 ""
# The background job's exit status is the install's; a failure must still fail
# here rather than be swallowed by the progress loop.
if ! wait "$INSTALL_PID"; then
  cat "$INSTALL_LOG" >&2
  rm -f "$INSTALL_LOG"
  exit 1
fi
cat "$INSTALL_LOG"
rm -f "$INSTALL_LOG"
"$ADB" -s "$TARGET" shell monkey -p "$PACKAGE" -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1 || true

echo
INSTALLED=$("$ADB" -s "$TARGET" shell dumpsys package "$PACKAGE" 2>/dev/null \
  | awk -F= '/versionName/ { print $2; exit }' | tr -d '\r')
echo "Installed $PACKAGE ${INSTALLED:+version $INSTALLED} on $MODEL."
echo "It now runs on its own — unplug it and record."
