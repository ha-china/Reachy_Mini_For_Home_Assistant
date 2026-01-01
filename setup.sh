#!/bin/bash
# Setup script for Reachy Mini Home Assistant Voice Assistant

set -e

echo "Setting up Reachy Mini Home Assistant Voice Assistant..."

# Create virtual environment
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

# Activate virtual environment
source .venv/bin/activate

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip setuptools wheel

# Install dependencies
echo "Installing Python dependencies..."
pip install -r requirements.txt

# Install package
echo "Installing package..."
pip install -e .

echo ""
echo "Setup complete!"
echo ""
echo "All wake word models and sound files are already included."
echo ""
echo "Run the application:"
echo "  python -m reachy_mini_ha_voice --name 'ReachyMini' --enable-reachy"
echo ""
echo "For more information, see README.md"