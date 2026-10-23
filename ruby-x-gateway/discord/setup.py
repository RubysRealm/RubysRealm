"""Idempotent, owner-authorized Ruby's X Discord makeover. Token stays outside git."""
import json, pathlib, os, time, base64, urllib.parse, urllib.request, urllib.error
ROOT=pathlib.Path(__file__).resolve().parents[1]
GUILD='1372700795878899845'
APP='1563285254918115348'
SITE='https://ruby-x-terminal.onrender.com'
STATE=ROOT/'discord/setup-state.json'
state=json.loads(STATE.read_text()) if STATE.exists() else {'messages':{},'channels':{},'roles':{}}
headers={'Authorization':'Bot '+pathlib.Path(os.environ.get('DISCORD_TOKEN_FILE','/workspace/scratch/.ruby-discord-token')).read_text().strip(),'User-Agent':'RubyXSetup/1.0','X-Audit-Log-Reason':urllib.parse.quote('Owner-authorized Ruby X server makeover')}
def save(): STATE.write_text(json.dumps(state,indent=2,ensure_ascii=False)+'\n')
def api(method,path,data=None):
 for attempt in range(4):
  body=json.dumps(data).encode() if data is not None else None
  request=urllib.request.Request('https://discord.com/api/v10'+path,data=body,method=method,headers={**headers,'Content-Type':'application/json'})
  try:
   with urllib.request.urlopen(request,timeout=30) as r:
    raw=r.read();return json.loads(raw) if raw else None
  except urllib.error.HTTPError as e:
   raw=e.read().decode()
   if e.code==429:
    delay=float(json.loads(raw).get('retry_after',1))
    if delay>45:raise RuntimeError('Discord rate limit; resume later')
    time.sleep(delay+.2);continue
   raise RuntimeError(f'{method} {path}: {e.code} {raw[:600]}') from None
 raise RuntimeError('Rate limit retries exhausted')
def img(name):return 'data:image/png;base64,'+base64.b64encode((ROOT/'public/discord'/name).read_bytes()).decode()
def message(key,channel,embed,components=None):
 payload={'embeds':[embed],'allowed_mentions':{'parse':[]},'components':components or []}
 if key in state['messages']:api('PATCH',f"/channels/{channel}/messages/{state['messages'][key]}",payload)
 else:
  payload.update(nonce=str(int.from_bytes(key.encode(),'big'))[-24:],enforce_nonce=True)
  result=api('POST',f'/channels/{channel}/messages',payload);state['messages'][key]=result['id'];save()
 print('Message ready:',key,flush=True)
