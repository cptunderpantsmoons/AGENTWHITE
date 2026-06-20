#!/usr/bin/env bash
# Downloads and prepares a Windows embeddable Python distribution with all
# app dependencies installed. Output goes to build/python/ which electron-builder
# bundles as extraResources.
#
# When run on Linux (cross-compile), uses the system Python + pip to install
# packages into the Windows Python's site-packages directory. The pure-Python
# packages are cross-platform; platform-specific wheels are skipped with a warning.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BUILD_DIR="$PROJECT_DIR/build"
PYTHON_DIR="$BUILD_DIR/python"

PYTHON_VERSION="3.12.9"
PYTHON_EMBED_URL="https://www.python.org/ftp/python/${PYTHON_VERSION}/python-${PYTHON_VERSION}-embed-amd64.zip"
PIP_URL="https://bootstrap.pypa.io/get-pip.py"

echo "=== Embedding Python ${PYTHON_VERSION} for Windows ==="

mkdir -p "$PYTHON_DIR"
cd "$PYTHON_DIR"

# Download embeddable Python
if [ ! -f "python.exe" ]; then
    echo "Downloading Python ${PYTHON_VERSION} embeddable..."
    curl -fSL -o python-embed.zip "$PYTHON_EMBED_URL"
    unzip -o python-embed.zip
    rm python-embed.zip
fi

# Modify python312._pth to enable site-packages and relative imports
PTH_FILE=$(ls python*._pth 2>/dev/null | head -1)
if [ -n "$PTH_FILE" ]; then
    cat > "$PTH_FILE" << 'EOF'
python312.zip
.
Lib
Lib\site-packages
..
..\app.asar.unpacked
..\app.asar.unpacked\routes
..\app.asar.unpacked\src
..\app.asar.unpacked\core
..\app.asar.unpacked\services
import site
EOF
fi

# Create site-packages directory
SITE_PKGS="$PYTHON_DIR/Lib/site-packages"
mkdir -p "$SITE_PKGS"

# Install pip into the Windows Python's site-packages
if [ ! -d "$SITE_PKGS/pip" ]; then
    echo "Installing pip..."
    curl -fSL -o get-pip.py "$PIP_URL"
    python3 get-pip.py --target "$SITE_PKGS" --no-warn-script-location 2>&1 | tail -3
    rm -f get-pip.py
fi

# Install app dependencies using system pip into Windows site-packages
# Must specify python-version 3.12 so compiled .pyd extensions match the embedded Python
echo "Installing app dependencies..."
python3 -m pip install \
    --target "$SITE_PKGS" \
    --no-warn-script-location \
    --platform win_amd64 \
    --python-version 3.12 \
    --implementation cp \
    --abi cp312 \
    --only-binary=:all: \
    -r "$PROJECT_DIR/requirements.txt" 2>&1 | tail -10 || true

# Also install pure-Python packages (no platform tag needed)
echo "Installing pure-Python dependencies..."
python3 -m pip install \
    --target "$SITE_PKGS" \
    --no-warn-script-location \
    --no-deps \
    -r "$PROJECT_DIR/requirements.txt" 2>&1 | tail -10 || true

# Copy start_server.py launcher
cp "$PROJECT_DIR/electron/start_server.py" "$PYTHON_DIR/"

echo ""
echo "=== Python embedded at: $PYTHON_DIR ==="
echo "=== Site-packages: $SITE_PKGS ==="
echo "=== Ready for electron-builder ==="
