import asyncio, json, os, random, re, shutil, sys, urllib.request
from pathlib import Path
import edge_tts
from reference_media import STYLE, compose_frame, fetch_photo, caption_cues, write_ass, render, verify, media_duration, safe_name, words, run

OUT=Path('tiktok_animator/output'); TMP=Path('tiktok_animator/tmp')
OUT.mkdir(parents=True,exist_ok=True); TMP.mkdir(parents=True,exist_ok=True)

CONCRETE=set('motel hotel office room door hallway corridor street road parking lot pool building house apartment warehouse garage diner cafe restaurant store shop hospital school church farm field forest river bridge station airport train bus truck car vehicle boat desk phone camera monitor key ledger envelope photo photograph deed receipt box safe cash file files cabinet calendar wall floor roof boiler machine air conditioner sign window stairs elevator suitcase bag package map newspaper letter lock gate contractor sheriff deputy police owner clerk manager stranger man woman child worker driver customer storage facility fence deadbolt locksmith'.split())
DRAMA=set('hidden missing locked dead died secret mysterious strange flicker static dark reveal discovered discover found vanished vanish warning broken cracked buried underground false fake stolen chase followed following watched watching unknown empty abandoned impossible suddenly'.split())
VERBS=set('arrived arrive opened open removed remove found find discovered discover called call rang ring returned return stopped stop handed hand lifted lift drove drive walked walk ran run bought buy sold sell climbed climb pulled pull pushed push entered enter left leave followed follow'.split())

MOTEL_STORY='''You buy a fading roadside motel at a county auction because the price looks impossible to ignore. The property sits two miles outside a small town, eighteen doors wrapped around an empty swimming pool, with a front office that still smells like burnt coffee and old carpet. The county paperwork says the place has been closed for three years. A handwritten note taped inside the office drawer says eleven months.

On the first afternoon, a contractor walks the property with you. He points out cracked stucco, two bad air conditioners, a roof patch over room eight, and a boiler old enough to have its own personality. Then he stops in front of a door beside room sixteen. There is no number on it. The county inventory lists only sixteen guest rooms.

You assume the numbering changed years ago, but the key rack behind the desk still has a brass tag stamped seventeen. The key is missing. Under the rack is an old ledger with every room written in blue ink. Room seventeen appears repeatedly, but instead of guest names the entries contain dates, dollar amounts, and one short word: hold.

That night you stay in the office because the utilities have just been restored. At 1:42 in the morning the desk phone rings. The outside line is not connected yet. You answer anyway. For several seconds there is only static, then a man says, very calmly, that the ice machine is empty. The motel has no ice machine. The contractor removed it that afternoon.

You walk outside with a flashlight. Every room is dark except the unnumbered door. A thin line of light shows beneath it even though the breaker to that side of the building is off. When you get close, the light disappears. The door is locked from the inside.

The next morning you call the county clerk and ask for the original floor plan. She sends a scanned drawing from 1978. It shows sixteen guest rooms, but behind the laundry room is a narrow service corridor that vanished from later plans. At the end of that corridor is a small square marked office storage.

You and the contractor remove a sheet of plywood from the laundry wall. Behind it is the corridor. The floor is dusty except for a clean path through the middle, as though someone has been walking there recently. Halfway down is an electrical panel feeding one circuit. The label is handwritten: seventeen.

At the end of the corridor is the back side of the mysterious room. The contractor opens it with a pry bar. Inside there is no bed or bathroom. There is a metal desk, three filing cabinets, a calendar frozen on April from eleven years ago, and an old security monitor connected to cameras around the property. One camera is still working. The picture shows the parking lot in real time.

On the desk is another ledger. This one explains the numbers. For years the previous owner rented normal motel rooms, but he also charged local businesses to store cash, documents, spare keys, and sealed envelopes in room seventeen. Nothing appeared on the motel books. The room operated like an unofficial night safe.

Most entries stop eleven years ago. One does not. Every few months a new amount appears beside the initials C W. The latest entry is dated three weeks before the county auction. You call the former owner. His number is disconnected. Then you discover he died four years earlier.

That afternoon a black pickup pulls into the lot. An older man gets out, looks at the construction dumpster, and asks whether the motel is open. You tell him not yet. He asks if you found the room behind the laundry wall. You do not answer. He smiles like that already answered the question, hands you a plain envelope, and says he will come back after dark for what belongs to him.

Inside the envelope is a photocopy of a deed, a storage receipt, and an old photograph of the motel. Someone circled the ground beneath room seventeen. On the back is written: not in the room. Under it.

The contractor wants to call the police. Before you can, he notices four newer bolts in the floor beneath the metal desk. You move the desk, remove the bolts, and lift a steel plate hidden under the carpet. Below it is a concrete cavity containing a locked fireproof box.

You do not open it. You call the sheriff. While you wait, the security monitor flickers. The parking-lot camera shows the black pickup returning. It stops across the road instead of pulling in. The driver never gets out.

A deputy arrives twenty minutes later. By then the truck is gone. The fireproof box contains old property records, several envelopes of cash, and a second set of ownership documents. One paper appears to transfer a narrow strip of land behind the motel to a company that no longer exists. That strip is exactly where the county plans to build an access road for a new industrial park.

Suddenly the auction price makes sense. The motel itself was never the valuable part.

Over the next week attorneys, county officials, and investigators sort through the papers. The cash is taken as evidence. The ownership claim is disputed. The mysterious man never returns. Three months later the county offers to purchase the disputed strip as part of a settlement. The payment is more than you paid for the entire motel.

You accept, use part of the money to finish the renovations, and finally open sixteen rooms to guests. You leave the seventeenth door exactly where it is. It becomes your locked records room. The old desk phone is gone, the security monitor is disconnected, and the brass key tag hangs behind the front counter as a reminder.

Every few weeks someone checking in notices the tag and asks why there is a key for a room that does not exist. You always give them the same answer. Old motels have strange numbering.'''

