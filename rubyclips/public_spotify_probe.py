#!/usr/bin/env python3
import asyncio, json
from pathlib import Path
from playwright.async_api import async_playwright

URL="https://open.spotify.com/embed/episode/2m4ncEaJmzwA9ucqrACTOH?utm_source=generator"
OUT=Path("rubyclips/public_spotify_probe")
OUT.mkdir(parents=True,exist_ok=True)

async def main():
    media_requests=[]
    async with async_playwright() as p:
        browser=await p.chromium.launch(
            headless=True,
            args=["--autoplay-policy=no-user-gesture-required","--disable-features=MediaRouter"]
        )
        page=await browser.new_page(viewport={"width":1280,"height":720})
        page.on("response", lambda r: media_requests.append({
            "url":r.url,
            "status":r.status,
            "content_type":r.headers.get("content-type","")
        }) if any(x in (r.headers.get("content-type","").lower()) for x in ["audio","video","mpeg","mp4","webm","octet-stream"]) or any(x in r.url.lower() for x in ["spotifycdn","scdn","audio","video"]) else None)
        await page.goto(URL,wait_until="domcontentloaded",timeout=90000)
        await page.wait_for_timeout(5000)
        await page.screenshot(path=str(OUT/"before.png"),full_page=True)

        buttons=await page.locator("button").all()
        button_data=[]
        for i,b in enumerate(buttons):
            try:
                button_data.append({
                    "i":i,
                    "text":(await b.inner_text())[:200],
                    "aria":await b.get_attribute("aria-label"),
                    "title":await b.get_attribute("title")
                })
            except: pass

        clicked=False
        candidates=[
            'button[aria-label*="Play" i]',
            'button[title*="Play" i]',
            'button:has-text("Play")',
            '[role="button"][aria-label*="Play" i]'
        ]
        for sel in candidates:
            loc=page.locator(sel)
            if await loc.count():
                try:
                    await loc.first.click(timeout=5000)
                    clicked=True
                    break
                except: pass
        if not clicked:
            for i,b in enumerate(buttons):
                try:
                    aria=(await b.get_attribute("aria-label") or "").lower()
                    txt=(await b.inner_text()).lower()
                    if "play" in aria or "play" in txt:
                        await b.click(timeout=5000)
                        clicked=True
                        break
                except: pass

        await page.wait_for_timeout(12000)
        await page.screenshot(path=str(OUT/"after.png"),full_page=True)

        media=await page.locator("video,audio").evaluate_all("""els => els.map((e,i)=>({
          i,tag:e.tagName,src:e.currentSrc||e.src||'',currentTime:e.currentTime,duration:e.duration,
          paused:e.paused,ended:e.ended,muted:e.muted,volume:e.volume,
          videoWidth:e.videoWidth||0,videoHeight:e.videoHeight||0,
          readyState:e.readyState,networkState:e.networkState
        }))""")
        result={
            "url":URL,
            "title":await page.title(),
            "clickedPlay":clicked,
            "buttons":button_data,
            "mediaElements":media,
            "bodyText":(await page.locator("body").inner_text())[:5000],
            "mediaRequests":media_requests[-200:]
        }
        (OUT/"result.json").write_text(json.dumps(result,indent=2))
        print(json.dumps(result,indent=2))
        await browser.close()

asyncio.run(main())
