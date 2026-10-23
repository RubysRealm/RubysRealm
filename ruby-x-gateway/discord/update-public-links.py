"""Update only the existing chart and arrival posts; verify Discord's response."""
from setup import *
c=state['channels']
def patch(key,channel,embed,components=None):
 payload={'embeds':[embed],'components':components or [],'allowed_mentions':{'parse':[]}}
 result=api('PATCH',f"/channels/{channel}/messages/{state['messages'][key]}",payload)
 public=json.dumps({'embeds':result['embeds'],'components':result['components']}).lower()
 if 'cody' in public or 'giles' in public:raise RuntimeError('Personal name remains in message')
 if result['id']!=state['messages'][key]:raise RuntimeError('Unexpected message')
 print('Verified public links:',key,flush=True)
for coin,name in [('BTC','BITCOIN'),('ETH','ETHEREUM'),('XRP','XRP'),('SOL','SOLANA')]:
 patch('terminal-'+coin,c[coin],{'title':name+' / LIVE TERMINAL','description':'**Interactive charts, current rounds, levels and call history.**\n\n**Launch in Discord** opens the chart inside Discord.\n\n**Open live chart** opens the shared browser chart. Free browser hosting may take about a minute to wake after inactivity. Always check feed freshness before acting.','color':{'BTC':0xffb347,'ETH':0x9b7aff,'XRP':0x27d8f2,'SOL':0x35e8a3}[coin]},[{'type':1,'components':[{'type':2,'style':1,'label':'Launch in Discord','custom_id':'ruby:launch'},{'type':2,'style':5,'label':'Open '+coin+' live chart','url':SITE+'/?asset='+coin}]}])
patch('welcome',c['welcome'],{'title':'RUBY’S X / THE INNER CIRCLE','description':f"Four markets. One place to watch them.\n\n📜 Read <#{c['rules']}>\n🎭 Pick your market colors in <#{c['roles']}>\n📊 Open your market in the **Live Terminals**\n💬 Say what’s up in <#{c['lounge']}>\n\nBring your ideas. Share your reasoning. Respect the risk.",'color':0xe92963,'image':{'url':SITE+'/discord/welcome-banner.png'},'footer':{'text':'BTC · ETH · XRP · SOL'}})