STORAGE_STORY='''You buy an abandoned storage unit at auction because nobody else wants it. The listing photos show cardboard boxes, three old lamps, a dented filing cabinet, and a wooden workbench pushed against the back wall. You pay less than the cost of a television and assume the weekend will be spent sorting junk.

The first strange thing is the lock. The facility manager cuts the auction lock in front of you, but underneath it is a second brass lock hidden inside the latch. It looks decades older than the storage building. The manager says he has never seen one installed that way.

You force the latch and roll the door open. Most boxes contain ordinary household things: kitchen glasses wrapped in newspaper, winter coats, tax folders, and framed photographs with every face turned toward the cardboard. The filing cabinet is empty except for one envelope taped under the bottom drawer.

Inside is a Polaroid of the storage facility taken before half the buildings existed. Someone drew a black circle around the exact unit you purchased. On the back are three numbers and the words east wall, six feet.

You assume it is an old maintenance note until you move the workbench. Behind it, several concrete blocks are a slightly different color. When you tap them, one section sounds hollow.

You call your brother before touching anything else. He arrives with a pry bar and immediately tells you to get the manager. The manager looks at the wall and says the facility has no record of repairs inside the unit. He also says the previous renter disappeared eight years ago, but the monthly bill kept paying automatically until three months before the auction.

The three of you remove one block. Behind the wall is a narrow cavity and a steel case wrapped in a contractor trash bag. There is no money inside. There are notebooks, keys, property maps, and dozens of small envelopes, each marked with an address.

Most addresses belong to local businesses. A few are houses. One belongs to the storage facility itself.

The notebooks go back almost twenty years. Every page lists an address, a date, a key number, and a short description such as rear office, basement cabinet, or second register. It looks less like a diary than an inventory of places someone could enter without permission.

The manager wants the case locked back inside the wall until police arrive. Before anyone moves it, your brother finds a newer page. It contains your home address. The date beside it is next Friday.

You call the sheriff.

While you wait, a gray sedan drives slowly through the facility. It passes your unit once, circles the property, and comes back. The driver never looks directly at you, but the car stops long enough for someone in the passenger seat to raise a phone and take a photograph.

The manager starts closing the gate remotely. The sedan accelerates and leaves before the gate reaches the pavement.

A deputy arrives and takes the steel case as evidence. He asks whether anyone besides the three of you knew what was hidden in the wall. As far as you know, nobody did.

That evening you return home and notice a thin scratch around the deadbolt on your back door. Nothing inside appears missing. On the kitchen counter is a folded piece of paper you have never seen before.

It says you bought the wrong locker.

Police search the house and find no one. Your security camera stopped recording for exactly nine minutes that afternoon. The camera company says the device never lost power or internet service.

The next morning, the storage manager calls. Someone cut through the rear fence overnight and opened six units. Nothing was stolen from five of them. In the sixth, every cardboard box was removed, but expensive tools sitting near the door were left behind.

The emptied unit was directly across from yours.

Investigators search old rental records and discover both units were leased under different names but paid from the same bank account. The account belonged to a locksmith company that closed twelve years earlier. The listed owner died before either storage lease was created.

The keys from the steel case eventually explain the rest. Several fit obsolete commercial locks at buildings that have since been renovated. Others match lock models still used around town. One opens the storage facility maintenance room.

Inside that room, behind a shelf, deputies find another hidden compartment containing old security tapes, blank access cards, and photographs of businesses after closing time.

The storage unit was never simply a place to hide records. It was the archive for a burglary operation that had lasted for years.

Investigators believe the missing renter kept watching the auction after his automatic payments failed. He expected a buyer to expose the hidden wall, making it easier to recover the case without drawing attention to himself.

The gray sedan is found abandoned two counties away. The renter is eventually identified, but not immediately arrested. The investigation expands into several old unsolved burglaries.

Two months later the facility offers to refund your auction payment. You decline. Technically the lamps and workbench still belong to you.

You keep one thing after investigators release it: the original Polaroid of the facility. You frame it in your garage, but you cover the handwritten numbers on the back.

You never buy another abandoned storage unit.'''

