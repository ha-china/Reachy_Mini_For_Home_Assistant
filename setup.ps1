# Setup script for Reachy Mini Home Assistant Voice Assistant (Windows)

Write-Host "Setting up Reachy Mini Home Assistant Voice Assistant..." -ForegroundColor Green

# Create virtual environment
if (-not (Test-Path ".venv")) {
    Write-Host "Creating virtual environment..." -ForegroundColor Yellow
    python -m venv .venv
}

# Activate virtual environment
.venv\Scripts\Activate.ps1

# Upgrade pip
Write-Host "Upgrading pip..." -ForegroundColor Yellow
pip install --upgrade pip setuptools wheel

# Install dependencies
Write-Host "Installing Python dependencies..." -ForegroundColor Yellow
pip install -r requirements.txt

# Install package
Write-Host "Installing package..." -ForegroundColor Yellow
pip install -e .

Write-Host ""
Write-Host "Setup complete!" -ForegroundColor Green
Write-Host ""
Write-Host "All wake word models and sound files are already included." -ForegroundColor Cyan
Write-Host ""
Write-Host "Run the application:" -ForegroundColor White
Write-Host "  python -m reachy_mini_ha_voice --name 'ReachyMini' --enable-reachy" -ForegroundColor Gray
Write-Host ""
Write-Host "For more information, see README.md" -ForegroundColor Gray