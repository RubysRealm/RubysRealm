#!/usr/bin/env python3
import asyncio
import subprocess

import edge_tts

import pipeline as p
import renderer_v2 as r


async def _edge_once(text, voice, path):
    if path.exists():
        path.unlink()
    comm = edge_tts.Communicate(text=text, voice=voice, rate="+5%")
    with path.open("wb") as f:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
    if not path.exists() or path.stat().st_size < 2000:
        raise RuntimeError("TTS returned too little audio")
    return p.probe_duration(path)


async def resilient_synthesize(text, voice, path):
    """Fast natural voice attempt, then guaranteed zero-cost local speech fallback."""
    last = None
    candidates = [voice]
    if voice != "en-US-AriaNeural":
        candidates.append("en-US-AriaNeural")

    for candidate in candidates:
        try:
            return await asyncio.wait_for(_edge_once(text, candidate, path), timeout=15)
        except Exception as exc:
            last = exc
            if path.exists():
                path.unlink()

    # Local fallback via espeak-ng. It is less natural, but it guarantees a complete
    # narrated episode without a paid service or a network dependency.
    wav = path.with_suffix(".wav")
    voice_name = "en-us"
    pitch = "48"
    speed = "170"
    if "Jenny" in voice or "Aria" in voice:
        pitch = "58"
        speed = "174"
    elif "Guy" in voice:
        pitch = "42"
        speed = "168"
    elif "Davis" in voice:
        pitch = "36"
        speed = "158"
    try:
        subprocess.run([
            "espeak-ng", "-v", voice_name, "-p", pitch, "-s", speed,
            "-w", str(wav), text
        ], check=True, timeout=20)
        subprocess.run([
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(wav), "-c:a", "libmp3lame", "-b:a", "112k", str(path)
        ], check=True, timeout=20)
        if not path.exists() or path.stat().st_size < 2000:
            raise RuntimeError("local narration fallback returned no usable audio")
        return p.probe_duration(path)
    except Exception as exc:
        raise RuntimeError(f"Narration failed after natural voice attempt and local fallback: {last}; local={exc}") from exc
    finally:
        wav.unlink(missing_ok=True)


async def main():
    p.synthesize = resilient_synthesize
    await r.run_v2()


if __name__ == "__main__":
    asyncio.run(main())
