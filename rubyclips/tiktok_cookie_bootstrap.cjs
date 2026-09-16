const fs=require('fs');
const puppeteer=require('puppeteer');
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{
  const browser=await puppeteer.launch({headless:true,args:['--no-sandbox','--disable-dev-shm-usage','--disable-blink-features=AutomationControlled']});
  const page=await browser.newPage();
  await page.setViewport({width:1365,height:900});
  await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36');
  await page.evaluateOnNewDocument(()=>Object.defineProperty(navigator,'webdriver',{get:()=>undefined}));
  await page.goto('https://www.tiktok.com/@muffindrama_us',{waitUntil:'domcontentloaded',timeout:90000});
  await sleep(10000);
  const cookies=await page.cookies('https://www.tiktok.com/');
  const names=cookies.map(c=>c.name).sort();
  console.log('TikTok cookie names:',names.join(', '));
  console.log('Has msToken:',names.includes('msToken'));
  fs.writeFileSync('/tmp/tiktok.cookies',cookies.map(c=>`${c.name}=${c.value}`).join('; '),{mode:0o600});
  await browser.close();
  if(!names.includes('msToken')) process.exit(2);
})().catch(e=>{console.error(e.message);process.exit(1)});
