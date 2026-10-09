# Cute Vitals

Small native-looking Linux desktop system monitor for KDE/Qt. It refreshes every second and shows CPU, RAM, NVIDIA, and AMD GPU health with compact coloured gauges.

## Dependencies

- Python 3.10+
- PySide6 or PyQt6
- psutil (required for Windows CPU, RAM, and process readings)
- `nvidia-smi` (optional for NVIDIA cards)
- Linux's `amdgpu` sysfs interface (used automatically for AMD cards)

On Kubuntu:

```bash
cd /home/conner/Documents/GitHub/cute-vitals
python3 -m venv .venv
.venv/bin/pip install PyQt6 psutil
.venv/bin/python cute_vitals.py
```

On Windows, install the dependencies with `py -m pip install PyQt6 psutil`, then run `py cute_vitals.py`. The app reads CPU, RAM, frequency, and process data through psutil on Windows, while Linux continues to use `/proc` and sysfs directly. NVIDIA values use `nvidia-smi`; AMD values use the Linux `amdgpu` sysfs interface when available. ROCm is not required for Linux AMD support.

## Tests

The parser tests do not require a GPU or an open Qt window:

```bash
python3 -m unittest discover -s tests -v
```

## What it shows

- CPU model, total load, package/main temperature, current frequency, and per-core load
- System RAM usage, calculated from total minus Linux's reclaimable `MemAvailable`
- GPU name, temperature, utilisation, VRAM used/total, and power draw
- One-second refresh timestamp, temporary GPU-reader failure handling, and compact always-on-top toggle
