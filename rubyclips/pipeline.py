#!/usr/bin/env python3
import asyncio
import hashlib
import json
import os
import random
import shutil
import subprocess
import textwrap
import urllib.error
import urllib.request
from pathlib import Path

import edge_tts
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
BASE = ROOT / "rubyclips"
WORK = BASE / "work"
OUT = BASE / "output"
IMAGES = WORK / "images"
AUDIO = WORK / "audio"
SEGMENTS = WORK / "segments"
STATE_PATH = BASE / "state.json"
IMAGE_URL = os.getenv("STORY_IMAGE_URL", "https://rubys-realm.vercel.app/api/story-image")
OIDC_TOKEN = os.getenv("GITHUB_OIDC_TOKEN", "").strip()
RUN_SEED = int(os.getenv("RUBYCLIPS_SEED", "1") or "1")
WIDTH, HEIGHT, FPS = 1080, 1920, 30

SERIES_TITLE = "The Contract After Midnight"
SERIES_ID = "contract-after-midnight"
TOTAL_EPISODES = 8
CAST = {
    "A": {"name": "Maya", "voice": "en-US-JennyNeural", "look": "Maya Hart, 27, dark auburn shoulder-length hair, green eyes, navy blazer, intelligent and guarded"},
    "B": {"name": "Adrian", "voice": "en-US-GuyNeural", "look": "Adrian Vale, 32, black hair, charcoal suit, controlled expression, hotel heir"},
    "C": {"name": "Elise", "voice": "en-US-AriaNeural", "look": "Elise Rowan, 36, blonde bob, cream trench coat, senior attorney, composed and unreadable"},
    "D": {"name": "Graham", "voice": "en-US-DavisNeural", "look": "Graham Vale, 61, silver hair, navy overcoat, hotel founder, tired but commanding"},
}
CAST_BIBLE = "; ".join(v["look"] for v in CAST.values())