STORY_BANK=[('Your Life as a Motel Owner',MOTEL_STORY),('Your Life After Buying a Storage Unit',STORAGE_STORY)]

SPECIFIC=[
 (('fireproof box','steel plate','concrete cavity'),'locked fireproof box hidden beneath a floor'),
 (('security monitor','parking-lot camera'),'old security monitor parking lot'),
 (('unnumbered door','room seventeen','room 17'),'old motel hallway closed door'),
 (('service corridor','corridor'),'narrow service corridor old building'),
 (('ledger','filing cabinet'),'old ledger filing cabinet desk'),
 (('envelope','deed','receipt','property records'),'old property deed envelope documents'),
 (('black pickup','pickup'),'black pickup truck roadside'),
 (('sheriff','deputy'),'sheriff patrol car roadside'),
 (('industrial park','access road'),'industrial park construction access road'),
 (('key rack','brass tag','key tag'),'vintage motel key rack brass key'),
 (('contractor','renovation','cracked stucco'),'old motel renovation contractor'),
 (('front office','front desk'),'vintage motel front desk office'),
 (('storage unit','storage facility'),'storage unit facility exterior'),
 (('gray sedan','sedan'),'gray sedan parking lot'),
 (('deadbolt','back door'),'residential back door deadbolt'),
 (('security camera',),'home security camera exterior'),
 (('rear fence',),'chain link fence storage facility'),
 (('locksmith',),'old locksmith keys workbench'),
 (('motel',),'old roadside motel exterior')]

def visual_query(text):
 low=text.lower()
 for keys,q in SPECIFIC:
  if any(k in low for k in keys): return q
 toks=[t.lower() for t in re.findall(r"[A-Za-z][A-Za-z0-9'-]+",text)]; concrete=[]
 for t in toks:
  if t in CONCRETE or t.rstrip('s') in CONCRETE:
   if t not in concrete: concrete.append(t)
 if concrete: return ' '.join(concrete[:4])
 meaningful=[t for t in toks if len(t)>4]
 return ' '.join(meaningful[:4]) or 'old building exterior'

def score(text):
 low=text.lower(); toks=set(re.findall(r'[a-z]+',low)); s=min(5,len(toks&CONCRETE))+min(4,len(toks&DRAMA))+min(3,len(toks&VERBS))
 if re.search(r'\b(suddenly|inside|behind|under|that night|next morning|then you|before you|when you|three months later)\b',low): s+=2
 if re.search(r'\b(\d{1,2}:\d{2}|room \d+|\d{4}|next friday)\b',low): s+=1
 return s

def split_beats(text):
 ss=re.split(r'(?<=[.!?])\s+',re.sub(r'\s+',' ',text.strip())); out=[]; cur=[]; count=0; start=0; total=0
 for sentence in ss:
  wc=len(words(sentence))
  if cur and count+wc>42:
   out.append({'text':' '.join(cur),'start_word':start,'word_count':count}); start=total; cur=[]; count=0
  cur.append(sentence); count+=wc; total+=wc
  if count>=28:
   out.append({'text':' '.join(cur),'start_word':start,'word_count':count}); start=total; cur=[]; count=0
 if cur: out.append({'text':' '.join(cur),'start_word':start,'word_count':count})
 return out

async def narrate(text,audio,event_file):
 events=[]; c=edge_tts.Communicate(text,'en-US-GuyNeural',rate='+11%')
 with open(audio,'wb') as f:
  async for chunk in c.stream():
   if chunk['type']=='audio': f.write(chunk['data'])
   elif chunk['type']=='WordBoundary': events.append({'text':chunk.get('text',''),'start':chunk.get('offset',0)/10000000,'duration':chunk.get('duration',0)/10000000})
 event_file.write_text(json.dumps(events,indent=2)); return events

