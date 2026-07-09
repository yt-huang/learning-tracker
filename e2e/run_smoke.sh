#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# Learning Tracker E2E Smoke Test Runner
# Uses TestZeus Hercules (AI-driven Gherkin E2E testing)
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
OUTPUT_DIR="${SCRIPT_DIR}/output"
PROOFS_DIR="${SCRIPT_DIR}/proofs"
LOG_DIR="${SCRIPT_DIR}/log_files"

# --- Configuration ---
BASE_URL="${E2E_BASE_URL:-http://127.0.0.1:8010}"
FEATURE_FILE="${SCRIPT_DIR}/smoke.feature"
CONFIG_FILE="${SCRIPT_DIR}/agents_llm_config.json"

# LLM settings (DeepSeek is cheapest, ~$0.01 per full run)
LLM_MODEL="${LLM_MODEL:-deepseek-chat}"
LLM_API_KEY="${DEEPSEEK_API_KEY:?DEEPSEEK_API_KEY must be set}"
LLM_BASE_URL="${LLM_BASE_URL:-https://api.deepseek.com/v1}"
LLM_API_TYPE="${LLM_API_TYPE:-openai}"

# --- Prepare output dirs ---
mkdir -p "$OUTPUT_DIR" "$PROOFS_DIR" "$LOG_DIR"
rm -rf "$OUTPUT_DIR"/* "$PROOFS_DIR"/* "$LOG_DIR"/*

# --- Substitute env vars in feature file and LLM config ---
FEATURE_TMP=$(mktemp --suffix=.feature)
CONFIG_TMP=$(mktemp --suffix=.json)
env E2E_BASE_URL="$BASE_URL" envsubst < "$FEATURE_FILE" > "$FEATURE_TMP"
env DEEPSEEK_API_KEY="$LLM_API_KEY" envsubst < "$CONFIG_FILE" > "$CONFIG_TMP"
trap 'rm -f "$FEATURE_TMP" "$CONFIG_TMP"' EXIT

echo "========================================"
echo " Learning Tracker E2E Smoke Tests"
echo "========================================"
echo " Target:  $BASE_URL"
echo " Feature: $FEATURE_FILE"
echo " Model:   $LLM_MODEL"
echo " Output:  $OUTPUT_DIR"
echo "========================================"
echo ""

# --- Run Hercules ---
AUTO_MODE=1 \
HEADLESS="${HEADLESS:-true}" \
RECORD_VIDEO="${RECORD_VIDEO:-true}" \
TAKE_SCREENSHOTS="${TAKE_SCREENSHOTS:-true}" \
python3 -m testzeus_hercules \
  --input-file "$FEATURE_TMP" \
  --output-path "$OUTPUT_DIR" \
  --agents-llm-config-file "$CONFIG_TMP" \
  --agents-llm-config-file-ref-key deepseek \
  2>&1 | tee "${LOG_DIR}/hercules_run.log"

# --- Check results ---
echo ""
echo "========================================"
echo " Test Results"
echo "========================================"

XML_FILE=$(find "$OUTPUT_DIR" -name '*_result.xml' -print -quit || true)
HTML_FILE=$(find "$OUTPUT_DIR" -name '*_result.html' -print -quit || true)

if [ -z "$XML_FILE" ]; then
  echo "ERROR: No JUnit XML result found in $OUTPUT_DIR"
  exit 1
fi

# Extract pass/fail counts from JUnit XML
PASS_COUNT=$(grep -c 'testcase' "$XML_FILE" 2>/dev/null || echo "0")
FAIL_COUNT=$(grep -c '<failure\|<error' "$XML_FILE" 2>/dev/null || echo "0")

echo " JUnit XML:  $XML_FILE"
echo " HTML Report: $HTML_FILE"
echo " Screenhots: $PROOFS_DIR"
echo " Total Tests: $PASS_COUNT"
echo " Failures:    $FAIL_COUNT"
echo "========================================"

if [ "$FAIL_COUNT" -gt 0 ]; then
  echo "SMOKE TESTS FAILED"
  exit 1
fi

echo "ALL SMOKE TESTS PASSED ✅"