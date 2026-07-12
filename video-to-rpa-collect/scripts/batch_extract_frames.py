# -*- coding: utf-8 -*-
"""
Batch-extract key frames for a list of videos defined in a JSON config.

Reads config['items'] (each item must have `video_file`), creates a
subdirectory under <output_root>/<basename_without_ext>/video_frames/
for each video, runs scene-detection key frame extraction, and writes
back `frames_dir` + `frames` list into the item.

Usage:
    python batch_extract_frames.py <config.json> <output_root> [--threshold 30] [--min-interval 1.5] [--frame-skip 5]
"""
import sys
import os
import json
import argparse
import importlib.util

# Load extract_frames.py from sibling directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ext_path = os.path.join(SCRIPT_DIR, "extract_frames.py")
spec = importlib.util.spec_from_file_location("extract_frames", ext_path)
extract_frames_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(extract_frames_mod)
extract_frames = extract_frames_mod.extract_frames


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("config", help="Path to config JSON (items array)")
    parser.add_argument("output_root", help="Root dir where per-video subdirs will be created")
    parser.add_argument("--threshold", type=float, default=30.0)
    parser.add_argument("--min-interval", type=float, default=1.5)
    parser.add_argument("--frame-skip", type=int, default=5)
    parser.add_argument("--max-frames", type=int, default=15, help="Soft cap on number of key frames per video (drops frames above this by raising threshold)")
    args = parser.parse_args()

    with open(args.config, "r", encoding="utf-8") as f:
        config = json.load(f)

    items = config.get("items", [])
    os.makedirs(args.output_root, exist_ok=True)

    for i, it in enumerate(items):
        vpath = it.get("video_file")
        if not vpath or not os.path.isfile(vpath):
            print(f"[{i+1}/{len(items)}] SKIP (not found): {vpath}")
            continue
        base = os.path.splitext(os.path.basename(vpath))[0]
        # sanitize: replace path-unsafe chars
        safe = "".join(c if c not in r'\/:*?"<>|' else "_" for c in base)
        subdir = os.path.join(args.output_root, safe)
        frames_dir = os.path.join(subdir, "video_frames")
        os.makedirs(frames_dir, exist_ok=True)

        print(f"\n[{i+1}/{len(items)}] {base}")
        n = extract_frames(vpath, frames_dir,
                           threshold=args.threshold,
                           min_interval=args.min_interval,
                           frame_skip=args.frame_skip)

        # If too many frames, retry with higher threshold
        if args.max_frames and n > args.max_frames:
            print(f"  Too many frames ({n}>{args.max_frames}), retrying with higher threshold...")
            # clear old frames
            for old in os.listdir(frames_dir):
                if old.endswith(".png"):
                    os.remove(os.path.join(frames_dir, old))
            n = extract_frames(vpath, frames_dir,
                               threshold=60.0, min_interval=2.0, frame_skip=args.frame_skip)

        # collect frame list sorted by name
        frames = sorted([f for f in os.listdir(frames_dir) if f.endswith(".png")])
        it["frames_dir"] = frames_dir
        it["frames"] = frames
        it["frames_count"] = n
        it["work_dir"] = subdir

    # write back config
    with open(args.config, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    print(f"\nUpdated config: {args.config}")


if __name__ == "__main__":
    main()