def run():
 guild=api('GET',f'/guilds/{GUILD}')
 if guild['name'] not in ["Ruby's Secret Realm","Ruby’s X","Ruby's X"]:raise RuntimeError('Unexpected server; stopped')
 if not state.get('branded'):
  api('PATCH',f'/guilds/{GUILD}',{'name':'Ruby’s X','icon':img('ruby-x-icon.png')})
  api('PATCH','/users/@me',{'avatar':img('ruby-x-icon.png')})
  state['branded']=True;save();print('Server name and artwork applied',flush=True)
 roles=api('GET',f'/guilds/{GUILD}/roles')
 for key,name,color in [('member','💎 Inner Circle',0xe92963),('new','🌱 New Arrival',0x99aabb),('BTC','₿ Bitcoin',0xffb347),('ETH','Ξ Ethereum',0x9b7aff),('XRP','✕ XRP',0x27d8f2),('SOL','◎ Solana',0x35e8a3)]:
  found=next((r for r in roles if r['name']==name),None)
  if not found:found=api('POST',f'/guilds/{GUILD}/roles',{'name':name,'permissions':'0','colors':{'primary_color':color},'hoist':key=='member','mentionable':False})
  state['roles'][key]=found['id'];save()
 print('Six community roles ready',flush=True)
 channels=api('GET',f'/guilds/{GUILD}/channels')
 def channel(key,name,typ,parent=None,existing=None,topic=None,readonly=False):
  found=next((c for c in channels if c['id']==state['channels'].get(key) or c['id']==existing or c['name']==name),None)
  body={'name':name,'type':typ}
  if parent:body['parent_id']=state['channels'][parent]
  if topic:body['topic']=topic
  if readonly:body['permission_overwrites']=[{'id':GUILD,'type':0,'deny':'2048','allow':'0'},{'id':APP,'type':1,'allow':'3072','deny':'0'}]
  if found: result=api('PATCH','/channels/'+found['id'],body)
  else:result=api('POST',f'/guilds/{GUILD}/channels',body)
  state['channels'][key]=result['id'];save();print('Channel ready:',name,flush=True)
 channel('entry','◆ START HERE',4)
 channel('live','◈ LIVE TERMINALS',4)
 channel('community','✦ THE INNER CIRCLE',4,existing='1372700795878899846')
 channel('voice','◉ AFTER HOURS',4,existing='1372700795878899847')
 for key,name,parent,topic,ro,old in [
 ('welcome','👋│arrival','entry','Welcome to Ruby’s X. Start here, meet the community, then pick your market.',True,None),
 ('rules','📜│house-rules','entry','Keep it respectful. No scams, spam, or unsolicited DMs.',True,None),
 ('roles','🎭│pick-your-role','entry','Choose your markets and community role.',True,None),
 ('announcements','📣│broadcasts','entry','Official Ruby’s X updates.',True,None),
 ('BTC','₿│bitcoin','live','BTC live terminal • 15-minute rounds • Discuss the setup, not guarantees.',False,None),
 ('ETH','Ξ│ethereum','live','ETH live terminal • 15-minute rounds • Discuss the setup, not guarantees.',False,None),
 ('XRP','✕│xrp','live','XRP live terminal • 15-minute rounds • Discuss the setup, not guarantees.',False,None),
 ('SOL','◎│solana','live','SOL live terminal • 15-minute rounds • Discuss the setup, not guarantees.',False,None),
 ('lounge','💬│the-lounge','community','Your spot to hang out. Existing general-chat history lives here.',False,'1372700795878899848'),
 ('market','📈│market-talk','community','Market context, news, and observations.',False,None),
 ('setups','🧠│setups','community','Share your thesis, entry, invalidation, and exit plan.',False,None),
 ('wins','🏆│wins-and-lessons','community','Share wins and losses honestly. Show the lesson, not just the screenshot.',False,None)]:channel(key,name,0,parent,old,topic,ro)
 channel('floor','🔊 Trading Floor',2,'voice','1372700795878899849')
 channel('after','🌙 After Hours',2,'voice')
 api('PATCH',f'/guilds/{GUILD}/channels',[{'id':state['channels'][k],'position':i} for i,k in enumerate(['entry','live','community','voice'])])
 api('PATCH',f'/guilds/{GUILD}',{'system_channel_id':state['channels']['welcome']})
 c=state['channels'];color=0xe92963
 message('welcome',c['welcome'],{'title':'RUBY’S X / THE INNER CIRCLE','description':f"Four markets. One place to watch them.\n\n**Start here**\n📜 Read <#{c['rules']}>\n🎭 Pick your colors in <#{c['roles']}>\n📊 Open your market in the **Live Terminals**\n💬 Say what’s up in <#{c['lounge']}>\n\nBring your ideas. Share your reasoning. Respect the risk.",'color':color,'image':{'url':SITE+'/discord/welcome-banner.png'},'footer':{'text':'BTC · ETH · XRP · SOL'}})
 message('rules',c['rules'],{'title':'THE HOUSE RULES','description':'**01 / Respect the room**\nDebate the setup, not the person. No harassment.\n\n**02 / No scams**\nNo unsolicited promotions, paid-signal DMs, impersonation, or wallet requests. Never share private keys or API secrets.\n\n**03 / Keep it real**\nNo guaranteed-profit claims or edited results. Label paper trades and hypothetical setups.\n\n**04 / Own the risk**\nCharts and projections can be wrong. You control every trade.\n\n**05 / Keep channels useful**\nUse the matching market channel, explain your thesis, and avoid spam.','color':color})
 for coin,name in [('BTC','BITCOIN'),('ETH','ETHEREUM'),('XRP','XRP'),('SOL','SOLANA')]:
  message('terminal-'+coin,c[coin],{'title':name+' / LIVE TERMINAL','description':'**Interactive charts, current rounds, levels and call history.**\n\nThe browser terminal is live. The Discord Activity is installed and in testing; Discord limits unverified Activities to the developer and approved testers. In-channel launch is not yet verified.\n\nUse this channel to compare setups and discuss the current round.','color':{'BTC':0xffb347,'ETH':0x9b7aff,'XRP':0x27d8f2,'SOL':0x35e8a3}[coin],'footer':{'text':'Estimates are not guarantees. Check feed freshness before acting.'}},[{'type':1,'components':[{'type':2,'style':5,'label':'Open '+coin+' live chart','url':SITE+'/?asset='+coin}]}])
 message('broadcast',c['announcements'],{'title':'WELCOME TO THE NEW RUBY’S X','description':'The server has a new look: ruby/chrome branding, four market rooms, a community lounge, and voice spaces.\n\nThe live browser terminals are available in each market room. Discord Activity access is still being tested.','color':color})
 save()
 print('MAKEOVER_APPLIED',flush=True)
if __name__=='__main__':run()
