"""
One-click installation UI for Reachy Mini Home Assistant Voice Assistant
"""

import os
import sys
import subprocess
import threading
from pathlib import Path
import gradio as gr


class Installer:
    """One-click installer"""
    
    def __init__(self):
        self.installation_log = []
        self.installation_complete = False
        self.installation_success = False
    
    def log_message(self, message):
        """Add message to log"""
        self.installation_log.append(message)
        return "\n".join(self.installation_log)
    
    def check_python_version(self):
        """Check Python version"""
        try:
            result = subprocess.run(
                [sys.executable, "--version"],
                capture_output=True,
                text=True
            )
            version = result.stdout.strip()
            return True, f"✓ Python version: {version}"
        except Exception as e:
            return False, f"✗ Python check failed: {str(e)}"
    
    def create_venv(self):
        """Create virtual environment"""
        try:
            venv_path = Path(".venv")
            if venv_path.exists():
                return True, "✓ Virtual environment already exists"
            
            subprocess.run(
                [sys.executable, "-m", "venv", ".venv"],
                check=True,
                capture_output=True,
                text=True
            )
            return True, "✓ Virtual environment created"
        except Exception as e:
            return False, f"✗ Failed to create virtual environment: {str(e)}"
    
    def install_dependencies(self):
        """Install dependencies"""
        try:
            pip_path = Path(".venv/bin/pip") if os.name != "nt" else Path(".venv/Scripts/pip.exe")
            
            subprocess.run(
                [str(pip_path), "install", "--upgrade", "pip"],
                check=True,
                capture_output=True,
                text=True
            )
            
            subprocess.run(
                [str(pip_path), "install", "-e", "."],
                check=True,
                capture_output=True,
                text=True
            )
            return True, "✓ Dependencies installed"
        except Exception as e:
            return False, f"✗ Failed to install dependencies: {str(e)}"
    
    def download_models(self):
        """Download models and sounds"""
        try:
            # Run download script
            if os.name == "nt":
                subprocess.run(
                    ["powershell", "-ExecutionPolicy", "Bypass", "-File", "download_models.ps1"],
                    check=True,
                    capture_output=True,
                    text=True
                )
            else:
                subprocess.run(
                    ["./download_models.sh"],
                    check=True,
                    capture_output=True,
                    text=True
                )
            return True, "✓ Models and sounds downloaded"
        except Exception as e:
            return False, f"✗ Failed to download models: {str(e)}"
    
    def create_config(self):
        """Create configuration file"""
        try:
            if not Path(".env").exists():
                subprocess.run(
                    ["cp", ".env.example", ".env"],
                    check=True,
                    capture_output=True
                )
                return True, "✓ Configuration file created"
            else:
                return True, "✓ Configuration file already exists"
        except Exception as e:
            return False, f"✗ Failed to create configuration: {str(e)}"
    
    def check_reachy_sdk(self):
        """Check Reachy Mini SDK"""
        try:
            pip_path = Path(".venv/bin/pip") if os.name != "nt" else Path(".venv/Scripts/pip.exe")
            result = subprocess.run(
                [str(pip_path), "show", "reachy-mini"],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                return True, "✓ Reachy Mini SDK is installed"
            else:
                return False, "⚠ Reachy Mini SDK is not installed. Please install with: pip install reachy-mini"
        except Exception as e:
            return False, f"⚠ Could not check Reachy Mini SDK: {str(e)}"
    
    def run_installation(self):
        """Run complete installation"""
        self.installation_log = []
        self.installation_complete = False
        self.installation_success = False
        
        steps = [
            ("Checking Python version", self.check_python_version),
            ("Creating virtual environment", self.create_venv),
            ("Installing dependencies", self.install_dependencies),
            ("Downloading models and sounds", self.download_models),
            ("Creating configuration", self.create_config),
            ("Checking Reachy Mini SDK", self.check_reachy_sdk),
        ]
        
        all_success = True
        for step_name, step_func in steps:
            self.log_message(f"\n{step_name}...")
            success, message = step_func()
            self.log_message(message)
            
            if not success and "⚠" not in message:
                all_success = False
        
        self.installation_complete = True
        self.installation_success = all_success
        
        if all_success:
            self.log_message("\n" + "="*60)
            self.log_message("✓ Installation completed successfully!")
            self.log_message("="*60)
            self.log_message("\nNext steps:")
            self.log_message("1. Edit .env file to configure your settings")
            self.log_message("2. Run: source .venv/bin/activate && python -m reachy_mini_ha_voice")
        else:
            self.log_message("\n" + "="*60)
            self.log_message("✗ Installation completed with errors")
            self.log_message("="*60)
            self.log_message("\nPlease check the errors above and try again.")
        
        return "\n".join(self.installation_log)


# Create installer instance
installer = Installer()


def start_installation():
    """Start installation in background thread"""
    def run_install():
        installer.run_installation()
    
    thread = threading.Thread(target=run_install)
    thread.start()
    
    return "Installation started... Please wait."


def get_installation_status():
    """Get current installation status"""
    if not installer.installation_complete:
        return installer.log_message("\n⏳ Installation in progress...")
    elif installer.installation_success:
        return installer.log_message("\n✅ Installation completed successfully!")
    else:
        return installer.log_message("\n❌ Installation failed with errors")


def create_ui():
    """Create Gradio UI"""
    with gr.Blocks(title="Reachy Mini Voice Assistant - Installation") as demo:
        gr.Markdown("# 🤖 Reachy Mini Home Assistant Voice Assistant")
        gr.Markdown("## One-Click Installation")
        
        gr.Markdown(
            """
            This installer will automatically:
            - ✓ Check Python version
            - ✓ Create virtual environment
            - ✓ Install all dependencies
            - ✓ Download wake word models and sound effects
            - ✓ Create configuration file
            - ✓ Check Reachy Mini SDK
            """
        )
        
        with gr.Row():
            install_btn = gr.Button("🚀 Start Installation", variant="primary", size="lg")
        
        with gr.Row():
            status_output = gr.Textbox(
                label="Installation Status",
                lines=20,
                placeholder="Click 'Start Installation' to begin...",
                interactive=False
            )
        
        refresh_btn = gr.Button("🔄 Refresh Status")
        
        # Event handlers
        install_btn.click(
            fn=start_installation,
            outputs=status_output
        )
        
        refresh_btn.click(
            fn=get_installation_status,
            outputs=status_output
        )
        
        gr.Markdown("---")
        gr.Markdown("### After Installation")
        gr.Markdown(
            """
            Once installation is complete, you can start the application:
            
            ```bash
            # Activate virtual environment
            source .venv/bin/activate  # Linux/Mac
            .venv\\Scripts\\Activate.ps1  # Windows
            
            # Run the application
            python -m reachy_mini_ha_voice
            ```
            
            For more information, see [README.md](README.md) or [QUICKSTART.md](QUICKSTART.md).
            """
        )
    
    return demo


if __name__ == "__main__":
    ui = create_ui()
    ui.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        show_error=True
    )