#!/usr/bin/env python3
import math, os, platform, re, subprocess, time
from pathlib import Path

try:
    import psutil
except ImportError:
    psutil = None

# Try PySide6 first, then fall back to PyQt6. Both provide the Qt widgets used here.
try:
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtGui import QColor, QPainter, QPen
    from PySide6.QtCore import QEasingCurve, QPropertyAnimation
    from PySide6.QtWidgets import QApplication, QCheckBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QMainWindow, QProgressBar, QSizePolicy, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget
except ImportError:
    from PyQt6.QtCore import Qt, QTimer
    from PyQt6.QtGui import QColor, QPainter, QPen
    from PyQt6.QtCore import QEasingCurve, QPropertyAnimation
    from PyQt6.QtWidgets import QApplication, QCheckBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QMainWindow, QProgressBar, QSizePolicy, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

# Linux exposes hardware information through virtual files under /sys and /proc.
BASE = Path('/sys')

def read_text(path):
    """Read a small system file, returning None if it is unavailable."""
    try: return Path(path).read_text().strip()
    except (OSError, ValueError): return None

def cpu_model():
    """Find the human-readable CPU model name from /proc/cpuinfo."""
    if os.name == 'nt':
        return platform.processor() or 'CPU'
    for line in (read_text('/proc/cpuinfo') or '').splitlines():
        if line.lower().startswith('model name'):
            return line.split(':', 1)[1].strip()
    return 'CPU'

def ram_reading():
    """Return RAM used and total in MiB using Linux's /proc/meminfo."""
    if os.name == 'nt':
        if psutil is None:
            return None
        memory = psutil.virtual_memory()
        return memory.used / 1024**2, memory.total / 1024**2
    values = {}
    for line in (read_text('/proc/meminfo') or '').splitlines():
        key, _, rest = line.partition(':')
        number = rest.strip().split()[0] if rest.strip() else None
        if number:
            # /proc/meminfo reports memory in KiB; convert to MiB for the UI.
            values[key] = float(number) / 1024
    total = values.get('MemTotal')
    available = values.get('MemAvailable')
    if total is None or available is None:
        return None
    return total - available, total

def cpu_stats():
    """Return cumulative CPU tick counts for the total CPU and each core.

    /proc/stat reports totals since boot. Comparing two samples lets us
    calculate how much of the most recent one-second interval was busy.
    """
    # Windows does not expose /proc/stat; refresh() uses psutil directly there.
    if os.name == 'nt':
        return []
    rows = []
    for line in (read_text('/proc/stat') or '').splitlines():
        p = line.split()
        # The first row is named "cpu" and contains the real system-wide total.
        # Following rows are named cpu0, cpu1, etc. for individual cores.
        if p and (p[0] == 'cpu' or p[0][3:].isdigit()):
            vals = list(map(int, p[1:])); idle = vals[3] + (vals[4] if len(vals) > 4 else 0)
            rows.append((p[0], sum(vals), idle))
    return rows

def parse_temperature(raw):
    """Convert a sysfs millidegree value, ignoring malformed sensor readings."""
    if not raw:
        return None
    try:
        value = float(raw) / 1000
    except ValueError:
        return None
    return value if math.isfinite(value) else None

def temp_reading():
    """Find a sensible CPU temperature from hwmon or thermal-zone sensors."""
    if os.name == 'nt':
        if psutil is not None:
            try:
                sensors = psutil.sensors_temperatures()
                candidates = [(label or name, entry.current) for name, entries in sensors.items() for entry in entries if entry.current is not None for label in [entry.label]]
                if candidates:
                    return candidates[0]
            except (AttributeError, OSError):
                pass
        return 'Unavailable', None
    candidates = []
    for hw in sorted((BASE / 'class/hwmon').glob('hwmon*')):
        name = read_text(hw / 'name') or ''
        for inp in hw.glob('temp*_input'):
            temperature = parse_temperature(read_text(inp))
            if temperature is not None:
                label = read_text(inp.with_name(inp.name.replace('_input', '_label'))) or name or 'Temperature'
                candidates.append((label, temperature))
    for z in sorted((BASE / 'class/thermal').glob('thermal_zone*')):
        temperature = parse_temperature(read_text(z / 'temp'))
        if temperature is not None:
            candidates.append((read_text(z / 'type') or 'Thermal zone', temperature))
    # Prefer a package/main-die reading: that represents the CPU as a whole.
    # Individual "Core 0" readings are only a fallback when no package sensor exists.
    def sensor_priority(item):
        label = item[0].lower()
        if 'package' in label or 'tctl' in label or 'tdie' in label: return 0
        if 'cpu' in label: return 1
        if 'core' in label: return 2
        return 3
    return (sorted(candidates, key=sensor_priority) or [("Unavailable", None)])[0]

