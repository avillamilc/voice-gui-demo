# scripts/generate_audio.py
#
# Cloud-safe version (no audioop).
# Uses numpy for demo effects.
#
# Effects:
# 1) Adds a beep at the beginning
# 2) Slight speed change
# 3) Slight volume change

import argparse
import json
import math
import os
import wave
import numpy as np
from pathlib import Path


def clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


def compute_intensity(word_params: dict) -> float:
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

    avg = total / count
    return clamp(avg / 2.0, 0.0, 1.0)


def read_wav(path):
    with wave.open(path, "rb") as wf:
        nchannels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        framerate = wf.getframerate()
        nframes = wf.getnframes()
        frames = wf.readframes(nframes)

    if sampwidth != 2:
        raise RuntimeError("Only 16-bit PCM WAV supported in demo.")

    audio = np.frombuffer(frames, dtype=np.int16)

    if nchannels == 2:
        audio = audio.reshape(-1, 2)

    return audio, framerate, nchannels


def write_wav(path, audio, framerate, nchannels):
    Path(path).parent.mkdir(parents=True, exist_ok=True)

    if nchannels == 2:
        audio = audio.reshape(-1)

    audio = audio.astype(np.int16)

    with wave.open(path, "wb") as wf:
        wf.setnchannels(nchannels)
        wf.setsampwidth(2)
        wf.setframerate(framerate)
        wf.writeframes(audio.tobytes())


def make_beep(sample_rate, duration_s, freq, nchannels):
    t = np.linspace(0, duration_s, int(sample_rate * duration_s), endpoint=False)
    beep = 12000 * np.sin(2 * np.pi * freq * t)
    beep = beep.astype(np.int16)

    if nchannels == 2:
        beep = np.column_stack((beep, beep))

    return beep


def change_speed(audio, factor):
    """
    Simple resampling-based speed change.
    """
    indices = np.arange(0, len(audio), factor)
    indices = indices[indices < len(audio)].astype(int)
    return audio[indices]


def process_wav(baseline_path, output_path, word_params):
    audio, framerate, nchannels = read_wav(baseline_path)

    intensity = compute_intensity(word_params)

    # 1) Add beep
    beep_freq = 440 + 660 * intensity
    beep = make_beep(framerate, 0.18, beep_freq, nchannels)
    audio = np.vstack((beep, audio)) if nchannels == 2 else np.concatenate((beep, audio))

    # 2) Speed change
    factor = 0.8 + 0.4 * intensity
    audio = change_speed(audio, factor)

    # 3) Volume change
    gain = 1.0 + 0.4 * intensity
    audio = np.clip(audio * gain, -32768, 32767)

    write_wav(output_path, audio, framerate, nchannels)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
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