def fallback_events(text,duration):
 toks=words(text); weights=[max(.7,min(2.1,.55+len(w)*.12)) for w in toks]; total=sum(weights) or 1; t=0; out=[]
 for w,x in zip(toks,weights):
  d=duration*x/total; out.append({'text':w,'start':t,'duration':d}); t+=d
 return out

def fallback_tts(text,audio):
 wav=TMP/'fallback.wav'; run(['espeak-ng','-v','en-us+m3','-s','190','-w',str(wav),text]); run(['ffmpeg','-y','-loglevel','error','-i',str(wav),'-c:a','libmp3lame','-b:a','144k',str(audio)]); return fallback_events(text,media_duration(audio))

def time_beats(beats,events,duration):
 total=max(1,sum(b['word_count'] for b in beats)); n=len(events)
 for b in beats:
  sf=b['start_word']/total; ef=(b['start_word']+b['word_count'])/total
  if n:
   a=min(n-1,max(0,round(sf*(n-1)))); z=min(n-1,max(0,round(ef*(n-1)))); b['start']=float(events[a]['start']); b['end']=min(duration,float(events[z]['start'])+max(.1,float(events[z].get('duration',.1))))
  else: b['start']=duration*sf; b['end']=duration*ef
  b['score']=score(b['text']); b['query']=visual_query(b['text'])
 return beats

def select_visuals(beats,duration):
 selected=[]; last=-999
 for idx,b in enumerate(beats):
  gap=b['start']-last; pick=idx==0 or gap>=STYLE['visual_max_gap'] or (gap>=STYLE['visual_min_gap'] and b['score']>=4)
  if not pick: continue
  hold=min(STYLE['visual_hold'][1],max(STYLE['visual_hold'][0],b['end']-b['start']+1.4)); hold=min(hold,max(0,duration-b['start']-.15))
  if hold<3.2: continue
  selected.append({'start':b['start'],'end':b['start']+hold,'duration':hold,'query':b['query'],'score':b['score'],'beat_text':b['text']}); last=b['start']
 desired=max(8,min(24,int(duration/24)))
 if len(selected)<desired:
  candidates=sorted((b for b in beats if all(abs(b['start']-v['start'])>=5.8 for v in selected)),key=lambda b:(-b['score'],b['start']))
  for b in candidates:
   hold=min(STYLE['visual_hold'][1],max(STYLE['visual_hold'][0],b['end']-b['start']+1.2)); hold=min(hold,max(0,duration-b['start']-.1))
   if hold<3.2: continue
   selected.append({'start':b['start'],'end':b['start']+hold,'duration':hold,'query':b['query'],'score':b['score'],'beat_text':b['text']})
   if len(selected)>=desired: break
  selected.sort(key=lambda v:v['start'])
 clean=[]
 for v in selected:
  if clean and v['start']<clean[-1]['end']+.8:
   if v['score']>clean[-1]['score']: clean[-1]=v
   continue
  clean.append(v)
 return clean[:26]

def gateway_story(seed):
 token=str(os.getenv('AI_GATEWAY_API_KEY','') or os.getenv('VERCEL_OIDC_TOKEN','')).strip()
 if not token: return None
 prompt=f'''Write an ORIGINAL second-person suspense or mystery story for a vertical social storytime video. Return JSON only with keys title and story. Story length 850-1150 words. It must be intricate but easy to follow, with a strong first-sentence hook, concrete physical locations and objects that can be illustrated, escalating discoveries, a coherent explanation or twist, and a satisfying ending. Plain natural narration, not dialogue-heavy prose. Do not copy internet stories or use copyrighted characters. No filler or repeated lines. Random seed {seed}.'''
 body=json.dumps({'model':os.getenv('AI_STORY_MODEL','openai/gpt-5.6-sol'),'messages':[{'role':'system','content':'You write original cinematic storytime scripts and return strict JSON.'},{'role':'user','content':prompt}],'temperature':.93,'max_tokens':2200}).encode()
 req=urllib.request.Request('https://ai-gateway.vercel.sh/v1/chat/completions',data=body,method='POST',headers={'Authorization':'Bearer '+token,'Content-Type':'application/json','User-Agent':'RubysRealmStoryRenderer/2.0'})
 try:
  with urllib.request.urlopen(req,timeout=90) as r: data=json.loads(r.read().decode())
  raw=str(data['choices'][0]['message']['content']).strip(); raw=re.sub(r'^```(?:json)?\s*|\s*```$','',raw,flags=re.I|re.S).strip(); parsed=json.loads(raw); story=str(parsed.get('story','')).strip(); title=str(parsed.get('title',"Ruby's Realm Story")).strip()[:80]
  if 650<=len(words(story))<=1450: return {'title':title,'part':'Part 1','story':story,'source':'ai-gateway'}
 except Exception as e: print('AI story generation unavailable:',e,file=sys.stderr)
 return None

