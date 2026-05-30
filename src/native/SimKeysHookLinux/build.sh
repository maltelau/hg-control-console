#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
OUT="${1:-${SCRIPT_DIR}/libSimKeysHookLinux.so}"
BUNDLE_OUT="${SIMKEYS_LINUX_BUNDLE_OUT:-${REPO_ROOT}/bin/libSimKeysHookLinux.so}"
read -r -a CXX_CMD <<< "${CXX:-g++}"

"${CXX_CMD[@]}" \
  -m32 \
  -std=gnu++11 \
  -O2 \
  -fPIC \
  -shared \
  -fno-exceptions \
  -fno-rtti \
  -nostdlib++ \
  -Wall \
  -Wextra \
  -Wno-unused-parameter \
  -Wno-unused-const-variable \
  -Wno-format-truncation \
  -o "${OUT}" \
  "${SCRIPT_DIR}/SimKeysHookLinux.cpp" \
  -ldl \
  -lpthread

if [[ -n "${BUNDLE_OUT}" ]]; then
  mkdir -p "$(dirname "${BUNDLE_OUT}")"
  cp "${OUT}" "${BUNDLE_OUT}"
fi

file "${OUT}" || true
if [[ -n "${BUNDLE_OUT}" ]]; then
  file "${BUNDLE_OUT}" || true
fi
