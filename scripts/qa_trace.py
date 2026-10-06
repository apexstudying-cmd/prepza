#!/usr/bin/env python3
"""Dependency-free verifier for Prepza's code-traced release QA registry."""
from __future__ import annotations
import argparse, json, subprocess
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "qa" / "release_manifest.json"

def read_text(path):
    p = ROOT / path
    if not p.exists():
        raise FileNotFoundError(path)
    return p.read_text(encoding="utf-8", errors="replace")

def check_layer(layer):
    errors = []
    try:
        content = read_text(layer["path"])
    except FileNotFoundError:
        return [f"missing file: {layer['path']}"]
    for anchor in layer.get("anchors", []):
        if anchor not in content:
            errors.append(f"{layer['path']}: missing anchor {anchor!r}")
    return errors

def test_target_exists(command):
    return any(part.endswith(".py") and (ROOT / part).exists() for part in command.split())

def git_head():
    try:
        return subprocess.check_output(["git","rev-parse","HEAD"], cwd=ROOT, text=True).strip()
    except Exception:
        return "unknown"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    failures, warnings = [], []
    print(f"QA trace registry v{data['version']}")
    print(f"Repository HEAD: {git_head()}")
    for feature in data["features"]:
        print(f"\n[{feature['id']}] {feature['name']}")
        layer_errors = []
        for layer in feature.get("layers", []):
            layer_errors.extend(check_layer(layer))
        for error in layer_errors:
            failures.append(f"{feature['id']}: {error}")
        commands = feature.get("required_test_commands", [])
        for command in commands:
            if not test_target_exists(command):
                failures.append(f"{feature['id']}: missing test target: {command}")
        if not commands:
            warnings.append(f"{feature['id']}: no executable release test command is registered")
        if layer_errors:
            print("  TRACE: RED")
        elif not commands:
            print("  TRACE: YELLOW")
        else:
            print("  TRACE: traced")
        if feature.get("notes"):
            print(f"  NOTE: {feature['notes']}")
    print("\nRelease QA trace summary")
    print(f"  features: {len(data['features'])}")
    print(f"  failures: {len(failures)}")
    print(f"  warnings: {len(warnings)}")
    for item in failures: print(f"  ERROR: {item}")
    for item in warnings: print(f"  WARNING: {item}")
    if failures or (args.strict and warnings):
        return 1
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
