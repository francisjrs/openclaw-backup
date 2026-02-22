#!/usr/bin/env bash
set -euo pipefail

IMG_PATH="${1:-}"
if [[ -z "$IMG_PATH" || ! -f "$IMG_PATH" ]]; then
  echo "ERROR: image path missing or not found"
  exit 2
fi

if [[ -z "${TRMNL_API_KEY:[API_KEY]" || -z "${TRMNL_DEVICE_ID:-}" ]]; then
  echo "ERROR: TRMNL_API_KEY or TRMNL_DEVICE_ID missing"
  exit 3
fi

curl -sS -X POST "https://usetrmnl.com/api/devices/${TRMNL_DEVICE_ID}/display" \
  -H "Authorization: Bearer ${TRMNL_API_KEY}" \
  -F "file=@${IMG_PATH}" \
  -F "content_type=image/png"

echo "TRMNL push OK: ${IMG_PATH}"