EPISODES = {
    1: {
        "title": "The Clause",
        "scenes": [
            ("Late-night legal office. Maya opens a sealed contract addressed to her while the city glows outside the windows.", [("A", "This is not my client file. Why is my name on it?"), ("C", "Because you were never supposed to open it before midnight.")]),
            ("Close view of the contract on a conference table as Maya points to a trustee clause and Elise watches tensely.", [("A", "It names me acting trustee if Graham Vale is missing at midnight."), ("C", "That clause was drafted three weeks before you met this firm.")]),
            ("Adrian storms into the office and confronts Maya across the table while Elise stands between them.", [("B", "My father vanished tonight, and somehow you control his hotels?"), ("A", "I did not write this, but that signature is his.")]),
            ("Security monitor shows Graham leaving a hotel garage beside a woman in a cream coat while Maya and Adrian stare.", [("B", "That coat is yours, Elise."), ("C", "It is common. That woman is not me.")]),
            ("Office lights flicker at midnight and a secure cabinet unlocks by itself as Maya's phone receives hotel credentials.", [("A", "The contract just activated."), ("B", "Then you are coming with me to the hotel right now.")]),
            ("Dark luxury hotel penthouse. Maya and Adrian find a warm coffee cup, a broken watch, and Graham's phone ringing on a desk.", [("A", "Someone was here minutes ago."), ("D", "Maya, do not trust the woman in the cream coat.")]),
        ],
    },
    2: {
        "title": "The Missing Floor",
        "scenes": [
            ("Hotel penthouse after the mysterious call ends. Maya and Adrian stare at Graham's silent phone.", [("B", "That was my father. I know his voice."), ("A", "Then he wanted me to hear that warning, not you.")]),
            ("Private elevator panel lights up with an unmarked nineteenth-floor service code on Maya's phone.", [("A", "My credentials just unlocked a floor that is not on the directory."), ("B", "There has not been a nineteenth floor since I was a kid.")]),
            ("Maya and Adrian step from a service elevator into a sealed dusty hotel corridor with covered furniture.", [("B", "My father closed this level after a fire."), ("A", "Then explain the fresh footprints in the dust.")]),
            ("A hidden room contains old photographs, including Graham beside a younger woman who resembles Maya.", [("A", "That woman is my mother."), ("B", "Why would my father have pictures of your family?")]),
            ("Elise appears at the far end of the sealed corridor holding a keycard and looking alarmed.", [("C", "You both need to leave before security finds you here."), ("A", "How did you get onto a floor you said did not exist?")]),
            ("A recorder on a desk plays while security doors slam shut around Maya and Adrian and footsteps approach.", [("D", "Maya is the only person who can finish what we started."), ("B", "Someone is coming. Turn off the light.")]),
        ],
    },
    3: {
        "title": "The Photograph",
        "scenes": [
            ("Maya and Adrian hide behind covered furniture as a shadowy figure walks through the sealed corridor.", [("A", "Whoever that is knows this floor better than we do."), ("B", "And they know we found the room.")]),
            ("The shadow disappears into a service stairwell, leaving behind a torn photograph corner on the floor.", [("B", "This piece came from the photo of your mother."), ("A", "So someone came here tonight to remove evidence.")]),
            ("Maya studies the complete photograph under a desk lamp and notices a hotel development blueprint in the background.", [("A", "My mother was not a guest. She was working with Graham."), ("B", "My father never mentioned a partner before the hotel opened.")]),
            ("Elise privately meets Maya in a quiet hotel bar and slides an old legal folder across the table.", [("C", "Your mother designed the trust structure behind this company."), ("A", "Then why was her name erased from every public record?")]),
            ("Adrian watches from across the lobby as Elise leaves and Maya opens a page showing two signatures.", [("B", "You believed her?"), ("A", "I believe this document, and one signature is yours from ten years ago.")]),
            ("Adrian looks stunned as Maya shows him a childhood signature beside a transfer clause he does not remember signing.", [("B", "I was seventeen. I never signed this contract."), ("A", "Then somebody built this entire company on a forged signature.")]),
        ],
    },
    4: {
        "title": "The Forged Heir",
        "scenes": [
            ("Maya and Adrian compare the forged signature with archived records in a locked hotel office before dawn.", [("B", "If that signature is fake, my ownership can be challenged."), ("A", "Which gives someone a reason to keep Graham missing.")]),
            ("Maya finds a recurring notary stamp linked to an abandoned law office while Adrian photographs the page.", [("A", "Every disputed document used the same notary."), ("B", "That office closed the week my father disappeared the first time.")]),
            ("They enter the abandoned law office in daylight and find recently used lights and a running shredder.", [("B", "This place is supposed to be empty."), ("A", "Someone has been destroying files all morning.")]),
            ("Maya pulls a half-shredded page showing Elise's name as a witness while Adrian reads over her shoulder.", [("A", "Elise witnessed the original transfer."), ("B", "She has been inside this from the beginning.")]),
            ("Elise arrives at the doorway with her hands visible, insisting they listen before judging her.", [("C", "I witnessed it because Graham asked me to protect Adrian."), ("B", "You protected me by forging my name?")]),
            ("Elise reveals a hidden audio file on her phone; Graham's voice says the forgery was meant to stop a hostile takeover.", [("D", "If Adrian signs willingly, they can take everything."), ("A", "Who is they?")]),
        ],
    },
    5: {
        "title": "The Buyer",
        "scenes": [
            ("Maya, Adrian, and Elise listen to Graham's recording in the abandoned office as a company name appears in the file metadata.", [("C", "The buyer called itself Northbridge Holdings."), ("B", "Northbridge has tried to buy our hotels for years.")]),
            ("Maya searches public corporate records on a laptop and finds Northbridge connected to a shell company near the hotel.", [("A", "The shell company bought the building beside your headquarters."), ("B", "So they have been watching us from across the street.")]),
            ("Adrian and Maya enter a glass office building posing as potential tenants and spot surveillance photos on a desk.", [("B", "Those are pictures of us from last night."), ("A", "And that one was taken outside my apartment last month.")]),
            ("A security guard approaches; Maya quietly photographs a board showing Graham's movements and an internal code name.", [("A", "They call Graham 'Asset One.'"), ("B", "Then he is alive, and they are holding him somewhere.")]),
            ("Elise calls from the hotel garage warning that someone has accessed the trust account using Adrian's credentials.", [("C", "Adrian, your login just approved a nine-million-dollar transfer."), ("B", "I have been standing beside Maya the entire time.")]),
            ("Maya looks at the transfer destination and sees her own name listed as beneficiary while Adrian recoils.", [("B", "The money went to you."), ("A", "No. Someone wants it to look like I betrayed you.")]),
        ],
    },
    6: {
        "title": "The Betrayal",
        "scenes": [
            ("Hotel command office. Adrian blocks Maya from leaving while the fraudulent transfer flashes on a monitor.", [("B", "Every trail ends at your name."), ("A", "Because whoever built this knew exactly what would make you turn on me.")]),
            ("Maya hands Adrian her phone showing an impossible login timestamp from when both were on camera elsewhere.", [("A", "My account was accessed while we were inside Northbridge."), ("B", "Then both of us were cloned.")]),
            ("Elise opens a secure hotel server rack and finds a small unauthorized device hidden behind network cables.", [("C", "Someone installed this inside your private network."), ("B", "Only executive security has access to this room.")]),
            ("They review staff access logs and discover the same badge used during every suspicious event belongs to Graham.", [("A", "Your father's badge never stopped moving."), ("B", "Either he is here, or someone wants us chasing his ghost.")]),
            ("Maya follows the badge signal into the hotel laundry level and finds Graham's navy overcoat hanging beside a hidden door.", [("A", "Adrian, I found his coat."), ("B", "Do not open that door without me.")]),
            ("Maya opens the hidden door anyway and finds Graham alive in a small surveillance room, watching hotel cameras.", [("D", "You were faster than I expected."), ("A", "You were never missing.")]),
        ],
    },
    7: {
        "title": "The Founder",
        "scenes": [
            ("Hidden surveillance room. Graham faces Maya while Adrian arrives furious and Elise stays near the door.", [("B", "You let us think you were kidnapped."), ("D", "I needed Northbridge to believe the trust had no one left protecting it.")]),
            ("Graham shows a wall of evidence mapping Northbridge payments to hotel executives and forged legal documents.", [("D", "The attack came from inside our own board."), ("A", "Then the contract made me bait.")]),
            ("Maya confronts Graham beside the evidence wall while Adrian realizes she was deliberately placed in danger.", [("A", "You used my mother's history to pull me into this."), ("D", "Your mother built the safeguard. I trusted you to finish it.")]),
            ("Elise reveals a board meeting invitation scheduled in one hour where the hostile transfer will become permanent.", [("C", "If the board votes today, Northbridge gets legal control."), ("B", "Then we stop the vote in front of everyone.")]),
            ("The four enter a crowded luxury boardroom as executives react to Graham appearing alive.", [("D", "Before you vote, you should know why I disappeared."), ("A", "And why nine million dollars was moved using forged credentials.")]),
            ("One executive quietly reaches for a phone under the table as Maya notices and the room erupts into argument.", [("A", "Adrian, the man at the end of the table is deleting something."), ("B", "Lock the room. Nobody leaves.")]),
        ],
    },
    8: {
        "title": "The Last Signature",
        "scenes": [
            ("Locked boardroom. Adrian takes the executive's phone while Maya projects transfer records for the board.", [("B", "This phone authorized the fake transfer."), ("A", "And the money never left the company. It was staged as evidence.")]),
            ("Elise presents original notarized documents showing Maya's mother created a veto right hidden inside the trust.", [("C", "One valid trustee signature can freeze the takeover."), ("A", "That is why the contract named me.")]),
            ("Maya hesitates over the signature page while Graham and Adrian watch, understanding the choice is hers alone.", [("D", "I will not ask you to clean up my mistakes."), ("A", "Good. I am signing for my mother, not for you.")]),
            ("Maya signs. Phones around the boardroom light up as the takeover vote is suspended and security enters.", [("B", "The transfer is frozen."), ("C", "Northbridge just lost its only legal path to the hotels.")]),
            ("Later on the hotel rooftop at sunrise, Adrian thanks Maya while the city brightens behind them.", [("B", "You could have walked away at any point."), ("A", "I almost did. Then everybody kept lying to me.")]),
            ("Maya receives a new sealed envelope with her mother's handwriting and looks stunned as Adrian notices.", [("B", "Please tell me that is not another contract."), ("A", "It is worse. This one is dated tomorrow.")]),
        ],
    },
}


