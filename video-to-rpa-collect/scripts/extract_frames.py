# -*- coding: utf-8 -*-
"""
Extract key frames from a video using scene-change detection (OpenCV MSE).

Usage:
    python extract_frames.py <video_path> <output_dir> [--threshold 30] [--min-interval 1.0] [--frame-skip 5]

Outputs PNG files named like: frame_00_5s.png, frame_01_12s.png, ...
The timestamp in the filename helps the agent select the most relevant frames.
"""
import cv2
import os
import sys
import argparse
import numpy as np


def _imwrite_unicode(path: str, img) -> bool:
    """Write image to path with Unicode (CJK) support on Windows.

    cv2.imwrite can silently fail on paths with CJK characters on some
    Python/OpenCV builds on Windows (uses fopen which isn't UTF-8 aware).
    Workaround: cv2.imencode to a buffer, then write bytes via Python's
    open() which handles Unicode natively.
    """
    try:
        # First try direct imwrite (fast path, works on most systems)
        ok = cv2.imwrite(path, img, [cv2.IMWRITE_PNG_COMPRESSION, 6])
        if ok and os.path.exists(path) and os.path.getsize(path) > 0:
            return True
    except Exception:
        pass
    # Fallback: imencode + binary write
    try:
        ext = os.path.splitext(path)[1] or ".png"
        ok2, buf = cv2.imencode(ext, img, [cv2.IMWRITE_PNG_COMPRESSION, 6])
        if ok2:
            with open(path, "wb") as f:
                f.write(buf.tobytes())
            return os.path.exists(path) and os.path.getsize(path) > 0
    except Exception as e:
        print(f"  WARN imwrite failed: {e}", file=sys.stderr)
    return False


def extract_frames(video_path, output_dir, threshold=30.0, min_interval=1.0, frame_skip=5):
    os.makedirs(output_dir, exist_ok=True)

    # Use a short ASCII temp path if the input/output path contains CJK characters
    # that might trip up cv2.VideoCapture. This is a belt-and-suspenders fix.
    use_native = True
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        # Fallback: try to read via numpy/ffmpeg if path is unicode? Actually
        # VideoCapture on Windows does support unicode via the wchar overload in
        # modern OpenCV builds; if it still fails we give up clearly.
        print(f"ERROR: Cannot open video: {video_path}", file=sys.stderr)
        sys.exit(1)

    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps if fps > 0 else 0

    min_interval_frames = int(fps * min_interval)
    last_saved_frame = -min_interval_frames
    saved_count = 0
    prev_frame = None

    print(f"Video: {total_frames} frames, {fps:.1f} fps, {duration:.1f}s")
    print(f"Scene detection: threshold={threshold}, min_interval={min_interval}s, frame_skip={frame_skip}")
    print("---")

    frame_idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx % frame_skip != 0:
            frame_idx += 1
            continue

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)

        if prev_frame is not None:
            diff = cv2.absdiff(gray, prev_frame)
            mse = (diff ** 2).mean()

            if mse > threshold and (frame_idx - last_saved_frame) >= min_interval_frames:
                timestamp = frame_idx / fps
                fname = f"frame_{saved_count:02d}_{timestamp:.0f}s.png"
                fpath = os.path.join(output_dir, fname)
                ok = _imwrite_unicode(fpath, frame)
                if ok:
                    print(f"[{saved_count}] t={timestamp:.1f}s  mse={mse:.1f}  -> {fname}")
                    saved_count += 1
                    last_saved_frame = frame_idx
                else:
                    print(f"[{saved_count}] t={timestamp:.1f}s  WARN failed to write {fname}", file=sys.stderr)

        prev_frame = gray
        frame_idx += 1

    # Always save the last frame
    if total_frames > 0:
        timestamp = duration
        fname = f"frame_{saved_count:02d}_{timestamp:.0f}s_end.png"
        fpath = os.path.join(output_dir, fname)
        cap.set(cv2.CAP_PROP_POS_FRAMES, total_frames - 1)
        ret, last_frame = cap.read()
        if ret:
            ok = _imwrite_unicode(fpath, last_frame)
            if ok:
                print(f"[{saved_count}] t={timestamp:.1f}s  -> {fname} (last frame)")
                saved_count += 1
            else:
                print(f"[{saved_count}] t={timestamp:.1f}s  WARN failed to write {fname}", file=sys.stderr)

    cap.release()
    print(f"\nTotal key frames extracted: {saved_count}")
    print(f"Output directory: {output_dir}")
    return saved_count


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Extract key frames from video via scene detection')
    parser.add_argument('video_path', help='Path to the input video file')
    parser.add_argument('output_dir', help='Directory to save extracted frames')
    parser.add_argument('--threshold', type=float, default=30.0, help='MSE threshold for scene change (default: 30)')
    parser.add_argument('--min-interval', type=float, default=1.0, help='Minimum seconds between frames (default: 1.0)')
    parser.add_argument('--frame-skip', type=int, default=5, help='Process every Nth frame (default: 5)')
    args = parser.parse_args()

    extract_frames(args.video_path, args.output_dir, args.threshold, args.min_interval, args.frame_skip)
