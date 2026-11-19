#!/usr/bin/env python3
"""Low-overhead, read-only OWGW memory monitor. Python 3.8+, standard library only.

Run on the OWGW Docker host. Reports go in load-simulator-dignotic-report/.
Existing reports are preserved; each execution creates uniquely named files.
Outputs a CSV of host/process/cgroup readings and JSONL containing complete
diagnostic API responses. No APs are created.
"""

import argparse
import csv
import datetime as dt
import json
import os
from pathlib import Path
import signal
import ssl
import subprocess
import sys
import time
from urllib import error as urlerror
from urllib import request as urlrequest

MIB = 1024.0 * 1024.0
GIB = 1024.0 * MIB
STOP = False


def on_signal(_signum, _frame):
    global STOP
    STOP = True


def utc_now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def read_kv(path):
    result = {}
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            tokens = value.split()
            if tokens:
                try:
                    result[key] = int(tokens[0])
                except ValueError:
                    pass
    return result


def host_memory():
    m = read_kv("/proc/meminfo")
    total = m.get("MemTotal", 0)
    avail = m.get("MemAvailable", m.get("MemFree", 0))
    return {
        "host_ram_pct": round((total - avail) * 100.0 / total, 2) if total else None,
        "host_available_gib": round(avail / 1024.0 / 1024.0, 3),
        "host_swap_free_gib": round(m.get("SwapFree", 0) / 1024.0 / 1024.0, 3),
    }


def cpu_times():
    with open("/proc/stat", "r", encoding="ascii") as handle:
        parts = handle.readline().split()
    values = [int(x) for x in parts[1:]]
    idle = values[3] + (values[4] if len(values) > 4 else 0)
    return sum(values), idle


def process_cpu_ticks(pid):
    with open("/proc/{}/stat".format(pid), "r", encoding="ascii") as handle:
        stat = handle.read().rsplit(")", 1)[1].split()
    # Fields 14/15 (utime/stime) after removing "pid (comm)".
    return int(stat[11]) + int(stat[12])


def process_status(pid):
    raw = read_kv("/proc/{}/status".format(pid))
    result = {}
    for source, dest in (
        ("VmRSS", "rss_mib"),
        ("RssAnon", "rss_anon_mib"),
        ("RssFile", "rss_file_mib"),
        ("RssShmem", "rss_shmem_mib"),
        ("VmData", "vm_data_mib"),
        ("VmSwap", "vm_swap_mib"),
        ("VmHWM", "rss_peak_mib"),
        ("VmSize", "vm_size_mib"),
    ):
        result[dest] = round(raw[source] / 1024.0, 2) if source in raw else None
    result["threads"] = raw.get("Threads")
    try:
        with open("/proc/{}/comm".format(pid), "r", encoding="utf-8") as handle:
            result["process_name"] = handle.read().strip()
    except OSError:
        result["process_name"] = ""
    return result


def process_io(pid):
    try:
        values = read_kv("/proc/{}/io".format(pid))
    except OSError:
        return {}
    return {
        "proc_read_mib": round(values.get("read_bytes", 0) / MIB, 2),
        "proc_write_mib": round(values.get("write_bytes", 0) / MIB, 2),
    }


def cgroup_memory(pid):
    """Read cgroup v2, or legacy memory cgroup, without running docker stats."""
    try:
        with open("/proc/{}/cgroup".format(pid), "r", encoding="ascii") as handle:
            entries = [line.strip().split(":", 2) for line in handle]
        cg2 = next((part[2] for part in entries if len(part) == 3 and part[0] == "0"), None)
        if cg2 is not None:
            base = Path("/sys/fs/cgroup") / cg2.lstrip("/")
            current = int((base / "memory.current").read_text().strip()) / MIB
        else:
            mem = next((part[2] for part in entries if len(part) == 3
                        and "memory" in part[1].split(",")), None)
            if mem is None:
                return {}
            base = Path("/sys/fs/cgroup/memory") / mem.lstrip("/")
            current = int((base / "memory.usage_in_bytes").read_text().strip()) / MIB
        values = {}
        with open(base / "memory.stat", "r", encoding="ascii") as handle:
            for line in handle:
                parts = line.split()
                if len(parts) == 2:
                    values[parts[0]] = int(parts[1])
        result = {"cgroup_memory_mib": round(current, 2)}
        for name in ("anon", "file", "sock", "slab", "kernel", "shmem",
                     "rss", "cache", "total_rss"):
            if name in values:
                result["cgroup_{}_mib".format(name)] = round(values[name] / MIB, 2)
        return result
    except (OSError, ValueError):
        return {}


