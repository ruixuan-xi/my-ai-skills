# -*- coding: utf-8 -*-
"""
Extract audio track from a video file as 16kHz mono WAV for ASR.

Usage:
    python extract_audio.py <video_path> [--output <audio.wav>] [--rate 16000]

Uses imageio-ffmpeg (bundled portable ffmpeg).
Python packages: imageio-ffmpeg
"""
import os
import sys
import argparse
import subprocess

try:
    import imageio_ffmpeg
    FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
except ImportError:
    print("ERROR: imageio-ffmpeg not installed. Run:")
    print("  pip install imageio-ffmpeg")
    sys.exit(1)


def extract_audio(video_path: str, output_path: str, sample_rate: int = 16000) -> str:
    """Extract audio from video to mono 16kHz WAV."""
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")

    cmd = [
        FFMPEG,
        "-i", video_path,
        "-vn",                     # no video
        "-acodec", "pcm_s16le",    # 16-bit PCM
        "-ar", str(sample_rate),   # sample rate
        "-ac", "1",                # mono
        output_path,
        "-y",                      # overwrite
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ffmpeg stderr:\n{result.stderr}")
        raise RuntimeError(f"ffmpeg exited with code {result.returncode}")

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"Audio extracted: {output_path} ({size_mb:.1f} MB)")
    return output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract audio from video")
    parser.add_argument("video", help="Path to input video file")
    parser.add_argument("--output", "-o", help="Output WAV path", default=None)
    parser.add_argument("--rate", "-r", type=int, default=16000, help="Sample rate (default: 16000)")
    args = parser.parse_args()

    if args.output is None:
        base = os.path.splitext(os.path.basename(args.video))[0]
        args.output = os.path.join(
            os.path.dirname(args.video) or ".",
            f"{base}_audio.wav"
        )

    extract_audio(args.video, args.output, args.rate)
