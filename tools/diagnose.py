#!/usr/bin/env python3
"""
diagnose.py — collect a compact, shareable bug report from a connected device.

The offline patch can only be validated on a real phone. This script makes the
"install -> crash -> paste the log" loop painless: it (re)launches the game,
captures logcat for a while, filters out the noise and writes a short report
that tells us *where* it failed.

Usage::

    # with the phone connected (USB debugging on):
    python3 tools/diagnose.py                 # clear log, launch, capture 25 s
    python3 tools/diagnose.py --seconds 60
    python3 tools/diagnose.py --no-launch     # the game is already running
    python3 tools/diagnose.py --airplane      # (prompt) toggle airplane mode first

    # without a phone: analyse a logcat dump someone else exported
    python3 tools/diagnose.py --logcat logcat.txt

Only the Python standard library and ``adb`` are required.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import os
import re
import subprocess
import sys
import time
from typing import Dict, List, Optional, Sequence, Tuple

PACKAGE = "com.paeezanstudio.pesarkhande"

LOGCAT_RE = re.compile(
    r"^(?P<ts>\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})\s+(?P<pid>\d+)\s+(?P<tid>\d+)"
    r"\s+(?P<level>[VDIWEF])\s+(?P<tag>\S+)\s*:\s?(?P<msg>.*)$"
)

# logcat lines worth keeping
IMPORTANT = re.compile(
    r"(?ix)"
    r"(FATAL\s+EXCEPTION|Fatal\s+signal|SIGSEGV|SIGABRT|SIGBUS|backtrace|tombstone)"
    r"|(AndroidRuntime|\bE\s*Unity\b|NullReferenceException|MissingMethodException|"
    r"IndexOutOfRangeException|ArgumentNullException|InvalidOperationException)"
    r"|(couldn't\s+be\s+loaded|Unable\s+to\s+find|Scene\s*'|\bScene\b.*load|LoadScene)"
    r"|(il2cpp|libil2cpp|libunity)"
    r"|(pesarkhande|unity3d\.com|Unity.*[Ee]xception)"
)

CRASH_RE = re.compile(r"(?i)(FATAL EXCEPTION|Fatal signal|SIGSEGV|SIGABRT|SIGBUS)")
NRE_RE = re.compile(r"NullReferenceException")
SCENE_RE = re.compile(r"(?i)(scene '[^']+' couldn't be loaded|couldn't be loaded|Unable to find scene|scene with name|invalid scene name)")
NET_RE = re.compile(
    r"(?i)(pesarkhande[hw]\.(ir|com)|firebaseio|crashlytics|applovin|appsflyer|"
    r"googleapis|SocketException|UnknownHostException|ConnectException|ENETUNREACH|ECONNREFUSED|timeout)"
)


def run(cmd: Sequence[str], timeout: int = 60) -> Tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        raise SystemExit(f"required tool not found: {cmd[0]} (is it installed and on PATH?)")
    except subprocess.TimeoutExpired:
        return 124, ""
    return p.returncode, (p.stdout or "") + (p.stderr or "")


# ---------------------------------------------------------------------------
# capture
# ---------------------------------------------------------------------------

def adb_devices(serial: Optional[str]) -> str:
    rc, out = run(["adb", "devices"])
    devices = [l.split()[0] for l in out.splitlines()[1:] if l.strip().endswith("device")]
    if serial:
        if serial not in devices:
            raise SystemExit(f"device {serial} not found/authorised. `adb devices` says:\n{out}")
        return serial
    if not devices:
        raise SystemExit(
            "no device found. Enable USB debugging (Developer options), connect the phone and\n"
            "accept the RSA prompt, then run `adb devices` to check."
        )
    return devices[0]


def adb(serial: str, *args: str, timeout: int = 60) -> str:
    rc, out = run(["adb", "-s", serial, *args], timeout=timeout)
    return out.strip()


def device_info(serial: str) -> Dict[str, str]:
    props = {
        "model": "ro.product.model",
        "brand": "ro.product.brand",
        "android": "ro.build.version.release",
        "sdk": "ro.build.version.sdk",
        "abilist": "ro.product.cpu.abilist",
    }
    info = {}
    for key, prop in props.items():
        info[key] = adb(serial, "shell", "getprop", prop)
    rc, out = run(["adb", "-s", serial, "shell", "dumpsys", "package", PACKAGE])
    for field in ("versionCode", "versionName", "primaryCpuAbi", "codePath", "lastUpdateTime"):
        m = re.search(rf"\b{field}=(\S+)", out)
        if m:
            info[field] = m.group(1)
    if "versionCode" not in info:
        info["installed"] = "NO — package not found"
    return info


def capture(serial: str, seconds: float, launch: bool, clear: bool) -> List[str]:
    if clear:
        adb(serial, "logcat", "-c")
    if launch:
        # the launcher activity may differ between builds; monkey picks the right one
        adb(serial, "shell", "monkey", "-p", PACKAGE, "-c", "android.intent.category.LAUNCHER", "1")
    print(f"capturing {seconds:.0f}s of logcat ... (use the phone now: open the game, reproduce the problem)")
    time.sleep(seconds)
    return adb(serial, "logcat", "-d", "-v", "threadtime", timeout=120).splitlines()


# ---------------------------------------------------------------------------
# analysis
# ---------------------------------------------------------------------------

def parse(lines: Sequence[str]) -> List[dict]:
    rows = []
    for raw in lines:
        m = LOGCAT_RE.match(raw.rstrip("\n"))
        if not m:
            # older/simplified formats: "E/Unity( 1234): message" or "I Unity : message"
            m2 = re.match(r"^(?P<level>[VDIWEF])/(?P<tag>[^(]+?)\s*\(\s*(?P<pid>\d+)\):\s?(?P<msg>.*)$", raw)
            if m2:
                d = m2.groupdict()
                d.setdefault("ts", "")
                d.setdefault("tid", d["pid"])
                rows.append(d)
            continue
        rows.append(m.groupdict())
    return rows


def analyze(rows: Sequence[dict]) -> Tuple[Dict[str, object], List[int]]:
    """Classify the parsed rows. Returns the summary and the indices worth keeping
    (errors plus a context window after every crash/exception so stack traces survive)."""
    summary: Dict[str, object] = {}
    crashes, nres, scenes, nets = [], [], [], []
    keep: List[int] = []

    for i, r in enumerate(rows):
        msg = r.get("msg", "")
        is_crash = CRASH_RE.search(msg) is not None
        is_nre = NRE_RE.search(msg) is not None
        is_scene = SCENE_RE.search(msg) is not None and not is_nre
        is_net = NET_RE.search(msg) is not None
        interesting = is_crash or is_nre or is_scene or is_net or IMPORTANT.search(msg) or r.get("level") in ("E", "F")
        if not interesting:
            continue
        line = f"{r.get('ts','')} {r.get('pid','')} {r.get('level','')} {r.get('tag','')}: {msg}"
        if is_crash:
            crashes.append(line)
            keep.extend(range(i, min(i + 45, len(rows))))  # stack trace / backtrace context
        else:
            keep.append(i)
        if is_nre:
            nres.append(line)
        if is_scene:
            scenes.append(line)
        if is_net:
            nets.append(line)

    keep = sorted(set(keep))
    summary["lines_total"] = len(rows)
    summary["errors_kept"] = len(keep)
    summary["crashes"] = crashes[:12]
    summary["null_refs"] = nres[:12]
    summary["scene_problems"] = scenes[:12]
    summary["network"] = nets[:12]
    return summary, keep


def render(info: Dict[str, str], summary: Dict[str, object], rows: Sequence[dict], keep: Sequence[int], max_lines: int) -> str:
    out: List[str] = []
    w = out.append
    w(f"=== mafiaso-offline diagnose report — {_dt.datetime.now():%Y-%m-%d %H:%M:%S} ===")
    w("")
    w("[device]")
    if info:
        for k, v in info.items():
            w(f"  {k:12s} {v}")
    else:
        w("  (no device info — logcat dump analysed offline)")
    w("")
    w("[summary]")
    w(f"  logcat lines parsed     : {summary.get('lines_total', 0)}")
    w(f"  lines kept for report   : {summary.get('errors_kept', 0)}")
    w(f"  crashes (Java/native)   : {len(summary.get('crashes', []))}")
    w(f"  NullReferenceException  : {len(summary.get('null_refs', []))}")
    w(f"  scene-loading problems  : {len(summary.get('scene_problems', []))}")
    w(f"  network attempts/errors : {len(summary.get('network', []))}")
    w("")
    w("[verdict]")
    crashes = summary.get("crashes", [])
    nres = summary.get("null_refs", [])
    scenes = summary.get("scene_problems", [])
    nets = summary.get("network", [])
    if crashes:
        w("  CRASH — a Java/native crash was captured. See [crashes] for the top frames.")
    elif nres:
        w("  MANAGED EXCEPTION — Unity logged an exception (game may continue in a broken state).")
    elif scenes:
        w("  SCENE PROBLEM — a scene failed to load.")
    elif not info:
        w("  no crash pattern found in this dump.")
    else:
        w("  no crash pattern found — if the game still misbehaves, capture longer (--seconds 60) "
          "or describe what you saw on screen.")
    if nets and info:
        w(f"  NETWORK — {len(nets)} log line(s) mention game servers/SDKs; "
          "in airplane mode this shows what still tries to reach the internet.")
    w("")
    for title, key in (("crashes", "crashes"), ("null references", "null_refs"),
                       ("scene problems", "scene_problems"), ("network", "network")):
        items = summary.get(key, [])
        if items:
            w(f"[{title}]")
            for l in items:
                w("  " + l)
            w("")
    if keep:
        tail = list(keep)[-max_lines:]
        w(f"[filtered log] (last {len(tail)} of {len(keep)} kept lines)")
        for i in tail:
            r = rows[i]
            w(f"  {r.get('ts','')} {r.get('pid','')} {r.get('level','')} {r.get('tag','')}: {r.get('msg','')}")
        w("")
    w("[next step] send this file back (paste or attach). "
      "Addresses like `#00 pc 00000000014c1234  /libil2cpp.so` map to exact C# methods on our side.")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--serial", help="adb device serial (default: the only connected device)")
    ap.add_argument("--seconds", type=float, default=25.0, help="capture duration (default 25)")
    ap.add_argument("--no-launch", action="store_true", help="don't (re)launch the game")
    ap.add_argument("--no-clear", action="store_true", help="don't clear logcat first")
    ap.add_argument("--logcat", metavar="FILE", help="analyse an existing logcat dump instead of using adb")
    ap.add_argument("--out", help="report path (default diagnose-<timestamp>.txt)")
    ap.add_argument("--max-lines", type=int, default=120, help="max filtered log lines in the report")
    args = ap.parse_args(argv)

    if args.logcat:
        with open(args.logcat, encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
        info: Dict[str, str] = {}
    else:
        serial = adb_devices(args.serial)
        info = device_info(serial)
        lines = capture(serial, args.seconds, not args.no_launch, not args.no_clear)

    rows = parse(lines)
    summary, keep = analyze(rows)
    report = render(info, summary, rows, keep, args.max_lines)

    out = args.out or f"diagnose-{_dt.datetime.now():%Y%m%d-%H%M%S}.txt"
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(report)
    print(report)
    print(f"report written to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
