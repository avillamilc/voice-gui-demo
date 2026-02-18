# scripts/generate_audio.py
#
# VERY SIMPLE + VERY OBVIOUS "mock" generator for your Streamlit demo.
# Your teammate will replace this later with the real backend.
#
# What it does:
# 1) Reads a request JSON that contains:
#    - baseline_path: input wav
#    - word_params: dict of word_index -> {param -> value}
#    - output_path: where to write generated wav
# 2) Applies two obvious demo effects so you can clearly hear a change each submit:
#    - Adds a short BEEP at the beginning (frequency depends on params)
#    - Changes speed slightly (tempo/pitch) using resampling (depends on params)
#
# Usage:
#   python scripts/generate_audio.py --request requests/ex1_request.json

import argparse
import json
import math
import os
import random
import wave
import audioop
from pathlib import Path


def clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


def compute_intensity(word_params: dict) -> float:
    """
    Compress all word params into one scalar 0..1
    (only for demo effects).
    """
    if not word_params:
        return 0.0

    total = 0.0
    count = 0

    for _, pmap in word_params.items():
        if not isinstance(pmap, dict):
            continue
        for _, v in pmap.items():
            try:
                total += float(v)
                count += 1
            except Exception:
                pass

    if count == 0:
        return 0.0

    # Your UI ranges are around 0..2; normalize roughly into 0..1
    avg = total / count
    return clamp(avg / 2.0, 0.0, 1.0)


def make_beep_mono(sample_rate: int, duration_s: float, freq_hz: float, amplitude: int = 12000) -> bytes:
    """
    Generate a 16-bit PCM mono beep.
    """
    n = int(sample_rate * duration_s)
    buf = bytearray()
    for i in range(n):
        t = i / sample_rate
        s = int(amplitude * math.sin(2 * math.pi * freq_hz * t))
        # 16-bit little-endian
        buf.append(s & 0xFF)
        buf.append((s >> 8) & 0xFF)
    return bytes(buf)


def add_light_noise(frames: bytes, sample_width: int, noise_level: float) -> bytes:
    """
    Adds light white noise to 16-bit PCM (demo only).
    noise_level: 0..1
    """
    if noise_level <= 0.0:
        return frames
    if sample_width != 2:
        return frames  # keep it simple

    nbytes = len(frames)
    amp = int(2000 * noise_level)  # noticeable but not insane
    noise = bytearray(nbytes)

    for i in range(0, nbytes, 2):
        r = random.randint(-amp, amp)
        noise[i] = r & 0xFF
        noise[i + 1] = (r >> 8) & 0xFF

    return audioop.add(frames, bytes(noise), sample_width)


def process_wav(baseline_path: str, output_path: str, word_params: dict) -> None:
    with wave.open(baseline_path, "rb") as wf:
        nchannels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        framerate = wf.getframerate()
        nframes = wf.getnframes()
        comptype = wf.getcomptype()

        frames = wf.readframes(nframes)

    if comptype != "NONE":
        raise RuntimeError("Only uncompressed PCM WAV is supported in this demo script.")

    intensity = compute_intensity(word_params)  # 0..1

    # -----------------------------------------
    # 1) BEEP at the beginning (very obvious)
    #    Frequency changes with intensity
    # -----------------------------------------
    beep_freq = 440.0 + 660.0 * intensity  # 440..1100 Hz
    beep = make_beep_mono(framerate, duration_s=0.18, freq_hz=beep_freq)

    if nchannels == 2:
        beep = audioop.tostereo(beep, 2, 1, 1)

    frames = beep + frames

    # -----------------------------------------
    # 2) Speed/Pitch change (very obvious)
    #    Using audioop.ratecv
    # -----------------------------------------
    # Map intensity -> speed factor: 0.80..1.20
    factor = 0.80 + 0.40 * intensity
    new_rate = max(8000, int(framerate * factor))

    frames, _state = audioop.ratecv(frames, sampwidth, nchannels, framerate, new_rate, None)

    # -----------------------------------------
    # 3) Tiny noise + volume tweak (optional)
    # -----------------------------------------
    frames = add_light_noise(frames, sampwidth, noise_level=0.10 * intensity)

    # small gain boost when intensity high (makes it even more noticeable)
    gain = 1.0 + 0.35 * intensity
    frames = audioop.mul(frames, sampwidth, gain)

    # Ensure output directory exists
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    # IMPORTANT:
    # Write WAV header using ORIGINAL framerate.
    # Since we resampled to new_rate but write framerate as original,
    # it produces a clear pitch/tempo change (demo effect).
    with wave.open(output_path, "wb") as out:
        out.setnchannels(nchannels)
        out.setsampwidth(sampwidth)
        out.setframerate(framerate)
        out.writeframes(frames)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True, help="Path to request JSON")
    args = parser.parse_args()

    with open(args.request, "r", encoding="utf-8") as f:
        req = json.load(f)

    baseline_path = req["baseline_path"]
    output_path = req["output_path"]
    word_params = req.get("word_params", {})

    if not os.path.exists(baseline_path):
        raise FileNotFoundError(f"baseline_path not found: {baseline_path}")

    process_wav(baseline_path, output_path, word_params)

    print(f"Generated: {output_path}")


if __name__ == "__main__":
    main()