def run(cmd, **kwargs):
    return subprocess.run(cmd, check=True, **kwargs)


def probe_duration(path):
    p = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)], capture_output=True, text=True)
    return float(p.stdout.strip())


async def synthesize(text, voice, path):
    comm = edge_tts.Communicate(text=text, voice=voice, rate="+5%")
    with path.open("wb") as f:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
    if not path.exists() or path.stat().st_size < 2000:
        raise RuntimeError(f"TTS failed for {path.name}")
    return probe_duration(path)


def request_image(scene, previous_scene, next_scene, index, season, episode, path):
    if not OIDC_TOKEN:
        raise RuntimeError("Missing GitHub OIDC token")
    payload = {
        "mode": "rubyclips-drama",
        "title": SERIES_TITLE,
        "part": f"Season {season}, Episode {episode}",
        "beat": scene,
        "previousBeat": previous_scene or "",
        "nextBeat": next_scene or "",
        "index": index,
        "seed": RUN_SEED + index + season * 100 + episode * 10,
        "cast": CAST_BIBLE,
    }
    body = json.dumps(payload).encode()
    last = None
    for attempt in range(3):
        req = urllib.request.Request(
            IMAGE_URL,
            data=body,
            method="POST",
            headers={"Authorization": f"Bearer {OIDC_TOKEN}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                data = r.read()
            if len(data) < 10000:
                raise RuntimeError(f"image response too small: {len(data)}")
            path.write_bytes(data)
            return True
        except Exception as exc:
            last = exc
            import time
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"image generation failed after retries: {last}")


def fallback_image(index, path):
    rng = random.Random(RUN_SEED + index * 97)
    top = (rng.randint(18, 55), rng.randint(20, 65), rng.randint(35, 85))
    bottom = (rng.randint(4, 20), rng.randint(7, 25), rng.randint(15, 40))
    im = Image.new("RGB", (WIDTH, HEIGHT), top)
    d = ImageDraw.Draw(im)
    for y in range(HEIGHT):
        q = y / max(1, HEIGHT - 1)
        c = tuple(int(top[i] * (1 - q) + bottom[i] * q) for i in range(3))
        d.line((0, y, WIDTH, y), fill=c)
    d.rectangle((0, 1280, WIDTH, HEIGHT), fill=(24, 28, 36))
    d.rectangle((80, 930, 1000, 1510), fill=(45, 52, 64), outline=(120, 132, 150), width=5)
    for x in (180, 430, 680, 880):
        d.rectangle((x, 1010, x + 95, 1230), fill=(90, 108, 132))
    people = [(330, (30, 55, 95)), (735, (66, 66, 72))]
    for x, coat in people:
        d.ellipse((x - 75, 540, x + 75, 690), fill=(210, 165, 135), outline=(45, 40, 40), width=4)
        d.rounded_rectangle((x - 105, 675, x + 105, 1110), radius=45, fill=coat)
        d.rectangle((x - 70, 1090, x - 20, 1390), fill=(30, 34, 42))
        d.rectangle((x + 20, 1090, x + 70, 1390), fill=(30, 34, 42))
    d.ellipse((520, 1140, 650, 1220), fill=(170, 120, 65), outline=(235, 215, 180), width=4)
    im.save(path, quality=92)


def ass_escape(text):
    return str(text).replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}")


