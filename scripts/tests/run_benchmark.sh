#!/bin/bash
# Resource Processing Benchmark Suite
# Runs the full test suite, generates reports, and tracks quality trends.

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TIMESTAMP=$(date +%Y-%m-%d_%H%M%S)

echo "=========================================="
echo "  Resource Processing Benchmark"
echo "  $TIMESTAMP"
echo "=========================================="

cd "$REPO_ROOT"

# Activate virtual environment if present
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
elif [ -d "venv" ]; then
    source venv/bin/activate
fi

# Ensure dependencies
echo ""
echo "Checking system dependencies..."
python -c "import pdfplumber; import pptx; import PIL; import cv2; import pytesseract" 2>/dev/null || {
    echo "WARNING: Some dependencies missing. Run: pip install -r requirements.txt"
}

# Run the test suite
echo ""
echo "Running test suite..."
python "$SCRIPT_DIR/resource_processing_test/run_test.py" \
    --historical \
    --quality-dir "$SCRIPT_DIR/resource_processing_test/quality_reports" \
    --verbose

# Save the exit code
EXIT_CODE=$?

# Generate trend report
echo ""
echo "Quality Trend Analysis..."
python "$SCRIPT_DIR/resource_processing_test/analyze_corrections.py" \
    --corrections-dir "$SCRIPT_DIR/resource_processing_test/corrections" \
    --suggest-tweaks 2>/dev/null || echo "(no corrections yet)"

echo ""
echo "Benchmark completed: $TIMESTAMP"
exit $EXIT_CODE
