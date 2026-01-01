// Reachy Mini Home Assistant Voice Assistant UI

document.addEventListener('DOMContentLoaded', function() {
    const statusDot = document.getElementById('statusDot');
    const statusText = document.getElementById('statusText');
    const startBtn = document.getElementById('startBtn');
    const stopBtn = document.getElementById('stopBtn');

    // Check initial status
    checkStatus();

    // Start button click handler
    startBtn.addEventListener('click', function() {
        // This will be handled by the Reachy Mini dashboard
        console.log('Start button clicked');
    });

    // Stop button click handler
    stopBtn.addEventListener('click', function() {
        // This will be handled by the Reachy Mini dashboard
        console.log('Stop button clicked');
    });

    // Check status periodically
    setInterval(checkStatus, 5000);
});

function checkStatus() {
    // In a real implementation, this would check the actual status
    // For now, we'll just update the UI
    const statusDot = document.getElementById('statusDot');
    const statusText = document.getElementById('statusText');

    // Simulate status check
    // In production, this would make an API call to get the actual status
    const isRunning = false; // Change this based on actual status

    if (isRunning) {
        statusDot.classList.add('running');
        statusDot.classList.remove('stopped');
        statusText.textContent = '运行中';
    } else {
        statusDot.classList.add('stopped');
        statusDot.classList.remove('running');
        statusText.textContent = '未运行';
    }
}