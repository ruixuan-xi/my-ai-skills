# -*- coding: utf-8 -*-
"""
Batch-extract audio + run ASR (影刀语音转文字) for a list of videos defined in a JSON config.

Reads config['items'] (each with `video_file`), creates <work_dir>/audio.wav and
<work_dir>/transcript.txt per video, then writes back `audio_path`, `transcript_path`,
and `transcript` text into the item.

If ffmpeg reports "Output file does not contain any stream" (no audio track),
the item is marked as `has_audio: false` and transcript is set to "" so downstream
steps can fall back to pure visual analysis.

If YINGDAO_AUTH_TOKEN / YINGDAO_WORKFLOW_ID env vars are missing, skips ASR but
still extracts audio (if present) so user can run ASR later.

Usage:
    python batch_asr.py <config.json>
"""
import sys
import os
import json
import argparse
import subprocess


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def _run(cmd, **kwargs):
    """Run subprocess and return (returncode, stdout, stderr)."""
    result = subprocess.run(cmd, capture_output=True, text=True, **kwargs)
    return result.returncode, result.stdout, result.stderr


def extract_audio_for_video(video_path: str, out_wav: str) -> tuple[bool, str]:
    """Extract 16kHz mono WAV. Returns (has_audio, error_msg)."""
    try:
        import imageio_ffmpeg
        FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        return False, "imageio-ffmpeg not installed"

    cmd = [
        FFMPEG, "-i", video_path,
        "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
        out_wav, "-y",
    ]
    rc, _out, err = _run(cmd)
    if rc != 0:
        # Detect "no audio stream" case
        if "does not contain any stream" in err or "Output file #0 does not contain any stream" in err:
            return False, "no_audio"
        return False, f"ffmpeg rc={rc}: {err[-300:]}"
    # verify file is non-empty
    if not os.path.exists(out_wav) or os.path.getsize(out_wav) < 1024:
        return False, "empty_audio"
    return True, ""


def transcribe_audio(audio_path: str, transcript_path: str) -> tuple[bool, str]:
    """Call asr_transcribe.py via subprocess. Returns (ok, transcript_or_error)."""
    asr_script = os.path.join(SCRIPT_DIR, "asr_transcribe.py")
    py = sys.executable
    rc, out, err = _run([py, asr_script, audio_path, "--output", transcript_path], timeout=300)
    if rc != 0:
        return False, (err or out)[-500:]
    # Read transcript back
    try:
        with open(transcript_path, "r", encoding="utf-8") as f:
            text = f.read().strip()
        return True, text
    except Exception as e:
        return False, f"read transcript failed: {e}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("config", help="Path to config JSON")
    parser.add_argument("--skip-asr", action="store_true",
                        help="Only extract audio, skip calling 影刀 ASR (useful for debug)")
    args = parser.parse_args()

    with open(args.config, "r", encoding="utf-8") as f:
        config = json.load(f)

    items = config.get("items", [])
    has_token = bool(os.environ.get("YINGDAO_AUTH_TOKEN")) and bool(os.environ.get("YINGDAO_WORKFLOW_ID"))

    if not has_token and not args.skip_asr:
        print("WARN: YINGDAO_AUTH_TOKEN / YINGDAO_WORKFLOW_ID 未设置，将只提取音频（不做 ASR）。")
        print("      设置环境变量后可重新运行此脚本完成转写。")

    ok_count = 0
    no_audio_count = 0
    fail_count = 0
    asr_count = 0

    for i, it in enumerate(items):
        vpath = it.get("video_file")
        work_dir = it.get("work_dir")
        if not vpath or not os.path.isfile(vpath):
            print(f"[{i+1}/{len(items)}] SKIP (video not found): {vpath}")
            continue
        if not work_dir:
            print(f"[{i+1}/{len(items)}] SKIP (no work_dir; run batch_extract_frames first): {vpath}")
            continue

        os.makedirs(work_dir, exist_ok=True)
        audio_path = os.path.join(work_dir, "audio.wav")
        transcript_path = os.path.join(work_dir, "transcript.txt")

        print(f"\n[{i+1}/{len(items)}] {os.path.basename(vpath)}")
        has_audio, err = extract_audio_for_video(vpath, audio_path)
        it["audio_path"] = audio_path if has_audio else None
        it["has_audio"] = has_audio

        if not has_audio:
            if err == "no_audio":
                print("  ⚠ 视频无音频轨道，跳过 ASR，后续将纯视觉分析")
                no_audio_count += 1
                it["transcript"] = ""
                it["transcript_path"] = None
            else:
                print(f"  ✗ 音频提取失败: {err}")
                fail_count += 1
                it["transcript"] = ""
                it["transcript_path"] = None
            continue

        print(f"  ✓ 音频已提取: {audio_path}")
        ok_count += 1

        if args.skip_asr or not has_token:
            it["transcript"] = ""
            it["transcript_path"] = None
            continue

        print(f"  调用影刀 ASR ...")
        ok, transcript_or_err = transcribe_audio(audio_path, transcript_path)
        if ok:
            it["transcript"] = transcript_or_err
            it["transcript_path"] = transcript_path
            print(f"  ✓ 转写完成: {len(transcript_or_err)} 字")
            asr_count += 1
        else:
            print(f"  ✗ ASR 失败: {transcript_or_err[:200]}")
            it["transcript"] = ""
            it["transcript_path"] = None
            fail_count += 1

    # write back
    with open(args.config, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    print(f"\n=== 汇总 ===")
    print(f"  成功提取音频: {ok_count}")
    print(f"  无音频轨道:   {no_audio_count}（将纯视觉分析）")
    print(f"  ASR 转写成功: {asr_count}")
    print(f"  失败:         {fail_count}")
    print(f"Config 已回写: {args.config}")


if __name__ == "__main__":
    main()