def gpu_reading():
    """Read GPU metrics, preferring NVIDIA and then falling back to AMD."""
    # Keep this list aligned with the command requested for the project.
    query = 'name,temperature.gpu,utilization.gpu,memory.used,memory.total,power.draw'
    try:
        # nounits makes the output easier to parse: values arrive as plain numbers.
        p = subprocess.run(['nvidia-smi', f'--query-gpu={query}', '--format=csv,noheader,nounits'], text=True, capture_output=True, timeout=.8)
        if p.returncode == 0 and p.stdout.strip():
            parts = [x.strip() for x in p.stdout.splitlines()[0].split(',')]
            if len(parts) >= 6:
                return {'name': parts[0], 'temp': float(parts[1]), 'load': float(parts[2]), 'mem_used': float(parts[3]), 'mem_total': float(parts[4]), 'power': float(parts[5])}, None
    except (OSError, subprocess.SubprocessError, ValueError) as e:
        pass

    # AMD's open-source amdgpu driver exposes equivalent values directly in sysfs.
    for device in sorted((BASE / 'class/drm').glob('card*/device')):
        if read_text(device / 'vendor') != '0x1002':
            continue
        load = read_text(device / 'gpu_busy_percent')
        used = read_text(device / 'mem_info_vram_used')
        total = read_text(device / 'mem_info_vram_total')
        power = read_text(device / 'power1_average')
        temp = None
        for sensor in sorted((device / 'hwmon').glob('hwmon*/temp*_input')):
            raw = read_text(sensor)
            if raw:
                temp = float(raw) / 1000
                break
        name = read_text(device / 'product_name') or read_text(device / 'device') or 'AMD GPU'
        # AMD VRAM and power sysfs values are bytes and microwatts respectively.
        return {'name': name, 'temp': temp, 'load': float(load) if load else None,
                'mem_used': float(used) / 1024**2 if used else 0,
                'mem_total': float(total) / 1024**2 if total else 0,
                'power': float(power) / 1_000_000 if power else None}, None
    return None, 'No supported NVIDIA or AMD GPU found'

def process_rows():
    """Return the busiest processes using the standard Linux ps utility."""
    if os.name == 'nt':
        if psutil is None:
            return []
        rows = []
        for process in psutil.process_iter(['pid', 'name', 'memory_percent', 'memory_info']):
            try:
                cpu = process.cpu_percent(None)
                info = process.info
                rows.append((str(info['pid']), info['name'] or 'Unknown', cpu, info['memory_percent'] or 0, int((info['memory_info'].rss if info['memory_info'] else 0) / 1024)))
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        return sorted(rows, key=lambda row: row[2], reverse=True)[:12]
    try:
        # ps already calculates process CPU and memory percentages for us.
        result = subprocess.run(['ps', '-eo', 'pid=,comm=,%cpu=,%mem=,rss=', '--sort=-%cpu'], text=True, capture_output=True, timeout=.5)
        rows = []
        for line in result.stdout.splitlines()[:12]:
            parts = line.split()
            if len(parts) >= 5:
                rows.append((parts[0], parts[1], float(parts[2]), float(parts[3]), int(parts[4])))
        return rows
    except (OSError, subprocess.SubprocessError, ValueError):
        return []

