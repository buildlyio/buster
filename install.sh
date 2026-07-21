#!/bin/sh
# Buster installer — macOS & Linux, no root required for normal setup.
# Usage:  ./install.sh        (from a checkout)
#         curl -fsSL https://install.buster.buildly.io | sh
set -eu

BLUE='\033[0;34m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
say() { printf "${BLUE}==>${NC} %s\n" "$1"; }
ok()  { printf "${GREEN}✓${NC} %s\n" "$1"; }
warn(){ printf "${YELLOW}!${NC} %s\n" "$1"; }

# 1. Detect OS + arch --------------------------------------------------------
OS="$(uname -s)"; ARCH="$(uname -m)"
case "$OS" in
  Darwin) PLATFORM="macos" ;;
  Linux)  PLATFORM="linux" ;;
  *) echo "Unsupported OS: $OS (macOS and Linux only)"; exit 1 ;;
esac
say "Detected $PLATFORM ($ARCH)"

# 2. Locate a source checkout or clone --------------------------------------
SCRIPT_DIR="$(cd "$(dirname "$0")" 2>/dev/null && pwd || echo "")"
if [ -n "$SCRIPT_DIR" ] && [ -f "$SCRIPT_DIR/pyproject.toml" ]; then
  SRC="$SCRIPT_DIR"
else
  SRC="${BUSTER_SRC:-$HOME/.buster-src}"
  if [ ! -d "$SRC/.git" ]; then
    say "Cloning Buster into $SRC"
    git clone --depth 1 https://github.com/buildlyio/buster "$SRC"
  fi
fi
say "Using source at $SRC"

# 3. Ensure Python 3.11+ -----------------------------------------------------
PY=""
for c in python3.13 python3.12 python3.11 python3; do
  if command -v "$c" >/dev/null 2>&1; then
    V="$("$c" -c 'import sys;print(sys.version_info[0]*100+sys.version_info[1])' 2>/dev/null || echo 0)"
    if [ "$V" -ge 311 ] 2>/dev/null; then PY="$c"; break; fi
  fi
done
[ -z "$PY" ] && { echo "Python 3.11+ required. Please install it and re-run."; exit 1; }
ok "Python: $($PY --version)"

# 4. Install uv when permitted (optional, faster) ---------------------------
if ! command -v uv >/dev/null 2>&1; then
  if [ "${BUSTER_USE_UV:-1}" = "1" ]; then
    say "Installing uv (fast Python installer)…"
    curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null 2>&1 || warn "uv install skipped"
    [ -f "$HOME/.local/bin/env" ] && . "$HOME/.local/bin/env" || true
  fi
fi

# 5. Create an isolated environment + install Buster ------------------------
VENV="$HOME/.buster/venv"
say "Creating environment at $VENV"
mkdir -p "$HOME/.buster"
if command -v uv >/dev/null 2>&1; then
  uv venv --python "$PY" "$VENV" >/dev/null
  uv pip install --python "$VENV/bin/python" -e "$SRC" >/dev/null
else
  "$PY" -m venv "$VENV"
  "$VENV/bin/pip" install --upgrade pip >/dev/null
  "$VENV/bin/pip" install -e "$SRC" >/dev/null
fi
ok "Buster installed"

# 6. Create a launcher on PATH ----------------------------------------------
BIN_DIR="$HOME/.local/bin"; mkdir -p "$BIN_DIR"
cat > "$BIN_DIR/buster" <<EOF
#!/bin/sh
exec "$VENV/bin/buster" "\$@"
EOF
chmod +x "$BIN_DIR/buster"
case ":$PATH:" in *":$BIN_DIR:"*) : ;; *) warn "Add $BIN_DIR to your PATH";; esac

# 7. Install the user-level service -----------------------------------------
if [ "$PLATFORM" = "macos" ]; then
  PLIST="$HOME/Library/LaunchAgents/io.buildly.buster.plist"
  mkdir -p "$HOME/Library/LaunchAgents"
  sed "s#__PY__#$VENV/bin/python#g" "$SRC/deploy/launchd/io.buildly.buster.plist.tmpl" > "$PLIST"
  launchctl unload "$PLIST" 2>/dev/null || true
  launchctl load "$PLIST" 2>/dev/null || warn "Could not load launchd agent (start manually with 'buster start')"
  ok "Installed launchd user agent"
else
  if command -v systemctl >/dev/null 2>&1; then
    UNIT_DIR="$HOME/.config/systemd/user"; mkdir -p "$UNIT_DIR"
    sed "s#__PY__#$VENV/bin/python#g" "$SRC/deploy/systemd/buster.service.tmpl" > "$UNIT_DIR/buster.service"
    systemctl --user daemon-reload 2>/dev/null || true
    systemctl --user enable --now buster.service 2>/dev/null || warn "Could not enable service (start manually with 'buster start')"
    ok "Installed systemd --user service"
  else
    warn "systemd not available; start manually with 'buster start'"
  fi
fi

# 8. Start + report ----------------------------------------------------------
"$BIN_DIR/buster" start >/dev/null 2>&1 || true
PORT="$("$VENV/bin/python" -c 'from buster.config import load_config; print(load_config().server.port)' 2>/dev/null || echo 8765)"
NAME="$("$VENV/bin/python" -c 'from buster.discovery import naming; print(naming.primary_name())' 2>/dev/null || echo buster.local)"
NEEDS_DNS="$("$VENV/bin/python" -c 'from buster.discovery import naming; print("1" if naming.needs_manual_dns() else "0")' 2>/dev/null || echo 0)"

cat <<EOF

$(ok "Buster is running.")

CLI:       buster
Web:       http://$NAME:$PORT
Fallback:  http://localhost:$PORT
Status:    buster status

Inference policy: Local first

Recovery:  buster doctor   ·   buster logs   ·   buster restart
EOF

if [ "$NEEDS_DNS" = "1" ]; then
  echo
  echo "Your domain isn't .local, so mDNS can't publish it. Add these records to"
  echo "your local DNS server (e.g. Pi-hole), then re-run 'buster doctor':"
  "$VENV/bin/python" -c 'from buster.discovery import naming; [print("  A  %s -> %s" % (n, ip)) for n, ip in naming.dns_records()]' 2>/dev/null || true
fi
