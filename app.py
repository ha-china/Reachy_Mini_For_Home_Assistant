"""
Hugging Face Space placeholder.

This is a Reachy Mini App, not a Hugging Face Space.
Install it on your Reachy Mini robot from the App Store.
"""

import gradio as gr

with gr.Blocks(title="Reachy Mini HA Voice") as demo:
    gr.Markdown("""
    # 🤖 Reachy Mini Home Assistant Voice Assistant

    **This is a Reachy Mini App, not a Hugging Face Space.**

    ## Installation

    Install this app directly from your **Reachy Mini Dashboard**:

    1. Open Reachy Mini Dashboard in your browser
    2. Go to **Apps** section
    3. Find **Reachy Mini HA Voice** and click **Install**

    ## Features

    - **Local Wake Word Detection**: Uses microWakeWord for offline wake word detection
    - **ESPHome Integration**: Seamlessly connects to Home Assistant
    - **Motion Control**: Head movements and antenna animations during voice interaction
    - **Zero Configuration**: Install and run - all settings are managed in Home Assistant

    ## Usage

    After installation on Reachy Mini:

    **Automatic Discovery (Recommended):**
    - Home Assistant will automatically discover your Reachy Mini via mDNS
    - A notification will appear in Home Assistant - just click to add the device

    **Manual Setup (if auto-discovery fails):**
    1. Open Home Assistant
    2. Go to **Settings** → **Devices & Services** → **Add Integration**
    3. Search for **ESPHome**
    4. Enter your Reachy Mini's IP address with port `6053`

    Default wake word: **"Okay Nabu"**

    ## Links

    - [Source Code](https://huggingface.co/spaces/djhui5710/reachy_mini_ha_voice/tree/main)
    - [OHF-Voice/linux-voice-assistant](https://github.com/OHF-Voice/linux-voice-assistant)
    - [Pollen Robotics](https://www.pollen-robotics.com/)
    """)

if __name__ == "__main__":
    demo.launch()