class Gauge(QWidget):
    def __init__(self, title, maximum=100, suffix='%'):
        # A Gauge is a label, a numeric value, and a coloured progress bar.
        super().__init__(); self.suffix = suffix; self.max = maximum
        self.title = QLabel(title); self.value = QLabel('—'); self.bar = QProgressBar(); self.bar.setRange(0, maximum); self.bar.setTextVisible(False); self.bar.setFixedHeight(10)
        # Animate the bar instead of snapping it to each one-second reading.
        self.animation = QPropertyAnimation(self.bar, b'value', self)
        # A slightly longer ease-in/ease-out feels smoother than a quick snap.
        self.animation.setDuration(900)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        top = QHBoxLayout(); top.setContentsMargins(0,0,0,0); top.addWidget(self.title); top.addStretch(); top.addWidget(self.value)
        box = QVBoxLayout(self); box.setContentsMargins(0,0,0,0); box.setSpacing(5); box.addLayout(top); box.addWidget(self.bar)
    def set_value(self, val, text=None):
        # None means the metric is unavailable; show that without crashing the UI.
        if val is None: self.value.setText('Unavailable'); target = 0; self.bar.setProperty('level','none')
        else:
            self.value.setText(text or f'{val:.0f}{self.suffix}')
            # Clamp the bar to its range even if a real sensor reports an odd value.
            target = max(0, min(self.max, int(val)))
            # Qt styles the bar according to this custom property.
            self.bar.setProperty('level', 'red' if val >= self.max*.85 else 'amber' if val >= self.max*.65 else 'green')
        # Start from the bar's current position and ease toward the new target.
        self.animation.stop()
        self.animation.setStartValue(self.bar.value())
        self.animation.setEndValue(target)
        self.animation.start()
        self.bar.style().unpolish(self.bar); self.bar.style().polish(self.bar)

class HistoryGraph(QWidget):
    """A small custom-painted line graph for one sensor series."""
    def __init__(self, title, unit, maximum):
        super().__init__(); self.title = title; self.unit = unit; self.maximum = maximum; self.values = []; self.setMinimumHeight(92); self.setMinimumWidth(180)

    def set_values(self, values):
        self.values = values; self.update()

    def paintEvent(self, event):
        painter = QPainter(self); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor('#202331')); painter.setPen(QColor('#eef0f6')); painter.drawText(8, 16, self.title)
        left, top, width, height = 42, 25, self.width() - 50, self.height() - 34
        painter.setPen(QColor('#303548')); painter.drawRect(left, top, width, height)
        # Draw 0, 50, and 100% (or °C) guide markers like a lightweight monitor.
        for fraction in (0, .5, 1):
            y = top + height - fraction * height; painter.setPen(QColor('#303548')); painter.drawLine(left, int(y), left + width, int(y))
            painter.setPen(QColor('#9ba1b5')); painter.drawText(2, int(y + 4), f'{self.maximum * fraction:.0f}{self.unit}')
        if len(self.values) >= 2:
            pen = QPen(QColor('#5cc8f2')); pen.setWidth(2); painter.setPen(pen); points = []
            for i, value in enumerate(self.values):
                x = left + i * width / max(1, len(self.values) - 1); y = top + height - max(0, min(1, value / self.maximum)) * height; points.append((x, y))
            for a, b in zip(points, points[1:]): painter.drawLine(int(a[0]), int(a[1]), int(b[0]), int(b[1]))

