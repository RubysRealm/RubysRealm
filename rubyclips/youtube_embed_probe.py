#!/usr/bin/env python3
import asyncio,json
from pathlib import Path
from playwright.async_api import async_playwright

URL="https://www.youtube.com/embed/-5JOZTSztgc?autoplay=1&playsinline=1&controls=1"
OUT=Path("rubyclips/youtube_embed_probe")
OUT.mkdir(parents=True,exist_ok=True)

async def main():
  async with async_playwright() as p:
    browser=await p.chromium.launch(headless=True,args=[
      "--autoplay-policy=no-user-gesture-required",
      "--disable-features=MediaRouter",
    ])
    page=await browser.new_page(viewport={"width":1280,"height":720})
    await page.goto(URL,wait_until="domcontentloaded",timeout=90000)
    await page.wait_for_timeout(7000)
    # Dismiss consent or click play if shown.
    for sel in ['button[aria-label*="Accept" i]','button:has-text("Accept all")','.ytp-large-play-button','button[aria-label*="Play" i]']:
      loc=page.locator(sel)
      if await loc.count():
        try: await loc.first.click(timeout=3000)
        except: pass
    await page.wait_for_timeout(12000)
    await page.screenshot(path=str(OUT/"screen.png"))
    media=await page.locator("video").evaluate_all("""els => els.map(e=>({
      currentTime:e.currentTime,duration:e.duration,paused:e.paused,ended:e.ended,
      readyState:e.readyState,videoWidth:e.videoWidth,videoHeight:e.videoHeight,
      muted:e.muted,volume:e.volume,currentSrc:e.currentSrc
    }))""")
    body=(await page.locator("body").inner_text())[:4000]
    result={"url":URL,"title":await page.title(),"media":media,"bodyText":body}
    (OUT/"result.json").write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
    if not media or media[0]["currentTime"] < 2 or media[0]["paused"]:
      raise SystemExit("YouTube browser transport did not advance playback")
    await browser.close()
asyncio.run(main())
