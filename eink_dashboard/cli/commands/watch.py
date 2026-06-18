from __future__ import annotations

import atexit
import os
import signal
import sys
import time
from datetime import datetime
from typing import Optional

import click
import requests
from rich.live import Live
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table

from eink_dashboard.utils.console import console, safe_print


DEFAULT_PID_FILE = os.path.expanduser("~/.eink/watch.pid")
DEFAULT_LOG_FILE = os.path.expanduser("~/.eink/watch.log")


def _get_pid_file(device_url: str) -> str:
    import hashlib
    url_hash = hashlib.md5(device_url.encode()).hexdigest()[:8]
    return os.path.expanduser(f"~/.eink/watch_{url_hash}.pid")


def _get_log_file(device_url: str) -> str:
    import hashlib
    url_hash = hashlib.md5(device_url.encode()).hexdigest()[:8]
    return os.path.expanduser(f"~/.eink/watch_{url_hash}.log")


def _daemonize(log_file: str, pid_file: str) -> None:
    try:
        pid = os.fork()
        if pid > 0:
            sys.exit(0)
    except OSError as e:
        safe_print(f"[error]Fork #1 failed: {e}[/error]")
        sys.exit(1)

    os.chdir("/")
    os.setsid()
    os.umask(0)

    try:
        pid = os.fork()
        if pid > 0:
            sys.exit(0)
    except OSError as e:
        safe_print(f"[error]Fork #2 failed: {e}[/error]")
        sys.exit(1)

    sys.stdout.flush()
    sys.stderr.flush()

    log_dir = os.path.dirname(log_file)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    with open("/dev/null", "r") as devnull:
        os.dup2(devnull.fileno(), sys.stdin.fileno())

    with open(log_file, "a+") as log:
        os.dup2(log.fileno(), sys.stdout.fileno())
        os.dup2(log.fileno(), sys.stderr.fileno())

    pid = str(os.getpid())
    pid_dir = os.path.dirname(pid_file)
    if pid_dir:
        os.makedirs(pid_dir, exist_ok=True)

    with open(pid_file, "w+") as f:
        f.write(pid)

    atexit.register(lambda: os.remove(pid_file) if os.path.exists(pid_file) else None)

    def handler(signum, frame):
        if os.path.exists(pid_file):
            os.remove(pid_file)
        sys.exit(0)

    signal.signal(signal.SIGTERM, handler)
    signal.signal(signal.SIGINT, handler)


def _is_running(pid_file: str) -> Optional[int]:
    if not os.path.exists(pid_file):
        return None

    try:
        with open(pid_file, "r") as f:
            pid = int(f.read().strip())
    except (ValueError, IOError):
        os.remove(pid_file)
        return None

    try:
        os.kill(pid, 0)
        return pid
    except OSError:
        os.remove(pid_file)
        return None


def _fetch_metrics(device_url: str) -> dict:
    try:
        resp = requests.get(f"{device_url}/api/metrics", timeout=5)
        if resp.ok:
            data = resp.json()
            return data.get("metrics", {})
    except requests.RequestException:
        pass
    return {}


def _make_layout(device_url: str, extra_metrics: list, metrics: dict) -> Layout:
    layout = Layout()

    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="body", ratio=1),
    )

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    header_text = f"[bold cyan]E-Ink Dashboard Watch[/bold cyan]  |  Device: {device_url}  |  {now}"
    layout["header"].update(Panel(header_text, style="cyan"))

    body_layout = Layout()
    body_layout.split_row(
        Layout(name="left"),
        Layout(name="right"),
    )

    time_table = Table(show_header=False, expand=True)
    time_table.add_column("Item", style="cyan")
    time_table.add_column("Value", style="white")
    time_table.add_row("Local Time", now)

    cpu_temp = metrics.get("cpu_temp", "N/A")
    if cpu_temp != "N/A":
        temp_str = f"{cpu_temp:.1f}C"
        if isinstance(cpu_temp, (int, float)) and cpu_temp > 70:
            temp_str = f"[red]{temp_str} WARN[/red]"
        time_table.add_row("CPU Temperature", temp_str)

    body_layout["left"].update(Panel(time_table, title="System Info", border_style="blue"))

    metric_table = Table(expand=True)
    metric_table.add_column("Metric", style="cyan")
    metric_table.add_column("Value", style="green")

    all_keys = list(metrics.keys())
    for key in extra_metrics:
        if key not in all_keys:
            all_keys.append(key)

    for key in sorted(all_keys):
        if key == "cpu_temp":
            continue
        value = metrics.get(key, "N/A")
        if isinstance(value, float):
            metric_table.add_row(key, f"{value:.2f}")
        else:
            metric_table.add_row(key, str(value))

    if not all_keys:
        metric_table.add_row("(no metrics)", "...")

    body_layout["right"].update(Panel(metric_table, title="Custom Metrics", border_style="green"))

    layout["body"].update(body_layout)

    return layout


def _run_watch_foreground(device_url: str, interval: int, extra_metrics: list) -> None:
    safe_print(f"[info]Watching device at {device_url}[/info]")
    safe_print(f"[muted]Refresh every {interval}s. Press Ctrl+C to stop.[/muted]\n")

    try:
        with Live(_make_layout(device_url, extra_metrics, {}), refresh_per_second=4) as live:
            while True:
                metrics = _fetch_metrics(device_url)
                live.update(_make_layout(device_url, extra_metrics, metrics))
                time.sleep(interval)
    except KeyboardInterrupt:
        safe_print("\n[warning]Stopped watching.[/warning]")


