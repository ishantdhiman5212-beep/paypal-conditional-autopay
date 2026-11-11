#!/usr/bin/env bash
cd "$(dirname "$0")"

echo "========================================================="
echo "   PayPal Conditional Autopay - AI Mandate Firewall"
echo "========================================================="
echo ""

# Check python3
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python 3 is not installed."
    echo "Please install Python 3.10+ from https://www.python.org/"
    exit 1
fi

echo "[1/3] Python detected: $(python3 --version)"
echo ""

echo "[2/3] Checking dependencies..."
python3 -m pip install -r requirements.txt --quiet
echo ""

echo "[3/3] Starting web application server..."
echo "========================================================="
echo " Server is LIVE at: http://localhost:5000"
echo " Press Ctrl+C in this terminal window to stop."
echo "========================================================="
echo ""

# Open browser if available
if command -v xdg-open &> /dev/null; then
    xdg-open http://localhost:5000 &
elif command -v open &> /dev/null; then
    open http://localhost:5000 &
fi

python3 app.py