class Window(QMainWindow):
    def __init__(self):
        # Store the previous /proc/stat sample so refresh() can calculate usage.
        super().__init__(); self.setWindowTitle('Cute Vitals'); self.resize(430, 700); self.prev = None; self.core_prev = {}; self.gpu_max_power = 250
        root = QWidget(); self.setCentralWidget(root); layout = QVBoxLayout(root); layout.setContentsMargins(18,16,18,16); layout.setSpacing(12)
        head = QHBoxLayout(); title = QLabel('Cute Vitals'); title.setObjectName('title'); head.addWidget(title); head.addStretch(); self.graph_toggle = QCheckBox('Graphs'); self.graph_toggle.toggled.connect(self.toggle_graphs); head.addWidget(self.graph_toggle); self.process_toggle = QCheckBox('Processes'); self.process_toggle.toggled.connect(self.toggle_processes); head.addWidget(self.process_toggle); self.pin = QCheckBox('Stay on top'); self.pin.toggled.connect(self.toggle_top); head.addWidget(self.pin); layout.addLayout(head)
        # Graph data is kept in memory only while the optional graphs are enabled.
        self.history = {'cpu_load': [], 'cpu_temp': [], 'gpu_load': [], 'gpu_temp': []}
        self.cpu_name = QLabel(cpu_model()); self.cpu_name.setObjectName('muted'); layout.addWidget(self.cpu_name)
        cpu_box = self.section('CPU'); grid = QGridLayout(); self.cpu_load=Gauge('Total load'); self.cpu_temp=Gauge('Temperature',100,'°C'); self.cpu_freq=QLabel('Frequency: —'); grid.addWidget(self.cpu_load,0,0); grid.addWidget(self.cpu_temp,1,0); grid.addWidget(self.cpu_freq,2,0); self.cores=QLabel('Per-core: —'); self.cores.setWordWrap(True); grid.addWidget(self.cores,3,0); self.cpu_usage_graph=HistoryGraph('Usage','%',100); self.cpu_temp_graph=HistoryGraph('Temperature','°C',100); self.cpu_graph_column=QWidget(); self.cpu_graphs=QVBoxLayout(self.cpu_graph_column); self.cpu_graphs.addWidget(self.cpu_usage_graph); self.cpu_graphs.addWidget(self.cpu_temp_graph); cpu_content=QHBoxLayout(); cpu_content.addLayout(grid, 1); cpu_content.addWidget(self.cpu_graph_column, 1); cpu_box.layout().addLayout(cpu_content); self.cpu_graph_column.hide(); layout.addWidget(cpu_box)
        # RAM gets its own compact panel because it is a system-wide resource.
        ram_box = self.section('RAM'); self.ram=Gauge('Memory',100,''); ram_box.layout().addWidget(self.ram); layout.addWidget(ram_box)
        gpu_box = self.section('GPU'); self.gpu_name=QLabel('NVIDIA GPU: searching…'); self.gpu_load=Gauge('GPU load'); self.gpu_temp=Gauge('Temperature',100,'°C'); self.vram=Gauge('VRAM',100,''); self.power=Gauge('Power',250,' W'); gpu_metrics=QVBoxLayout(); gpu_metrics.addWidget(self.gpu_name); gpu_metrics.addWidget(self.gpu_load); gpu_metrics.addWidget(self.gpu_temp); gpu_metrics.addWidget(self.vram); gpu_metrics.addWidget(self.power); self.gpu_usage_graph=HistoryGraph('Usage','%',100); self.gpu_temp_graph=HistoryGraph('Temperature','°C',100); self.gpu_graph_column=QWidget(); self.gpu_graphs=QVBoxLayout(self.gpu_graph_column); self.gpu_graphs.addWidget(self.gpu_usage_graph); self.gpu_graphs.addWidget(self.gpu_temp_graph); gpu_content=QHBoxLayout(); gpu_content.addLayout(gpu_metrics, 1); gpu_content.addWidget(self.gpu_graph_column, 1); gpu_box.layout().addLayout(gpu_content); self.gpu_graph_column.hide(); layout.addWidget(gpu_box)
        # Optional Task Manager-style process list; hidden to preserve the compact default view.
        self.process_panel = self.section('Processes'); self.process_table = QTableWidget(0, 5); self.process_table.setHorizontalHeaderLabels(['PID', 'Process', 'CPU', 'Memory', 'RAM']); self.process_table.horizontalHeader().setStretchLastSection(True); self.process_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers); self.process_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection); self.process_table.verticalHeader().setVisible(False); self.process_panel.layout().addWidget(self.process_table); self.process_panel.hide(); layout.addWidget(self.process_panel); layout.addStretch(); self.status=QLabel('Refreshing…'); self.status.setObjectName('muted'); layout.addWidget(self.status)
        self.setStyleSheet('''QMainWindow { background:#171923; color:#eef0f6; } QLabel { font-size:13px; } #title { font-size:24px; font-weight:700; color:#f5a7d7; } #muted { color:#9ba1b5; } QFrame { background:#202331; border:1px solid #303548; border-radius:14px; } QProgressBar { background:#303548; border:0; border-radius:5px; } QProgressBar::chunk { border-radius:5px; background:#65d6a2; } QProgressBar[level="amber"]::chunk { background:#f6c85f; } QProgressBar[level="red"]::chunk { background:#f27d8a; } QCheckBox { color:#b9bfd1; }''')
        # Qt calls refresh every 1,000 ms, then we also refresh immediately on startup.
        self.timer=QTimer(self); self.timer.timeout.connect(self.refresh); self.timer.start(1000); self.refresh()
    def section(self, text):
        """Create one rounded panel containing a section heading."""
        f=QFrame(); f.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Maximum); f.setLayout(QVBoxLayout()); f.layout().setContentsMargins(14,12,14,14); h=QLabel(text); h.setStyleSheet('font-size:16px;font-weight:700;color:#bda7ff;'); f.layout().addWidget(h); return f
    def toggle_top(self, on): self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, on); self.show()
    def toggle_processes(self, on):
        """Show or hide the process table; data is refreshed only while visible."""
        self.process_panel.setVisible(on)

    def toggle_graphs(self, on):
        # Turning graphs off deliberately discards the session's samples.
        for graph in (self.cpu_usage_graph, self.cpu_temp_graph, self.gpu_usage_graph, self.gpu_temp_graph): graph.setVisible(on)
        self.cpu_graph_column.setVisible(on); self.gpu_graph_column.setVisible(on)
        self.resize(850 if on else 430, 700)
        if not on: self.history = {key: [] for key in self.history}

    def refresh(self):
        # The first sample is only a baseline; a percentage needs two samples.
        stats=cpu_stats(); total=core=None
        if os.name == 'nt' and psutil is not None:
            # psutil provides the cross-platform equivalent of /proc/stat on Windows.
            total = psutil.cpu_percent(None)
            core = psutil.cpu_percent(None, percpu=True)
        elif self.prev and stats:
            def pct(old,new):
                # CPU ticks are cumulative. Busy ticks divided by all ticks gives load.
                dt=new[1]-old[1]; di=new[2]-old[2]; return 100*(dt-di)/dt if dt else 0
            total=pct(self.prev[0],stats[0]); core=[pct(self.prev[i+1],stats[i+1]) for i in range(min(len(stats)-1, os.cpu_count() or 1)) if i+1 < len(self.prev)]
        self.prev=stats; self.cpu_load.set_value(total); label,temp=temp_reading(); self.cpu_temp.set_value(temp, f'{temp:.1f}°C' if temp is not None else None)
        if os.name == 'nt' and psutil is not None:
            frequency = psutil.cpu_freq(); self.cpu_freq.setText(f'Frequency: {frequency.current:.0f} MHz' if frequency else 'Frequency: unavailable')
        else:
            mhz=read_text('/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq'); self.cpu_freq.setText(f'Frequency: {float(mhz)/1000:.0f} MHz' if mhz else 'Frequency: unavailable')
        self.cores.setText('Per-core: ' + ('  '.join(f'C{i} {v:.0f}%' for i,v in enumerate(core)) if core else 'warming up…'))
        ram=ram_reading(); self.ram.set_value(ram[0]/ram[1]*100 if ram else None, f'{ram[0]:.0f} / {ram[1]:.0f} MiB' if ram else None)
        # GPU metrics are independent of CPU sampling and may temporarily fail.
        gpu,err=gpu_reading();
        if gpu:
            self.gpu_name.setText(gpu['name']); self.gpu_load.set_value(gpu['load']); self.gpu_temp.set_value(gpu['temp'],f"{gpu['temp']:.0f}°C"); self.vram.set_value(gpu['mem_used']/gpu['mem_total']*100 if gpu['mem_total'] else None,f"{gpu['mem_used']:.0f} / {gpu['mem_total']:.0f} MiB"); self.power.set_value(gpu['power'],f"{gpu['power']:.1f} W")
        else:
            self.gpu_name.setText('NVIDIA GPU: unavailable'); [g.set_value(None) for g in (self.gpu_load,self.gpu_temp,self.vram,self.power)]
        if self.graph_toggle.isChecked():
            # Keep the most recent 60 seconds, enough for a useful compact chart.
            samples = {'cpu_load': total, 'cpu_temp': temp, 'gpu_load': gpu['load'] if gpu else None, 'gpu_temp': gpu['temp'] if gpu else None}
            for key, value in samples.items():
                if value is not None: self.history[key].append(value)
                self.history[key] = self.history[key][-60:]
            self.cpu_usage_graph.set_values(self.history['cpu_load']); self.cpu_temp_graph.set_values(self.history['cpu_temp'])
            self.gpu_usage_graph.set_values(self.history['gpu_load']); self.gpu_temp_graph.set_values(self.history['gpu_temp'])
        if self.process_toggle.isChecked():
            rows = process_rows(); self.process_table.setRowCount(len(rows))
            for row, (pid, name, cpu, mem, rss) in enumerate(rows):
                values = (pid, name, f'{cpu:.1f}%', f'{mem:.1f}%', f'{rss / 1024:.0f} MiB')
                for column, value in enumerate(values): self.process_table.setItem(row, column, QTableWidgetItem(value))
        self.status.setText(f'Updated {time.strftime("%H:%M:%S")} · ' + ('GPU query OK' if gpu else 'GPU query unavailable; will retry'))

# QApplication owns the Qt event loop: it keeps the window alive and dispatches timers.
if __name__ == '__main__':
    app=QApplication([]); app.setApplicationName('Cute Vitals'); w=Window(); w.show(); app.exec()
