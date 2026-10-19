#!/bin/sh
set -eu
BASE_URL="${BASE_URL:-http://localhost:8080}"
echo "Checking $BASE_URL/api/health/live"
curl --fail --silent --show-error "$BASE_URL/api/health/live"
echo
echo "Checking $BASE_URL/api/health/ready"
curl --fail --silent --show-error "$BASE_URL/api/health/ready"
echo
echo "Smoke test passed (API + database ready)."
