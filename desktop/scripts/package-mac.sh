#!/bin/sh
# Build the macOS arm64 desktop app end to end:
#   dist + PyInstaller backend -> .app -> ad-hoc signature -> dmg from the signed app
#
# Apple Silicon refuses to launch an unsigned arm64 app, and electron-builder skips
# signing because this project has no Apple certificate, so the ad-hoc signature
# (codesign --sign -) is what makes the bundle runnable on this machine.
#
#   scripts/package-mac.sh            # build + dmg
#   scripts/package-mac.sh --install  # build + dmg, then replace /Applications/ECA Desktop.app
set -eu
cd "$(dirname "$0")/.."

# Electron's binaries come from GitHub releases, which stalls on some Chinese
# networks. Override ELECTRON_MIRROR to use another mirror.
export ELECTRON_MIRROR="${ELECTRON_MIRROR:-https://npmmirror.com/mirrors/electron/}"
export CSC_IDENTITY_AUTO_DISCOVERY=false

npm run build
npm run backend:mac
node_modules/.bin/electron-builder --mac --arm64

app="../output/release/desktop/mac-arm64/ECA Desktop.app"
codesign --force --deep --sign - "$app"
codesign --verify --deep --strict "$app"

# Rebuild the dmg from the signed bundle so the installer is signed too.
node_modules/.bin/electron-builder --mac dmg --arm64 --prepackaged "$app"

if [ "${1:-}" = "--install" ]; then
  rm -rf "/Applications/ECA Desktop.app"
  cp -R "$app" /Applications/
  xattr -cr "/Applications/ECA Desktop.app"
  echo "installed: /Applications/ECA Desktop.app"
fi

echo "dmg: $(ls -1 ../output/release/desktop/ECA-Desktop-*-arm64.dmg | tail -1)"
