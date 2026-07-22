#!/bin/sh
# Buster uninstaller — macOS & Linux. Mirrors install.sh.
# Removes the user-level service, the isolated venv, and the CLI shim.
# Data (reports, memory, config) is PRESERVED unless you pass --purge.
#
# Usage:  ./uninstall.sh            # remove program + service, keep data
#         ./uninstall.sh --purge    # also delete the data directory
set -eu

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
say() { printf "${BLUE}==>${NC} %s\n" "$1"; }
ok()  { printf "${GREEN}✓${NC} %s\n" "$1"; }
warn(){ printf "${YELLOW}!${NC} %s\n" "$1"; }

PURGE=0
for arg in "$@"; do
  case "$arg" in
    --purge) PURGE=1 ;;
  esac
done

cat <<'RABBIT'

     (\_/)
     (o.o)     Uninstalling Buster
     (> <)     brought to you by buildly.io

RABBIT

OS="$(uname -s)"
VENV="$HOME/.buster/venv"
SHIM="$HOME/.local/bin/buster"

# 1. Prefer the CLI's own uninstall (handles service + program + data flags).
if [ -x "$VENV/bin/buster" ]; then
  say "Running 'buster uninstall'…"
  if [ "$PURGE" -eq 1 ]; then
    "$VENV/bin/buster" uninstall --purge --yes || warn "CLI uninstall reported an issue; continuing"
  else
    "$VENV/bin/buster" uninstall --yes || warn "CLI uninstall reported an issue; continuing"
  fi
fi

# 2. Belt-and-suspenders: ensure service artifacts and program are gone even if
#    the CLI was already removed or failed.
if [ "$OS" = "Darwin" ]; then
  PLIST="$HOME/Library/LaunchAgents/io.buildly.buster.plist"
  if [ -f "$PLIST" ]; then
    launchctl unload "$PLIST" 2>/dev/null || true
    rm -f "$PLIST"
    ok "Removed launchd agent"
  fi
else
  UNIT="$HOME/.config/systemd/user/buster.service"
  if [ -f "$UNIT" ]; then
    systemctl --user disable --now buster.service 2>/dev/null || true
    rm -f "$UNIT"
    systemctl --user daemon-reload 2>/dev/null || true
    ok "Removed systemd --user service"
  fi
fi

[ -e "$SHIM" ] && { rm -f "$SHIM"; ok "Removed CLI shim $SHIM"; }
[ -d "$VENV" ] && { rm -rf "$HOME/.buster"; ok "Removed $HOME/.buster"; }

if [ "$PURGE" -eq 1 ]; then
  # Data-home locations (see buster/config/paths.py).
  if [ "$OS" = "Darwin" ]; then
    rm -rf "$HOME/Library/Application Support/Buster"
  else
    rm -rf "${XDG_DATA_HOME:-$HOME/.local/share}/buster"
  fi
  warn "Purged Buster data."
else
  echo
  say "Data preserved. To also delete reports/memory/config, re-run with --purge."
fi

echo
ok "Buster uninstalled. Thanks for trying it — buildly.io"
