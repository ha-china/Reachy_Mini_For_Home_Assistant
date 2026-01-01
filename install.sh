#!/bin/bash
# Automated installation script for Reachy Mini Home Assistant Voice Assistant

set -e  # Exit on error

echo "=========================================="
echo "Reachy Mini Home Assistant Voice Assistant"
echo "Automated Installation Script"
echo "=========================================="
echo ""

# Check Python version
echo "Checking Python version..."
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 8 ]); then
    echo "Error: Python 3.8 or higher is required. Found: $PYTHON_VERSION"
    exit 1
fi

echo "✓ Python version: $PYTHON_VERSION"
echo ""

# Create virtual environment
echo "Creating virtual environment..."
python3 -m venv .venv
echo "✓ Virtual environment created"
echo ""

# Activate virtual environment
echo "Activating virtual environment..."
source .venv/bin/activate
echo "✓ Virtual environment activated"
echo ""

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip
echo "✓ Pip upgraded"
echo ""

# Install dependencies
echo "Installing dependencies..."
pip install -e .
echo "✓ Dependencies installed"
echo ""

# Download wake word models and sound effects
echo "Downloading wake word models and sound effects..."
./download_models.sh
echo "✓ Models and sound effects downloaded"
echo ""

# Copy environment template
echo "Creating environment configuration..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo "✓ Created .env file from template"
else
    echo "⚠ .env file already exists, skipping..."
fi
echo ""

# Check if Reachy Mini SDK is installed
echo "Checking Reachy Mini SDK..."
if python -c "import reachy_mini" 2>/dev/null; then
    echo "✓ Reachy Mini SDK is installed"
else
    echo "⚠ Reachy Mini SDK is not installed"
    echo "  Please install it with: pip install reachy-mini"
    echo "  Or for wireless version: pip install reachy-mini[wireless]"
fi
echo ""

# Check audio devices
echo "Checking audio devices..."
python -m reachy_mini_ha_voice --list-input-devices 2>/dev/null || echo "  (Will check on first run)"
python -m reachy_mini_ha_voice --list-output-devices 2>/dev/null || echo "  (Will check on first run)"
echo ""

# Installation complete
echo "=========================================="
echo "✓ Installation complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Edit .env file to configure your settings"
echo "2. Run the application:"
echo "   source .venv/bin/activate"
echo "   python -m reachy_mini_ha_voice"
echo ""
echo "For more information, see README.md or QUICKSTART.md"
echo ""