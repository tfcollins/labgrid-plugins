#!/usr/bin/env bash

# Bash script to build and install ser2net (version 4.6.1) and its dependency gensio (version 2.8.2)
# from source into a custom user prefix.
#
# This solves the RFC2217 serial port locking / purge timeout issue in the default ser2net 4.6.0.

set -euo pipefail

# Default configuration
DEFAULT_PREFIX="/usr/local"
PREFIX="${1:-$DEFAULT_PREFIX}"
WORK_DIR=$(mktemp -d -t ser2net-build-XXXXXX)

SER2NET_VERSION="4.6.1"
GENSIO_VERSION="2.8.2"

echo "=========================================================="
echo "Installing ser2net $SER2NET_VERSION & gensio $GENSIO_VERSION"
echo "Target Prefix: $PREFIX"
echo "Build Directory: $WORK_DIR"
echo "=========================================================="

# 1. Check System Dependencies
DEPS_MISSING=()
if ! pkg-config --exists yaml-0.1 2>/dev/null; then
    DEPS_MISSING+=("libyaml-dev")
fi
if ! pkg-config --exists openssl 2>/dev/null; then
    DEPS_MISSING+=("libssl-dev")
fi
if ! command -v gcc >/dev/null 2>&1; then
    DEPS_MISSING+=("build-essential")
fi
if ! command -v make >/dev/null 2>&1; then
    DEPS_MISSING+=("make")
fi
if ! command -v pkg-config >/dev/null 2>&1; then
    DEPS_MISSING+=("pkg-config")
fi

if [ ${#DEPS_MISSING[@]} -ne 0 ]; then
    echo "ERROR: Missing required build dependencies: ${DEPS_MISSING[*]}"
    echo "Please install them manually using:"
    if [ -f /etc/debian_version ]; then
        echo "  sudo apt-get update && sudo apt-get install -y build-essential pkg-config libyaml-dev libssl-dev curl tar"
    else
        echo "  (equivalent build-essential, pkg-config, libyaml-dev, libssl-dev on your package manager)"
    fi
    exit 1
else
    echo "All system build dependencies are satisfied."
fi

# Uninstall system-provided apt ser2net if present to avoid conflicts
if command -v dpkg >/dev/null 2>&1 && dpkg -s ser2net >/dev/null 2>&1; then
    echo "System-provided ser2net package is currently installed via apt."
    echo "Uninstalling it to prevent conflicts..."
    if [ "$(id -u)" -eq 0 ]; then
        apt-get remove -y ser2net
    elif command -v sudo >/dev/null 2>&1; then
        sudo apt-get remove -y ser2net
    else
        echo "ERROR: System-provided ser2net is installed but we cannot run sudo to remove it."
        echo "Please run: 'sudo apt-get remove -y ser2net' manually first."
        exit 1
    fi
fi

# Determine if we need sudo for installing to $PREFIX
INSTALL_PREFIX_WRITABLE=0
if [ ! -d "$PREFIX" ]; then
    if [ "$(id -u)" -eq 0 ]; then
        INSTALL_PREFIX_WRITABLE=1
    elif command -v sudo >/dev/null 2>&1; then
        INSTALL_PREFIX_WRITABLE=0
    else
        [ -w "$(dirname "$PREFIX")" ] && INSTALL_PREFIX_WRITABLE=1 || INSTALL_PREFIX_WRITABLE=0
    fi
else
    [ -w "$PREFIX" ] && INSTALL_PREFIX_WRITABLE=1 || INSTALL_PREFIX_WRITABLE=0
fi

make_install() {
    if [ "$INSTALL_PREFIX_WRITABLE" -eq 1 ]; then
        make install
    else
        echo "Root/sudo privileges required to install to $PREFIX. Running sudo make install..."
        sudo make install
    fi
}

run_ldconfig() {
    if [ "$PREFIX" = "/usr/local" ] || [ "$PREFIX" = "/usr" ]; then
        echo "Updating shared library cache..."
        if [ "$(id -u)" -eq 0 ]; then
            ldconfig
        elif command -v sudo >/dev/null 2>&1; then
            sudo ldconfig
        fi
    fi
}

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
curl -LO "https://downloads.sourceforge.net/project/ser2net/ser2net/gensio-$GENSIO_VERSION.tar.gz"
tar -xzf "gensio-$GENSIO_VERSION.tar.gz"

echo "Building and installing gensio $GENSIO_VERSION..."
cd "gensio-$GENSIO_VERSION"
./configure --prefix="$PREFIX"
make -j"$(nproc 2>/dev/null || echo 2)"
make_install
run_ldconfig
cd ..

# 3. Download and Build ser2net
echo "----------------------------------------------------------"
echo "Downloading ser2net $SER2NET_VERSION..."
echo "----------------------------------------------------------"
curl -LO "https://downloads.sourceforge.net/project/ser2net/ser2net/ser2net-$SER2NET_VERSION.tar.gz"
tar -xzf "ser2net-$SER2NET_VERSION.tar.gz"

echo "Building and installing ser2net $SER2NET_VERSION..."
cd "ser2net-$SER2NET_VERSION"

# We must set PKG_CONFIG_PATH so configure finds the custom gensio we just built.
# We also set CPPFLAGS and LDFLAGS to prioritize our custom gensio headers and libraries
# and bake the rpath of our prefix's lib directory so the executable can find libgensio at runtime.
export PKG_CONFIG_PATH="$PREFIX/lib/pkgconfig:${PKG_CONFIG_PATH:-}"
export CPPFLAGS="-I$PREFIX/include ${CPPFLAGS:-}"
export LDFLAGS="-L$PREFIX/lib -Wl,-rpath,$PREFIX/lib ${LDFLAGS:-}"

./configure --prefix="$PREFIX"
make -j"$(nproc 2>/dev/null || echo 2)"
make_install
run_ldconfig

echo "=========================================================="
echo "Installation complete!"
echo "=========================================================="
echo "Verify installation:"
echo "  ser2net -v"
echo ""
if [ "$PREFIX" = "/usr/local" ] || [ "$PREFIX" = "/usr" ]; then
    echo "ser2net was installed to a global system path ($PREFIX/sbin/ser2net)."
    echo "It should be automatically available on your PATH."
else
    echo "To use this version, add it to your PATH:"
    echo "  export PATH=\"$PREFIX/sbin:\$PATH\""
fi
echo "=========================================================="
