#!/bin/bash

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

HARD_MISSING=0

echo "Ganesh AI Assistant - Environment Preflight Check"
echo "================================================"

check_version() {
    local name=$1
    local cmd=$2
    local min_ver=$3
    local hard=$4
    
    if ! command -v $cmd &> /dev/null; then
        if [ "$hard" -eq 1 ]; then
            echo -e "${RED}[FAIL]${NC} $name is missing (Required >= $min_ver)"
            HARD_MISSING=1
        else
            echo -e "${YELLOW}[WARN]${NC} $name is missing (Optional)"
        fi
        return 1
    fi

    local current_ver=$($cmd --version 2>&1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -n1)
    if [ -z "$current_ver" ]; then
        current_ver=$($cmd -v 2>&1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -n1)
    fi

    if [ -n "$current_ver" ]; then
        local major=$(echo $current_ver | cut -d. -f1)
        local min_major=$(echo $min_ver | cut -d. -f1)

        if [ "$major" -lt "$min_major" ]; then
            if [ "$hard" -eq 1 ]; then
                echo -e "${RED}[FAIL]${NC} $name version $current_ver < $min_ver"
                HARD_MISSING=1
            else
                echo -e "${YELLOW}[WARN]${NC} $name version $current_ver < $min_ver"
            fi
        else
            echo -e "${GREEN}[PASS]${NC} $name $current_ver"
        fi
    else
        if [ "$hard" -eq 1 ]; then
            echo -e "${RED}[FAIL]${NC} $name version could not be detected"
            HARD_MISSING=1
        else
            echo -e "${YELLOW}[WARN]${NC} $name version could not be detected"
        fi
    fi
}

check_version "Python" "python3" "3.11.0" 1
check_version "Node.js" "node" "20.0.0" 1
check_version "npm" "npm" "10.0.0" 1

if ! command -v cargo &> /dev/null; then
    echo -e "${RED}[FAIL]${NC} Rust (cargo) is missing. Install from https://rustup.rs/"
    HARD_MISSING=1
else
    RUST_VER=$(rustc --version | cut -d' ' -f2)
    echo -e "${GREEN}[PASS]${NC} Rust $RUST_VER"
fi

if ! cargo tauri --version &> /dev/null; then
    echo -e "${YELLOW}[WARN]${NC} Tauri CLI is missing. Install with: cargo install tauri-cli --version '^2.0.0-beta'"
else
    TAURI_VER=$(cargo tauri --version | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -n1)
    echo -e "${GREEN}[PASS]${NC} Tauri CLI $TAURI_VER"
fi

DEPS=("libwebkit2gtk-4.1-dev" "libssl-dev" "libayatana-appindicator3-dev" "librsvg2-dev")
MISSING_DEPS=()
for dep in "${DEPS[@]}"; do
    if ! dpkg -s "$dep" &> /dev/null; then
        MISSING_DEPS+=("$dep")
    fi
done

if [ ${#MISSING_DEPS[@]} -gt 0 ]; then
    echo -e "${YELLOW}[WARN]${NC} Missing system dependencies: ${MISSING_DEPS[*]}"
    echo "       Install with: sudo apt-get install ${MISSING_DEPS[*]}"
else
    echo -e "${GREEN}[PASS]${NC} System dependencies met"
fi

FREE_SPACE=$(df -BG . | awk 'NR==2 {print $4}' | sed 's/G//')
if [ "$FREE_SPACE" -lt 5 ]; then
    echo -e "${YELLOW}[WARN]${NC} Low disk space: ${FREE_SPACE}GB free (Recommended >= 5GB)"
else
    echo -e "${GREEN}[PASS]${NC} Disk space: ${FREE_SPACE}GB free"
fi

echo "------------------------------------------------"
if [ "$HARD_MISSING" -eq 1 ]; then
    echo -e "Preflight check failed. Please install missing requirements."
    exit 1
else
    echo -e "Preflight check passed!"
    exit 0
fi
