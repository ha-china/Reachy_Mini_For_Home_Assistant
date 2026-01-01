"""Setup script for Reachy Mini Home Assistant Voice Assistant."""

from setuptools import setup, find_packages

setup(
    name="reachy-mini-ha-voice",
    version="1.0.0",
    packages=find_packages(),
    install_requires=[
        "aioesphomeapi==42.7.0",
        "numpy>=2,<3",
        "pymicro-wakeword>=2,<3",
        "pyopen-wakeword>=1,<2",
        "pyaudio>=0.2.11",
        "zeroconf<1",
    ],
    python_requires=">=3.9",
    entry_points={
        "console_scripts": [
            "reachy-mini-ha-voice=reachy_mini_ha_voice.__main__:main",
        ],
    },
)