def psi_memory():
    result = {}
    try:
        with open("/proc/pressure/memory", "r", encoding="ascii") as handle:
            for line in handle:
                parts = line.split()
                if not parts or parts[0] not in ("some", "full"):
                    continue
                for item in parts[1:]:
                    if item.startswith("avg10="):
                        result["psi_memory_{}_avg10".format(parts[0])] = float(item[6:])
    except (OSError, ValueError):
        pass
    return result


def count_fds(pid):
    with os.scandir("/proc/{}/fd".format(pid)) as entries:
        return sum(1 for _ in entries)


def count_ap_tcp(pid, port):
    count = 0
    wanted = "{:04X}".format(port)
    for suffix in ("tcp", "tcp6"):
        try:
            with open("/proc/{}/net/{}".format(pid, suffix), "r", encoding="ascii") as handle:
                next(handle, None)
                for line in handle:
                    parts = line.split()
                    if (len(parts) > 3 and parts[3] == "01"
                            and parts[1].rsplit(":", 1)[-1].upper() == wanted):
                        count += 1
        except OSError:
            pass
    return count


def inspect_container(name):
    try:
        call = subprocess.run(
            ["docker", "inspect", name],
            capture_output=True, text=True, timeout=3, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("docker inspect unavailable: {}".format(type(exc).__name__))
    if call.returncode:
        raise RuntimeError("docker inspect exited {}".format(call.returncode))
    info = json.loads(call.stdout)[0]
    state = info.get("State") or {}
    networks = (info.get("NetworkSettings") or {}).get("Networks") or {}
    ips = [v.get("IPAddress", "") for v in networks.values() if isinstance(v, dict)]
    return {
        "pid": int(state.get("Pid", 0) or 0),
        "status": str(state.get("Status", "unknown")),
        "started_at": str(state.get("StartedAt", "")),
        "restart_count": int(info.get("RestartCount", 0) or 0),
        "container_ip": next((ip for ip in ips if ip), ""),
    }


def read_token(args):
    if args.token_file:
        return Path(args.token_file).read_text(encoding="utf-8").strip()
    return os.environ.get("OWGW_MONITOR_TOKEN", "").strip()


def diagnostics_url(args, state):
    if args.diag_url:
        return args.diag_url.replace("{container_ip}", state.get("container_ip", ""))
    if not args.diag_path:
        return ""
    if not args.diag_path.startswith("/"):
        raise ValueError("--diag-path must start with /")
    ip = state.get("container_ip", "")
    if not ip:
        raise ValueError("Docker container IP unavailable")
    return "https://{}:{}{}".format(ip, args.diag_port, args.diag_path)


def get_diagnostics(url, token, args):
    if not url:
        return None, "disabled", None
    if "{container_ip}" in url or "://" not in url:
        return None, "invalid_diagnostic_url", None
    if token and url.startswith("http://"):
        return None, "refusing_bearer_token_over_http", None
    headers = {"Accept": "application/json", "User-Agent": "OWGW-memory-monitor/1.0"}
    if token:
        headers["Authorization"] = "Bearer " + token
    context = None
    if url.startswith("https://"):
        context = (ssl._create_unverified_context() if args.diag_insecure else
                   ssl.create_default_context(cafile=args.diag_ca))
    req = urlrequest.Request(url, headers=headers, method="GET")
    started = time.monotonic()
    try:
        with urlrequest.urlopen(req, timeout=args.http_timeout, context=context) as response:
            raw = response.read(args.max_json_bytes + 1)
            if len(raw) > args.max_json_bytes:
                return None, "response_too_large", None
            data = json.loads(raw.decode("utf-8"))
        return data, "ok", round((time.monotonic() - started) * 1000, 1)
    except urlerror.HTTPError as exc:
        return None, "HTTP_{}".format(exc.code), None
    except (urlerror.URLError, ValueError, OSError, TimeoutError, json.JSONDecodeError) as exc:
        return None, type(exc).__name__, None


def json_path(obj, path):
    if not path:
        return None
    for key in path.split("."):
        if not isinstance(obj, dict) or key not in obj:
            return None
        obj = obj[key]
    return obj if isinstance(obj, (int, float, str)) else None


def output_fields():
    return [
        "utc", "sample", "target_devices", "container_status", "container_pid",
        "container_started_at", "restart_count", "host_cpu_pct", "host_ram_pct",
        "host_available_gib", "host_swap_free_gib", "psi_memory_some_avg10",
        "psi_memory_full_avg10", "owgw_cpu_pct", "process_name", "rss_mib",
        "rss_anon_mib", "rss_file_mib", "rss_shmem_mib", "rss_peak_mib",
        "vm_data_mib", "vm_size_mib", "vm_swap_mib", "threads",
        "proc_read_mib", "proc_write_mib", "cgroup_memory_mib", "cgroup_anon_mib",
        "cgroup_file_mib", "cgroup_sock_mib", "cgroup_slab_mib",
        "cgroup_kernel_mib", "cgroup_shmem_mib", "cgroup_rss_mib",
        "cgroup_cache_mib", "cgroup_total_rss_mib", "fds", "fd_age_s",
        "tcp_estab_15002", "tcp_age_s", "connected_aps", "diagnostics_status",
        "diagnostics_latency_ms", "diagnostics_bytes"
    ]


def parser():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--container", default="openwifi_owgw_1")
    ap.add_argument("--devices", type=int, default=None,
                    help="Optional target label only; does not start or count APs")
    ap.add_argument("--minutes", type=float, default=45,
                    help="Monitoring duration; 0 means until interrupted (default 45)")
    ap.add_argument("--interval", type=float, default=15,
                    help="Seconds between snapshots (default 15)")
    ap.add_argument("--inspect-every", type=float, default=60)
    ap.add_argument("--fd-every", type=float, default=60)
    ap.add_argument("--tcp-every", type=float, default=60)
    ap.add_argument("--ap-port", type=int, default=15002)
    ap.add_argument("--diag-path",
                    default="/api/v1/system?command=resources&diagnostics=memory",
                    help="Internal memory diagnostics API path (default: resources/memory)")
    ap.add_argument("--diag-url", default="",
                    help="Alternative full URL; use {container_ip} for current Docker IP")
    ap.add_argument("--diag-port", type=int, default=17002)
    ap.add_argument("--diag-insecure", action="store_true",
                    help="Disable HTTPS certificate verification ONLY on trusted local Docker bridge")
    ap.add_argument("--diag-ca", default=None, help="Trusted CA PEM for HTTPS")
    ap.add_argument("--token-file", default=None,
                    help="File containing an API bearer token (never printed)")
    ap.add_argument("--ap-field", default="",
                    help="Dotted JSON field for actual connected AP count")
    ap.add_argument("--http-timeout", type=float, default=2)
    ap.add_argument("--max-json-bytes", type=int, default=1024 * 1024)
    ap.add_argument("--warn-rss-gib", type=float, default=6)
    ap.add_argument("--warn-available-gib", type=float, default=2)
    ap.add_argument("--output-dir", default="load-simulator-dignotic-report",
                    help="Shared report directory; existing reports are never removed")
    return ap


def main():
    args = parser().parse_args()
    if args.interval < 5 or args.minutes < 0:
        sys.exit("Use --interval >= 5 and --minutes >= 0")
    if args.diag_insecure and args.diag_ca:
        sys.exit("Specify either --diag-ca or --diag-insecure, not both")
    token = read_token(args)
    # Never remove, clear, or replace the shared report directory or old files.
    directory = Path(args.output_dir)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    # Microseconds plus PID avoid collisions across repeated/concurrent runs.
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run_id = "{}-{}".format(stamp, os.getpid())
    csv_path = directory / ("metrics-" + run_id + ".csv")
    json_pathname = directory / ("diagnostics-" + run_id + ".jsonl")
    print("Writing:", csv_path, "and", json_pathname, flush=True)
    print("--devices is a target label, not a simulation command.", flush=True)
    print("Diagnostics:", "enabled" if args.diag_path or args.diag_url else
          "disabled (specify --diag-path with the exact internal route)", flush=True)
    print("Warning thresholds only ALERT; this monitor never stops OWLS/OWGW.", flush=True)

    state = {}
    last_inspect = -1e30
    last_fd = -1e30
    last_tcp = -1e30
    last_warn = -1e30
    previous_host = None
    previous_proc = None
    fds = None
    estab = None
    pid_previous = None
    clock_ticks = os.sysconf("SC_CLK_TCK")
    started = time.monotonic()
    next_sample = started
    deadline = started + args.minutes * 60 if args.minutes else float("inf")
    fields = output_fields()

    with open(csv_path, "x", newline="", encoding="utf-8", buffering=1) as csv_file, \
            open(json_pathname, "x", encoding="utf-8", buffering=1) as json_file:
        writer = csv.DictWriter(csv_file, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        sample = 0
        while not STOP and time.monotonic() < deadline:
            tick = time.monotonic()
            sample += 1
            row = {"utc": utc_now(), "sample": sample,
                   "target_devices": args.devices}
            errors = []
            if tick - last_inspect >= args.inspect_every or not state:
                last_inspect = tick
                try:
                    state = inspect_container(args.container)
                except (RuntimeError, ValueError, KeyError) as exc:
                    errors.append("inspect: {}".format(exc))
            pid = state.get("pid", 0)
            row.update({
                "container_status": state.get("status", "unknown"),
                "container_pid": pid or None,
                "container_started_at": state.get("started_at"),
                "restart_count": state.get("restart_count"),
            })
            if pid != pid_previous:
                previous_proc = None
                last_fd = last_tcp = -1e30
                fds = estab = None
                pid_previous = pid

            row.update(host_memory())
            row.update(psi_memory())
            try:
                current_host = cpu_times()
                if previous_host:
                    total_delta = current_host[0] - previous_host[0]
                    idle_delta = current_host[1] - previous_host[1]
                    if total_delta > 0:
                        row["host_cpu_pct"] = round(
                            100 * (total_delta - idle_delta) / total_delta, 2)
                previous_host = current_host
            except (OSError, ValueError):
                pass

            if pid:
                try:
                    row.update(process_status(pid))
                    row.update(process_io(pid))
                    row.update(cgroup_memory(pid))
                    current_proc = (process_cpu_ticks(pid), time.monotonic())
                    if previous_proc and current_proc[0] >= previous_proc[0]:
                        elapsed = current_proc[1] - previous_proc[1]
                        if elapsed > 0:
                            row["owgw_cpu_pct"] = round(
                                100 * (current_proc[0] - previous_proc[0]) /
                                clock_ticks / elapsed, 2)
                    previous_proc = current_proc
                except (OSError, ValueError, IndexError) as exc:
                    errors.append("process: {}".format(type(exc).__name__))
                    previous_proc = None
                if tick - last_fd >= args.fd_every:
                    last_fd = tick
                    try:
                        fds = count_fds(pid)
                    except OSError:
                        fds = None
                if tick - last_tcp >= args.tcp_every:
                    last_tcp = tick
                    try:
                        estab = count_ap_tcp(pid, args.ap_port)
                    except OSError:
                        estab = None
            row["fds"] = fds
            row["fd_age_s"] = round(tick - last_fd, 1) if last_fd > 0 else None
            row["tcp_estab_15002"] = estab
            row["tcp_age_s"] = round(tick - last_tcp, 1) if last_tcp > 0 else None

            diagnostics = None
            diag_status = "disabled"
            try:
                url = diagnostics_url(args, state)
                if url:
                    diagnostics, diag_status, latency = get_diagnostics(url, token, args)
                    row["diagnostics_latency_ms"] = latency
                    row["connected_aps"] = json_path(diagnostics, args.ap_field)
                    if diagnostics is not None:
                        row["diagnostics_bytes"] = len(
                            json.dumps(diagnostics, separators=(",", ":")).encode("utf-8"))
            except (ValueError, OSError) as exc:
                diag_status = "config_error:{}".format(type(exc).__name__)
            row["diagnostics_status"] = diag_status

            writer.writerow(row)
            record = {"utc": row["utc"], "sample": sample,
                      "metrics": row, "diagnostics": diagnostics}
            if errors:
                record["collection_errors"] = errors
            json_file.write(json.dumps(record, separators=(",", ":")) + "\n")

            host_ram = row.get("host_ram_pct")
            anon = row.get("rss_anon_mib")
            rss = row.get("rss_mib")
            cpu = row.get("owgw_cpu_pct")
            available = row.get("host_available_gib")
            def fmt(x, suffix=""):
                return ("-" if x is None else str(x) + suffix)
            print("{} host={} avail={}GiB OWGW_RSS={}MiB anon={}MiB "
                  "cpu={}% fd={} estab={} APs={} diag={}".format(
                      row["utc"], fmt(host_ram, "%"), fmt(available),
                      fmt(rss), fmt(anon), fmt(cpu), fmt(fds), fmt(estab),
                      fmt(row.get("connected_aps")), diag_status),
                  flush=True)
            if (tick - last_warn >= 60 and (
                    (rss is not None and rss >= args.warn_rss_gib * 1024) or
                    (available is not None and available <= args.warn_available_gib))):
                last_warn = tick
                print("WARNING: memory threshold reached; stop OWLS and "
                      "investigate OWGW before the host runs out of RAM.", file=sys.stderr,
                      flush=True)

            next_sample += args.interval
            remaining = next_sample - time.monotonic()
            if remaining <= 0:
                next_sample = time.monotonic()
            elif not STOP:
                time.sleep(remaining)
    print("Done. CSV:", csv_path, "JSONL:", json_pathname)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)
    try:
        main()
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