def _run_watch_daemon(device_url: str, interval: int, extra_metrics: list, log_file: str) -> None:
    print(f"Starting watch daemon for {device_url}...")
    print(f"Log file: {log_file}")

    while True:
        try:
            metrics = _fetch_metrics(device_url)
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cpu_temp = metrics.get("cpu_temp", "N/A")
            print(f"[{now}] CPU: {cpu_temp}, Metrics: {len(metrics)} keys")
            sys.stdout.flush()
        except Exception as e:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{now}] Error: {e}")
            sys.stdout.flush()

        time.sleep(interval)


@click.command()
@click.option("--interval", "-i", type=int, default=5, help="Refresh interval in seconds")
@click.option("--metric", "-m", multiple=True, help="Additional metric keys to display")
@click.option("--daemon", "-D", is_flag=True, help="Run as daemon in background")
@click.option("--start", is_flag=True, help="Start watch daemon")
@click.option("--stop", is_flag=True, help="Stop watch daemon")
@click.option("--restart", is_flag=True, help="Restart watch daemon")
@click.option("--status", is_flag=True, help="Check daemon status")
@click.option("--nohup", is_flag=True, help="Run with nohup (detach from terminal)")
@click.option("--log-file", help="Log file path for daemon mode")
@click.option("--pid-file", help="PID file path for daemon mode")
@click.pass_context
def watch(
    ctx: click.Context,
    interval: int,
    metric: tuple,
    daemon: bool,
    start: bool,
    stop: bool,
    restart: bool,
    status: bool,
    nohup: bool,
    log_file: Optional[str],
    pid_file: Optional[str],
) -> None:
    """Watch device metrics in real-time.

    Supports foreground mode (default) and daemon/background mode.
    Use --start/--stop/--restart/--status to manage the daemon.
    """
    device_url = ctx.obj["device_url"]
    extra_metrics = list(metric)

    actual_pid_file = pid_file or _get_pid_file(device_url)
    actual_log_file = log_file or _get_log_file(device_url)

    if stop:
        _cmd_stop(actual_pid_file)
        return

    if status:
        _cmd_status(actual_pid_file, device_url)
        return

    if start or restart or daemon or nohup:
        if restart:
            _cmd_stop(actual_pid_file)
            time.sleep(1)

        running_pid = _is_running(actual_pid_file)
        if running_pid:
            safe_print(f"[warning]Watch daemon already running (PID {running_pid})[/warning]")
            return

        _cmd_start(device_url, interval, extra_metrics, actual_pid_file, actual_log_file, nohup)
        return

    _run_watch_foreground(device_url, interval, extra_metrics)


def _cmd_start(
    device_url: str,
    interval: int,
    extra_metrics: list,
    pid_file: str,
    log_file: str,
    use_nohup: bool,
) -> None:
    os.makedirs(os.path.dirname(pid_file), exist_ok=True)
    os.makedirs(os.path.dirname(log_file), exist_ok=True)

    if use_nohup and sys.platform != "win32":
        import subprocess

        cmd = [
            sys.executable,
            "-m",
            "eink_dashboard.cli.main",
            "--device-url",
            device_url,
            "dashboard",
            "watch",
            "--interval",
            str(interval),
            "--daemon",
        ]
        for m in extra_metrics:
            cmd.extend(["--metric", m])

        log_f = open(log_file, "a+")
        null_f = open(os.devnull, "r")

        subprocess.Popen(
            cmd,
            stdin=null_f,
            stdout=log_f,
            stderr=log_f,
            start_new_session=True,
        )

        time.sleep(1)
        running_pid = _is_running(pid_file)
        if running_pid:
            safe_print(f"[success]Watch daemon started (PID {running_pid})[/success]")
            safe_print(f"  Log file: {log_file}")
        else:
            safe_print(f"[warning]Watch daemon may have failed to start[/warning]")
            safe_print(f"  Check log file: {log_file}")
        return

    try:
        _daemonize(log_file, pid_file)
    except Exception as e:
        safe_print(f"[error]Failed to daemonize: {e}[/error]")
        if sys.platform == "win32":
            safe_print("[info]Windows does not support fork(). Using nohup mode instead.[/info]")
        raise SystemExit(1)

    _run_watch_daemon(device_url, interval, extra_metrics, log_file)


def _cmd_stop(pid_file: str) -> None:
    pid = _is_running(pid_file)
    if pid is None:
        safe_print("[warning]Watch daemon is not running[/warning]")
        return

    try:
        os.kill(pid, signal.SIGTERM)
        for _ in range(10):
            if not _is_running(pid_file):
                break
            time.sleep(0.2)

        if _is_running(pid_file):
            os.kill(pid, signal.SIGKILL)
            time.sleep(0.5)

        if os.path.exists(pid_file):
            os.remove(pid_file)

        safe_print(f"[success]Watch daemon stopped (PID {pid})[/success]")
    except OSError as e:
        safe_print(f"[error]Failed to stop daemon: {e}[/error]")
        if os.path.exists(pid_file):
            os.remove(pid_file)


def _cmd_status(pid_file: str, device_url: str) -> None:
    pid = _is_running(pid_file)
    if pid:
        safe_print(f"[success]Watch daemon is running (PID {pid})[/success]")
        safe_print(f"  Device: {device_url}")
        safe_print(f"  PID file: {pid_file}")
        safe_print(f"  Log file: {_get_log_file(device_url)}")
    else:
        safe_print("[warning]Watch daemon is not running[/warning]")
