# Automated installation script for Reachy Mini Home Assistant Voice Assistant

$ErrorActionPreference = "Stop"

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Reachy Mini Home Assistant Voice Assistant" -ForegroundColor Cyan
Write-Host "Automated Installation Script" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Check Python version
Write-Host "Checking Python version..." -ForegroundColor Yellow
try {
    $pythonVersion = python --version 2>&1
    Write-Host "✓ Python version: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "✗ Python not found. Please install Python 3.8 or higher." -ForegroundColor Red
    exit 1
}
Write-Host ""

# Create virtual environment
Write-Host "Creating virtual environment..." -ForegroundColor Yellow
python -m venv .venv
Write-Host "✓ Virtual environment created" -ForegroundColor Green
Write-Host ""

# Activate virtual environment
Write-Host "Activating virtual environment..." -ForegroundColor Yellow
& .\.venv\Scripts\Activate.ps1
Write-Host "✓ Virtual environment activated" -ForegroundColor Green
Write-Host ""

# Upgrade pip
Write-Host "Upgrading pip..." -ForegroundColor Yellow
python -m pip install --upgrade pip
Write-Host "✓ Pip upgraded" -ForegroundColor Green
Write-Host ""

# Install dependencies
Write-Host "Installing dependencies..." -ForegroundColor Yellow
pip install -e .
Write-Host "✓ Dependencies installed" -ForegroundColor Green
Write-Host ""

# Download wake word models and sound effects
Write-Host "Downloading wake word models and sound effects..." -ForegroundColor Yellow
powershell -ExecutionPolicy Bypass -File download_models.ps1
Write-Host "✓ Models and sound effects downloaded" -ForegroundColor Green
Write-Host ""

# Copy environment template
Write-Host "Creating environment configuration..." -ForegroundColor Yellow
if (-not (Test-Path ".env")) {
    Copy-Item .env.example .env
    Write-Host "✓ Created .env file from template" -ForegroundColor Green
} else {
    Write-Host "⚠ .env file already exists, skipping..." -ForegroundColor Yellow
}
Write-Host ""

# Check if Reachy Mini SDK is installed
Write-Host "Checking Reachy Mini SDK..." -ForegroundColor Yellow
try {
    python -c "import reachy_mini" 2>$null
    Write-Host "✓ Reachy Mini SDK is installed" -ForegroundColor Green
} catch {
    Write-Host "⚠ Reachy Mini SDK is not installed" -ForegroundColor Yellow
    Write-Host "  Please install it with: pip install reachy-mini" -ForegroundColor Gray
    Write-Host "  Or for wireless version: pip install reachy-mini[wireless]" -ForegroundColor Gray
}
Write-Host ""

# Check audio devices
Write-Host "Checking audio devices..." -ForegroundColor Yellow
try {
    python -m reachy_mini_ha_voice --list-input-devices 2>$null
} catch {
    Write-Host "  (Will check on first run)" -ForegroundColor Gray
}
try {
    python -m reachy_mini_ha_voice --list-output-devices 2>$null
} catch {
    Write-Host "  (Will check on first run)" -ForegroundColor Gray
}
Write-Host ""

# Installation complete
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "✓ Installation complete!" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "1. Edit .env file to configure your settings" -ForegroundColor White
Write-Host "2. Run the application:" -ForegroundColor White
Write-Host "   .\.venv\Scripts\Activate.ps1" -ForegroundColor Gray
Write-Host "   python -m reachy_mini_ha_voice" -ForegroundColor Gray
Write-Host ""
Write-Host "For more information, see README.md or QUICKSTART.md" -ForegroundColor Gray
Write-Host ""