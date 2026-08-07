#!/usr/bin/env bash

# Bash script to build and install ser2net (version 4.6.1) and its dependency gensio (version 2.8.2)
# from source into a custom user prefix.
#
# This solves the RFC2217 serial port locking / purge timeout issue in the default ser2net 4.6.0.

set -euo pipefail

# Default configuration
DEFAULT_PREFIX="$HOME/opt/ser2net-4.6.1"
PREFIX="${1:-$DEFAULT_PREFIX}"
WORK_DIR=$(mktemp -d -t ser2net-build-XXXXXX)

SER2NET_VERSION="4.6.1"
GENSIO_VERSION="2.8.2"

echo "=========================================================="
echo "Installing ser2net $SER2NET_VERSION & gensio $GENSIO_VERSION"
echo "Target Prefix: $PREFIX"
echo "Build Directory: $WORK_DIR"
echo "=========================================================="

# 1. Check/Install System Dependencies
if [ -f /etc/debian_version ]; then
    echo "Debian/Ubuntu-based system detected."
    echo "Ensuring required build tools and dependencies are installed..."
    
    # We use non-interactive mode. If running as non-root, check if sudo is available.
    DEPS="build-essential pkg-config libyaml-dev libssl-dev curl tar"
    
    if [ "$(id -u)" -eq 0 ]; then
        apt-get update && apt-get install -y $DEPS
    elif command -v sudo >/dev/null 2>&1; then
        echo "Running: sudo apt-get update && sudo apt-get install -y $DEPS"
        sudo apt-get update && sudo apt-get install -y $DEPS
    else
        echo "WARNING: Not running as root and 'sudo' is not available."
        echo "Please ensure the following packages are installed: $DEPS"
    fi
else
    echo "Non-Debian system detected. Please ensure you have equivalent build tools"
    echo "(gcc, make, pkg-config, libyaml, openssl, curl, tar) installed."
fi

# Clean up build dir on exit
cleanup() {
    echo "Cleaning up build directory..."
    rm -rf "$WORK_DIR"
}
trap cleanup EXIT

cd "$WORK_DIR"

# 2. Download and Build gensio
echo "----------------------------------------------------------"
echo "Downloading gensio $GENSIO_VERSION..."
echo "----------------------------------------------------------"
curl -LO "https://github.com/cminyard/gensio/archive/refs/tags/v$GENSIO_VERSION.tar.gz"
tar -xzf "v$GENSIO_VERSION.tar.gz"

echo "Building and installing gensio $GENSIO_VERSION..."
cd "gensio-$GENSIO_VERSION"
./configure --prefix="$PREFIX"
make -j"$(nproc 2>/dev/null || echo 2)"
make install
cd ..

# 3. Download and Build ser2net
echo "----------------------------------------------------------"
echo "Downloading ser2net $SER2NET_VERSION..."
echo "----------------------------------------------------------"
curl -LO "https://github.com/cminyard/ser2net/archive/refs/tags/v$SER2NET_VERSION.tar.gz"
tar -xzf "v$SER2NET_VERSION.tar.gz"

echo "Building and installing ser2net $SER2NET_VERSION..."
cd "ser2net-$SER2NET_VERSION"

# We must set PKG_CONFIG_PATH so configure finds the custom gensio we just built.
# We also set LDFLAGS to bake the rpath of our prefix's lib directory so the
# executable can find libgensio at runtime without LD_LIBRARY_PATH.
export PKG_CONFIG_PATH="$PREFIX/lib/pkgconfig:${PKG_CONFIG_PATH:-}"
export LDFLAGS="-Wl,-rpath,$PREFIX/lib ${LDFLAGS:-}"

./configure --prefix="$PREFIX"
make -j"$(nproc 2>/dev/null || echo 2)"
make install

echo "=========================================================="
echo "Installation complete!"
echo "=========================================================="
echo "Verify installation:"
echo "  $PREFIX/sbin/ser2net -v"
echo ""
echo "To use this version with labgrid-exporter, add it to your PATH:"
echo "  export PATH=\"$PREFIX/sbin:\$PATH\""
echo "=========================================================="
