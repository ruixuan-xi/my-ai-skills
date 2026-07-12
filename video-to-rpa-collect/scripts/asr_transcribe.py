# -*- coding: utf-8 -*-
"""
Transcribe audio to text via 影刀 AI Work OS speech recognition workflow.

Workflow:
  1. Upload audio file to 影刀 file upload API
  2. Call ASR workflow with uploaded file URL
  3. Extract and return transcribed text

Usage:
    python asr_transcribe.py <audio.wav> [--output transcript.txt]
"""
import os
import sys
import json
import argparse
import requests

# ========== 影刀 API 配置（从环境变量读取） ==========
UPLOAD_FILE_URL = "https://power-api.yingdao.com/oapi/power/v1/file/upload"

AUTH_TOKEN = os.environ.get("YINGDAO_AUTH_TOKEN", "")
WORKFLOW_ID = os.environ.get("YINGDAO_WORKFLOW_ID", "")

if not AUTH_TOKEN or not WORKFLOW_ID:
    print("ERROR: 请设置环境变量 YINGDAO_AUTH_TOKEN 和 YINGDAO_WORKFLOW_ID")
    sys.exit(1)

WORKFLOW_URL = f"https://power-api.yingdao.com/oapi/power/v1/rest/flow/{WORKFLOW_ID}/execute"

AUTH_HEADER = {"Authorization": f"Bearer {AUTH_TOKEN}"}
JSON_HEADER = {
    "Authorization": f"Bearer {AUTH_TOKEN}",
    "Content-Type": "application/json",
}


def upload_file(file_path: str) -> dict:
    """Upload a file to 影刀 and return the response JSON."""
    print(f"  [1/2] Uploading: {file_path} ...")
    fname = os.path.basename(file_path)
    with open(file_path, "rb") as f:
        resp = requests.post(
            UPLOAD_FILE_URL,
            headers=AUTH_HEADER,
            files={"file": (fname, f)},
            timeout=120,
        )
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 200:
        raise RuntimeError(f"Upload failed: {data}")
    print(f"  Upload OK (requestId={data.get('requestId', '?')})")
    return data


def transcribe(file_url: str, file_name: str = "audio.wav") -> dict:
    """Call speech recognition workflow with uploaded file."""
    payload = {
        "input": {
            "input_audio_0": {
                "filename": file_name,
                "url": file_url,
            }
        }
    }
    print(f"  [2/2] Calling ASR workflow ...")
    resp = requests.post(WORKFLOW_URL, headers=JSON_HEADER, json=payload, timeout=300)
    resp.raise_for_status()
    data = resp.json()
    return data


def extract_text(asr_result: dict) -> str:
    """Extract transcribed text from ASR workflow response."""
    data = asr_result.get("data", {})
    result = data.get("result", {})

    # The workflow outputs "output_text_0"
    if isinstance(result, dict) and "output_text_0" in result:
        return result["output_text_0"]

    # Fallback: search common keys
    def find_text(d, depth=0):
        if depth > 5 or d is None:
            return None
        if isinstance(d, str) and len(d) > 10:
            return d
        if isinstance(d, dict):
            for key in ["output_text_0", "text", "transcript", "content", "result"]:
                if key in d and isinstance(d[key], str) and len(d[key]) > 10:
                    return d[key]
            for v in d.values():
                r = find_text(v, depth + 1)
                if r:
                    return r
        return None

    text = find_text(asr_result)
    return text or json.dumps(asr_result, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(
        description="Transcribe audio via 影刀 AI Work OS ASR workflow"
    )
    parser.add_argument("audio_file", help="Path to WAV audio file (16kHz mono)")
    parser.add_argument("--output", "-o", help="Output transcript file", default=None)
    args = parser.parse_args()

    audio_file = args.audio_file
    if not os.path.exists(audio_file):
        print(f"ERROR: file not found: {audio_file}")
        sys.exit(1)

    # Step 1: Upload
    upload_result = upload_file(audio_file)
    upload_data = upload_result.get("data", upload_result)
    file_url = upload_data.get("fileReadUrl", "") or upload_data.get("url", "")
    file_name = os.path.basename(audio_file)

    if not file_url:
        print("ERROR: could not find file URL in upload response.")
        print(json.dumps(upload_result, ensure_ascii=False, indent=2))
        sys.exit(1)

    # Step 2: Transcribe
    asr_result = transcribe(file_url, file_name)
    text = extract_text(asr_result)

    print(f"\n{'=' * 60}")
    print(f"  Transcription complete ({len(text)} characters)")
    print(f"{'=' * 60}")
    print(text[:1500])
    if len(text) > 1500:
        print(f"\n  ... (total {len(text)} chars, preview truncated)")

    # Save
    output_path = args.output
    if output_path is None:
        base = os.path.splitext(audio_file)[0]
        output_path = f"{base}_transcript.txt"

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"\n  Transcript saved: {output_path}")

    # Print to stdout for piping
    print("\n---TRANSCRIPT_START---")
    print(text)
    print("---TRANSCRIPT_END---")


if __name__ == "__main__":
    main()
