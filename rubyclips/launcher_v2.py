#!/usr/bin/env python3
import asyncio
import subprocess
from pathlib import Path

import edge_tts

import pipeline as p
import renderer_v2 as r


async def resilient_synthesize(text, voice, path):
    """Prefer natural Edge voices, retry transient failures, then use local FFmpeg flite."""
    candidates = [voice]
    if voice != "en-US-AriaNeural":
        candidates.append("en-US-AriaNeural")
    last = None

    for candidate in candidates:
        for attempt in range(3):
            try:
                if path.exists():
                    path.unlink()
                comm = edge_tts.Communicate(text=text, voice=candidate, rate="+5%")
                with path.open("wb") as f:
                    async for chunk in comm.stream():
                        if chunk["type"] == "audio":
                            f.write(chunk["data"])
                if path.exists() and path.stat().st_size >= 2000:
                    return p.probe_duration(path)
                raise RuntimeError("TTS returned too little audio")
            except Exception as exc:
                last = exc
                if path.exists():
                    path.unlink()
                await asyncio.sleep(2 + attempt * 2)

    # Fully local fallback. No account, API key, payment, or network dependency.
    textfile = path.with_suffix(".txt")
    wav = path.with_suffix(".wav")
    textfile.write_text(text)
    try:
        subprocess.run([
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", f"flite=textfile={textfile.as_posix()}:voice=slt",
            "-ar", "24000", "-ac", "1", str(wav)
        ], check=True)
        subprocess.run([
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(wav), "-c:a", "libmp3lame", "-b:a", "96k", str(path)
        ], check=True)
        if not path.exists() or path.stat().st_size < 2000:
            raise RuntimeError("local narration fallback returned no usable audio")
        return p.probe_duration(path)
    except Exception as exc:
        raise RuntimeError(f"Narration failed after online retries and local fallback: {last}; local={exc}") from exc
    finally:
        textfile.unlink(missing_ok=True)
        wav.unlink(missing_ok=True)


async def main():
    p.synthesize = resilient_synthesize
    await r.run_v2()


if __name__ == "__main__":
    asyncio.run(main())