def wrap_caption(text, width=34):
    return r"\N".join(textwrap.wrap(text, width=width, break_long_words=False, break_on_hyphens=False))


def ass_time(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def concat_audio(files, out):
    listing = out.with_suffix(".txt")
    listing.write_text("\n".join(f"file '{p.as_posix()}'" for p in files) + "\n")
    run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(listing), "-ar", "48000", "-ac", "2", "-c:a", "aac", "-b:a", "160k", str(out)])


def render_segment(image, audio, out):
    run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-loop", "1", "-i", str(image), "-i", str(audio),
        "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,format=yuv420p",
        "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "160k", "-shortest", str(out)
    ])


async def main():
    for p in (WORK, OUT):
        if p.exists():
            shutil.rmtree(p)
    for p in (IMAGES, AUDIO, SEGMENTS, OUT):
        p.mkdir(parents=True, exist_ok=True)

    state = json.loads(STATE_PATH.read_text())
    season = max(1, int(state.get("seasonNumber", 1)))
    episode = min(TOTAL_EPISODES, max(1, int(state.get("episodeNumber", 1))))
    plan = EPISODES[episode]
    scenes = plan["scenes"]
    production_id = f"{SERIES_ID}-s{season}e{episode}"

    captions = []
    scene_segments = []
    global_time = 0.0
    ai_visuals = 0

    for si, (visual, lines) in enumerate(scenes):
        line_files = []
        local_time = 0.0
        for li, (speaker, text) in enumerate(lines):
            mp3 = AUDIO / f"s{si:02d}_l{li:02d}.mp3"
            duration = await synthesize(text, CAST[speaker]["voice"], mp3)
            line_files.append(mp3)
            captions.append({
                "start": global_time + local_time,
                "end": global_time + local_time + duration,
                "speaker": CAST[speaker]["name"],
                "text": text,
            })
            local_time += duration

        scene_audio = AUDIO / f"scene_{si:02d}.m4a"
        concat_audio(line_files, scene_audio)
        scene_duration = probe_duration(scene_audio)

        image = IMAGES / f"scene_{si:02d}.jpg"
        try:
            prev_visual = scenes[si - 1][0] if si else ""
            next_visual = scenes[si + 1][0] if si + 1 < len(scenes) else ""
            if request_image(visual, prev_visual, next_visual, si, season, episode, image):
                ai_visuals += 1
        except Exception as exc:
            print(f"AI visual {si} failed; using original procedural fallback: {exc}")
            fallback_image(si, image)

        segment = SEGMENTS / f"scene_{si:02d}.mp4"
        render_segment(image, scene_audio, segment)
        scene_segments.append(segment)
        global_time += scene_duration

    concat_list = WORK / "segments.txt"
    concat_list.write_text("\n".join(f"file '{p.as_posix()}'" for p in scene_segments) + "\n")
    base_video = WORK / "base.mp4"
    run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(concat_list), "-c", "copy", str(base_video)])
    total_duration = probe_duration(base_video)

    ass = WORK / "captions.ass"
    title_text = ass_escape(SERIES_TITLE.upper()) + r"\N" + ass_escape(f"SEASON {season}  •  EPISODE {episode}")
    ass_lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 1080",
        "PlayResY: 1920",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding",
        "Style: Title,DejaVu Sans,48,&H00FFFFFF,&H00FFFFFF,&H00101010,&H78000000,-1,0,0,0,100,100,0,0,3,2,0,8,70,70,70,1",
        "Style: Caption,DejaVu Sans,58,&H00FFFFFF,&H00FFFFFF,&H00101010,&H98000000,-1,0,0,0,100,100,0,0,3,3,0,2,70,70,230,1",
        "Style: Speaker,DejaVu Sans,34,&H00DDEEFF,&H00FFFFFF,&H00101010,&H00000000,-1,0,0,0,100,100,0,0,1,2,0,2,70,70,340,1",
        "",
        "[Events]",
        "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text",
        f"Dialogue: 0,{ass_time(0)},{ass_time(total_duration)},Title,,0,0,0,,{title_text}",
    ]
    for c in captions:
        start, end = ass_time(c["start"]), ass_time(c["end"])
        speaker = ass_escape(c["speaker"].upper())
        text = ass_escape(wrap_caption(c["text"]))
        ass_lines.append(f"Dialogue: 0,{start},{end},Speaker,,0,0,0,,{speaker}")
        ass_lines.append(f"Dialogue: 0,{start},{end},Caption,,0,0,0,,{text}")
    ass.write_text("\n".join(ass_lines) + "\n")

    final_name = f"rubyclips-s{season:02d}e{episode:02d}.mp4"
    final_video = OUT / final_name
    run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(base_video),
        "-vf", f"ass={ass.as_posix()}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
        "-c:a", "copy", "-movflags", "+faststart", str(final_video)
    ])

    duration = probe_duration(final_video)
    if not (35 <= duration <= 110):
        raise RuntimeError(f"RubyClips duration outside gate: {duration:.2f}s")
    if final_video.stat().st_size < 500_000:
        raise RuntimeError("RubyClips MP4 is unexpectedly small")

    story_payload = {
        "series": SERIES_TITLE,
        "season": season,
        "episode": episode,
        "episodeTitle": plan["title"],
        "scenes": scenes,
    }
    story_hash = hashlib.sha256(json.dumps(story_payload, sort_keys=True).encode()).hexdigest()
    video_hash = hashlib.sha256(final_video.read_bytes()).hexdigest()
    manifest = {
        "platform": "rubyclips-original-drama-v1",
        "rightsPolicy": "original-generated-assets-only",
        "originalOnly": True,
        "generatedVisualsOnly": True,
        "seriesId": SERIES_ID,
        "seriesTitle": SERIES_TITLE,
        "seasonNumber": season,
        "episodeNumber": episode,
        "totalEpisodes": TOTAL_EPISODES,
        "episodeTitle": plan["title"],
        "productionId": production_id,
        "durationSeconds": round(duration, 3),
        "sceneCount": len(scenes),
        "aiVisualCount": ai_visuals,
        "fallbackVisualCount": len(scenes) - ai_visuals,
        "captionsBurnedIn": True,
        "qualityPassed": True,
        "file": final_name,
        "storyFingerprint": f"sha256:{story_hash}",
        "videoFingerprint": f"sha256:{video_hash}",
        "targetChannel": "rubaradaclips",
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