def choose_story(seed):
 supplied=os.getenv('STORY_TEXT','').strip()
 if supplied: return {'title':os.getenv('STORY_TITLE',"Ruby's Realm Story").strip() or "Ruby's Realm Story",'part':os.getenv('STORY_PART','Part 1').strip() or 'Part 1','story':supplied,'source':'supplied'}
 generated=gateway_story(seed)
 if generated: return generated
 title,story=STORY_BANK[seed%len(STORY_BANK)]; return {'title':title,'part':'Part 1','story':story,'source':'original-built-in'}

def prepare_visuals(visuals,seed):
 source_count=0
 for i,v in enumerate(visuals):
  photo=TMP/f'photo_{i:02d}.jpg'; source=fetch_photo(v['query'],seed+i*271,photo); v['source']=source
  if source.get('source_type')=='wikimedia-public-domain': v['photo']=photo; source_count+=1
  else: v['photo']=None
 real=[i for i,v in enumerate(visuals) if v.get('photo')]
 if real:
  for i,v in enumerate(visuals):
   if v.get('photo'): continue
   nearest=min(real,key=lambda j:abs(j-i)); v['photo']=visuals[nearest]['photo']; v['source']['source_type']='reused-nearest-context-photo'; v['source']['reused_from']=nearest
 return source_count

def main():
 for p in TMP.glob('*'):
  p.unlink() if p.is_file() else shutil.rmtree(p,ignore_errors=True)
 for p in OUT.glob('*'):
  p.unlink() if p.is_file() else shutil.rmtree(p,ignore_errors=True)
 seed=int(os.getenv('STORY_SEED',str(random.randint(10000,999999)))); info=choose_story(seed); title=info['title']; part=info.get('part','Part 1'); story=info['story']
 audio=TMP/'narration.mp3'; events_file=TMP/'word-boundaries.json'
 try:
  events=asyncio.run(narrate(story,audio,events_file))
  if len(events)<100: raise RuntimeError('insufficient word boundaries')
 except Exception as e:
  print('Edge narration fallback:',e,file=sys.stderr); events=fallback_tts(story,audio); events_file.write_text(json.dumps(events,indent=2))
 duration=media_duration(audio)
 if not STYLE['hard_duration'][0]<=duration<=STYLE['hard_duration'][1]: raise RuntimeError(f'narration duration {duration:.1f}s outside 2-9 minute range')
 cues=caption_cues(story,events); beats=time_beats(split_beats(story),events,duration); visuals=select_visuals(beats,duration); source_count=prepare_visuals(visuals,seed)
 if not visuals or not any(v.get('photo') for v in visuals): raise RuntimeError('No legitimate photographic visuals found; refusing placeholder fallback')
 baseline=next(v['photo'] for v in visuals if v.get('photo')); base=TMP/'base.jpg'; compose_frame(title,part,baseline,seed,base,False); ass=TMP/'captions.ass'; write_ass(cues,ass); name=f'{safe_name(title)}-{seed}'; video=OUT/f'{name}.mp4'; render(base,visuals,audio,ass,duration,video,title,part,seed,TMP)
 actual,cov,gaps,ratio,checks,passed=verify(video,cues,visuals,duration,source_count)
 manifest={'renderer':STYLE['renderer'],'qualityGate':STYLE['quality_gate'],'qualityPassed':passed,'title':title,'part':part,'storySource':info.get('source'),'file':video.name,'durationSeconds':round(actual,3),'narrationSeconds':round(duration,3),'captionCueCount':len(cues),'captionMaxWords':max((c['words'] for c in cues),default=0),'visualInsertCount':len(visuals),'visualCoverageRatio':round(cov,4),'photoSourceRatio':round(ratio,4),'visualMedianDuration':round(sorted(v['duration'] for v in visuals)[len(visuals)//2],3),'visualMaxGap':round(max(gaps),3) if gaps else None,'style':STYLE,'checks':checks,'visuals':[{'start':round(v['start'],3),'end':round(v['end'],3),'duration':round(v['duration'],3),'query':v['query'],'score':v['score'],'source':v.get('source')} for v in visuals]}
 (OUT/f'{name}.json').write_text(json.dumps(manifest,indent=2))
 if not passed:
  print(json.dumps(manifest,indent=2),file=sys.stderr); raise RuntimeError('Reference v2 quality gate failed; refusing to publish')
 print(video)

if __name__=='__main__': main()