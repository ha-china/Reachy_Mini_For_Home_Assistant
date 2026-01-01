# PowerShell script to download wake word models and sound effects

Write-Host "Downloading wake word models and sound effects..." -ForegroundColor Green

# Create directories if they don't exist
if (-not (Test-Path "wakewords")) {
    New-Item -ItemType Directory -Path "wakewords" | Out-Null
}
if (-not (Test-Path "sounds")) {
    New-Item -ItemType Directory -Path "sounds" | Out-Null
}

# Download wake word models
Write-Host "Downloading okay_nabu model..." -ForegroundColor Yellow
Invoke-WebRequest -Uri "https://github.com/esphome/micro-wake-word-models/raw/main/models/okay_nabu.json" -OutFile "wakewords/okay_nabu.json"
Invoke-WebRequest -Uri "https://github.com/esphome/micro-wake-word-models/raw/main/models/okay_nabu.tflite" -OutFile "wakewords/okay_nabu.tflite"

Write-Host "Downloading hey_jarvis model..." -ForegroundColor Yellow
Invoke-WebRequest -Uri "https://github.com/esphome/micro-wake-word-models/raw/main/models/hey_jarvis.json" -OutFile "wakewords/hey_jarvis.json"
Invoke-WebRequest -Uri "https://github.com/esphome/micro-wake-word-models/raw/main/models/hey_jarvis.tflite" -OutFile "wakewords/hey_jarvis.tflite"

# Download sound effects
Write-Host "Downloading sound effects..." -ForegroundColor Yellow
Invoke-WebRequest -Uri "https://github.com/OHF-Voice/linux-voice-assistant/raw/main/sounds/wake_word_triggered.flac" -OutFile "sounds/wake_word_triggered.flac"
Invoke-WebRequest -Uri "https://github.com/OHF-Voice/linux-voice-assistant/raw/main/sounds/timer_finished.flac" -OutFile "sounds/timer_finished.flac"

Write-Host "Download complete!" -ForegroundColor Green
Write-Host ""
Write-Host "Files downloaded:" -ForegroundColor Cyan
Get-ChildItem wakewords/*.tflite, wakewords/*.json, sounds/*.flac | Select-Object Name, @{Name="Size";Expression={"{0:N2} KB" -f ($_.Length / 1KB)}}