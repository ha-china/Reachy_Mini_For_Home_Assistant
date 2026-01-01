"""Simple web server for Hugging Face Spaces display."""

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI()


@app.get("/", response_class=HTMLResponse)
async def read_root():
    """Serve the main page."""
    with open("index.html", "r", encoding="utf-8") as f:
        return f.read()


@app.get("/style.css")
async def get_style():
    """Serve the CSS file."""
    return FileResponse("style.css")


@app.get("/main.js")
async def get_script():
    """Serve the JavaScript file."""
    return FileResponse("main.js")