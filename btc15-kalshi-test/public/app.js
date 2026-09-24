
const KEY='kalshi_test_history';
const MODEL_KEY='kalshi_test_model';
const SHADOW_KEY='kalshi_test_shadow';
const VERIFY_VERSION=3;
const LOCK_AFTER_SEC=55;
const MAX_VALUE_ENTRY=.67;
const ENTRY_WINDOW_END_SEC=60;

const BASE_W={
  momentum:.10, trend:.07, mean_reversion:.04, ptb_time:.62,
  market:.05, book:.035, flow:.035, cross:.015, research:0
};
const LIMITS={
  momentum:[-.05,.28], trend:[-.05,.24], mean_reversion:[-.08,.18],
  ptb_time:[.25,1.10], market:[-.05,.18], book:[-.08,.14],
  flow:[-.08,.14], cross:[-.05,.10], research:[-.06,.06]
};

let last=null,busy=false,forceAfter=false,seenContract=null,priceStream=null;
let livePrice=null,liveAt=0,liveBrti=null,liveSpread=null,liveVenues=[],liveSpot=null,liveExchange=null;

const el=id=>document.getElementById(id);
const clamp=(x,a,b)=>Math.max(a,Math.min(b,x));
const money=x=>Number.isFinite(Number(x))?'$'+Number(x).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2}):'—';
const tm=s=>{s=Math.max(0,Math.floor(s));return String(Math.floor(s/60)).padStart(2,'0')+':'+String(s%60).padStart(2,'0')};

function loadHistory(){try{return JSON.parse(localStorage.getItem(KEY)||'[]')}catch{return[]}}
function saveHistory(a){localStorage.setItem(KEY,JSON.stringify(a.slice(-200)))}
function loadShadow(){try{return JSON.parse(localStorage.getItem(SHADOW_KEY)||'[]')}catch{return[]}}
function saveShadow(a){localStorage.setItem(SHADOW_KEY,JSON.stringify(a.slice(-800)))}
function freshModel(){return{version:1,active:false,weights:{...BASE_W},verified_rounds:0,evals:[],rollback_count:0,last_update:null}}
function loadModel(){
  try{
    const m=JSON.parse(localStorage.getItem(MODEL_KEY)||'null');
    if(!m||!m.weights)return freshModel();
    m.weights={...BASE_W,...m.weights};m.evals=Array.isArray(m.evals)?m.evals:[];
    return m;
  }catch{return freshModel()}
}
function saveModel(m){localStorage.setItem(MODEL_KEY,JSON.stringify(m))}

function activePrice(s){
  return Number.isFinite(livePrice)&&Date.now()-liveAt<5000?livePrice:Number(s.spot.price);
}
function regimeScore(sig,w,dist){
  dist=Math.abs(Number(dist)||0);
  const ptb=Number(sig?.ptb_time)||0;
  let tech=0;
  for(const k of Object.keys(BASE_W)){
    if(k==='ptb_time')continue;
    const x=Number(sig?.[k]),wk=Number(w?.[k]);
    if(Number.isFinite(x)&&Number.isFinite(wk))tech+=wk*x;
  }
  const pw=Number(w.ptb_time)||0;
  if(dist>=100)return pw*ptb*1.35+tech*.20;
  if(dist>=50)return pw*ptb*1.15+tech*.50;
  if(dist>=25)return pw*ptb*.90+tech*.85;
  return pw*ptb*.70+tech;
}
const pickSide=score=>score>=0?'OVER':'UNDER';
const strength=score=>Math.round(clamp(50+Math.tanh(Math.abs(score))*24,50,74));

function decision(s){
  const m=loadModel(),p=activePrice(s),dist=Math.abs(p-Number(s.market.price_to_beat));
  const baseScore=regimeScore(s.prediction.signals,BASE_W,dist);
  const adaptiveScore=regimeScore(s.prediction.signals,m.weights,dist);
  const basePick=pickSide(baseScore),adaptivePick=pickSide(adaptiveScore);
  const use=m.active,score=use?adaptiveScore:baseScore;
  return{
    pick:use?adaptivePick:basePick,score,confidence:strength(score),
    base_pick:basePick,adaptive_pick:adaptivePick,base_score:baseScore,
    adaptive_score:adaptiveScore,model_version:m.version,adaptive_active:use,
    distance_abs:dist
  };
}

function captureShadow(s){
  const elapsed=(Date.now()-Date.parse(s.market.start_utc))/1000;
  if(elapsed<0)return;
  const a=loadShadow(),marks=[15,30,45,55];
  for(const second of marks){
    if(elapsed<second)continue;
    if(a.some(x=>x.contract_id===s.market.contract_id&&x.second===second))continue;
    const d=decision(s),p=activePrice(s);
    a.push({
      contract_id:s.market.contract_id,second,time:new Date().toISOString(),
      pick:d.pick,score:d.score,price:p,ptb:s.market.price_to_beat,
      distance:p-s.market.price_to_beat,yes_ask:s.market.yes_ask,no_ask:s.market.no_ask,
      signals:s.prediction.signals,actual:null
    });
  }
  saveShadow(a);
}

function lockIfReady(s){
  const h=loadHistory();
  let row=h.find(x=>x.contract_id===s.market.contract_id);
  if(row)return row;
  const elapsed=(Date.now()-Date.parse(s.market.start_utc))/1000;
  if(elapsed<LOCK_AFTER_SEC)return null;
  if(elapsed>ENTRY_WINDOW_END_SEC){
      const d=decision(s),p=activePrice(s);
      const entry=d.pick==='OVER'?(s.market.yes_ask??s.market.yes_mid):(s.market.no_ask??s.market.no_mid);
      row={
        contract_id:s.market.contract_id,pick:d.pick,locked_at:new Date().toISOString(),
        lock_elapsed_sec:elapsed,entry_price:entry,yes_ask:s.market.yes_ask,no_ask:s.market.no_ask,
        ptb:s.market.price_to_beat,btc:p,distance_abs:Math.abs(p-s.market.price_to_beat),
        signals:s.prediction.signals,confidence:d.confidence,score:d.score,
        base_pick:d.base_pick,adaptive_pick:d.adaptive_pick,model_version:d.model_version,
        adaptive_active:d.adaptive_active,outcome:'PENDING',verified:false,
        verification_version:null,trained:true,early150:false,theoretical_spent:0,
        value_entry:false,late_test:true
      };
      h.push(row);saveHistory(h);return row;
    }

  const d=decision(s),p=activePrice(s);
  const entry=d.pick==='OVER'?(s.market.yes_ask??s.market.yes_mid):(s.market.no_ask??s.market.no_mid);
  const valueEntry=Number.isFinite(Number(entry))&&Number(entry)<=MAX_VALUE_ENTRY;
  row={
    contract_id:s.market.contract_id,pick:d.pick,locked_at:new Date().toISOString(),
    lock_elapsed_sec:elapsed,
    entry_price:entry,
    yes_ask:s.market.yes_ask,no_ask:s.market.no_ask,ptb:s.market.price_to_beat,
    btc:p,distance_abs:Math.abs(p-s.market.price_to_beat),signals:s.prediction.signals,
    confidence:d.confidence,score:d.score,base_pick:d.base_pick,adaptive_pick:d.adaptive_pick,
    model_version:d.model_version,adaptive_active:d.adaptive_active,
    outcome:'PENDING',verified:false,verification_version:null,trained:false,early150:false,
    theoretical_spent:valueEntry?1:0,value_entry:valueEntry
  };
  h.push(row);saveHistory(h);return row;
}

function theoreticalPnl(row,pick,actual){
  const px=pick==='OVER'?Number(row.yes_ask):Number(row.no_ask);
  if(!Number.isFinite(px)||px<=0||px>1)return null;
  return pick===actual?(1/px)-1:-1;
}
function train(row){
  if(row.trained||row.late_test||!row.verified||row.verification_version!==VERIFY_VERSION||!row.signals)return;
  const m=loadModel(),actual=row.actual,y=actual==='OVER'?1:0;
  const base=row.base_pick||pickSide(regimeScore(row.signals,BASE_W,row.distance_abs));
  const adaptive=row.adaptive_pick||pickSide(regimeScore(row.signals,m.weights,row.distance_abs));
  const bp=theoreticalPnl(row,base,actual),ap=theoreticalPnl(row,adaptive,actual);
  m.evals.push({contract_id:row.contract_id,base_correct:+(base===actual),adaptive_correct:+(adaptive===actual),base_pnl:bp,adaptive_pnl:ap});
  m.evals=m.evals.slice(-50);

  const cur=regimeScore(row.signals,m.weights,row.distance_abs);
  const prob=1/(1+Math.exp(-2*cur)),err=y-prob,lr=.008;
  for(const k of Object.keys(BASE_W)){
    const x=Number(row.signals[k]);if(!Number.isFinite(x))continue;
    let w=Number(m.weights[k]);if(!Number.isFinite(w))w=BASE_W[k];
    w=w*.998+BASE_W[k]*.002+lr*err*x;
    const lim=LIMITS[k];m.weights[k]=clamp(w,lim[0],lim[1]);
  }

  m.verified_rounds=(m.verified_rounds||0)+1;
  m.version=(m.version||1)+1;m.last_update=new Date().toISOString();

  const recent=m.evals.slice(-30),n=recent.length;
  if(n>=20){
    const ba=recent.reduce((a,e)=>a+e.base_correct,0)/n;
    const aa=recent.reduce((a,e)=>a+e.adaptive_correct,0)/n;
    const bpl=recent.reduce((a,e)=>a+(Number.isFinite(e.base_pnl)?e.base_pnl:0),0);
    const apl=recent.reduce((a,e)=>a+(Number.isFinite(e.adaptive_pnl)?e.adaptive_pnl:0),0);
    if(!m.active&&(aa>=ba+.02||(aa>=ba&&apl>bpl+.10)))m.active=true;
    else if(m.active&&aa+.03<ba&&apl<bpl){
      m.active=false;m.rollback_count=(m.rollback_count||0)+1;
      for(const k of Object.keys(BASE_W))m.weights[k]=(Number(m.weights[k])+BASE_W[k])/2;
    }
  }
  saveModel(m);row.trained=true;row.training_version=m.version;
}

async function verifyHistory(currentTicker){
  const h=loadHistory();
  const now=Date.now();const todo=h.filter(x=>!(x.verified&&x.verification_version===VERIFY_VERSION)&&((x.contract_id!==currentTicker)||((Number(x.lock_elapsed_sec)||0)>=0&&last&&Date.parse(last.market.end_utc)<=now))).slice(0,12);
  if(!todo.length)return;
  const results=await Promise.all(todo.map(async row=>{
    try{
      const r=await fetch('/api/verify?ticker='+encodeURIComponent(row.contract_id)+'&ts='+Date.now(),{cache:'no-store'});
      return{row,j:await r.json()};
    }catch(e){return{row,j:{verified:false,state:'VERIFYING',reason:String(e.message||e)}}}
  }));
  const shadows=loadShadow();
  for(const {row,j} of results){
    row.verification_version=VERIFY_VERSION;row.verification_checked_at=new Date().toISOString();
    row.verification_reason=j.reason||'Verification unavailable';
    if(j.verified===true&&j.actual){
      row.actual=j.actual;row.settlement_value=j.settlement_value;row.settlement_ts=j.settlement_ts;
      row.official_ptb=j.price_to_beat;row.outcome=j.actual===row.pick?'WIN':'LOSS';
      row.verified=true;row.verification_conflict=false;row.verification_source='KALSHI_DUAL_FINAL+BRTI_MATH';
      row.trained=false;train(row);
      for(const s of shadows)if(s.contract_id===row.contract_id)s.actual=j.actual;
    }else{
      row.verified=false;row.outcome='PENDING';row.verification_conflict=j.state==='CONFLICT';
      row.verification_source=j.state||'VERIFYING';
    }
  }
  saveHistory(h);saveShadow(shadows);renderStats();
}

function track150(s,row){
  if(!row||row.early150)return;
  const ep=Number(row.entry_price);if(!Number.isFinite(ep)||ep<=0)return;
  const mid=row.pick==='OVER'?Number(s.market.yes_mid):Number(s.market.no_mid);
  if(Number.isFinite(mid)&&mid>=ep*1.5){
    const h=loadHistory(),x=h.find(q=>q.contract_id===row.contract_id);
    if(x){x.early150=true;saveHistory(h)}
  }
}

function renderPrice(){
  if(!last)return;
  const p=activePrice(last),ptb=Number(last.market.price_to_beat),d=p-ptb,age=Date.now()-liveAt;
  el('price').textContent=money(p);
  el('dist').textContent=(d>=0?'+':'')+d.toFixed(2)+' '+(d>=0?'above':'below');
  el('cbmeta').textContent=Number.isFinite(livePrice)&&age<5000?'BRTI proxy • '+(age/1000).toFixed(1)+'s • '+(liveVenues.join(' + ')||'feed warming'):'BTC reference fallback';
  el('cbcompare').textContent='Proxy '+money(liveBrti)+' • Coinbase Spot '+money(liveSpot)+' • Advanced '+money(liveExchange)+(Number.isFinite(liveSpread)?' • venue spread $'+liveSpread.toFixed(2):'');
}

function renderStats(){
  const h=loadHistory();
  const settled=h.filter(x=>x.verified&&x.verification_version===VERIFY_VERSION&&(x.outcome==='WIN'||x.outcome==='LOSS'));
  const wins=settled.filter(x=>x.outcome==='WIN').length,losses=settled.length-wins;
  el('wins').textContent=wins;el('losses').textContent=losses;el('wr').textContent=settled.length?(100*wins/settled.length).toFixed(1)+'%':'—';
  el('ew').textContent=settled.filter(x=>x.outcome==='WIN'&&x.early150).length;
  el('el').textContent=settled.filter(x=>x.outcome==='LOSS'&&x.early150).length;

  const spent=h.reduce((a,x)=>a+(Number(x.theoretical_spent)||0),0);
  const earned=settled.reduce((a,x)=>{
    if(x.outcome!=='WIN'||!x.value_entry)return a;
    const p=Number(x.entry_price);return a+(Number.isFinite(p)&&p>0?1/p:0);
  },0);
  const net=earned-spent;
  el('simspent').textContent='$'+spent.toFixed(2);
  el('simearned').textContent='$'+earned.toFixed(2);
  el('simpl').textContent=(net>=0?'+$':'-$')+Math.abs(net).toFixed(2);
  el('simpl').className=net>=0?'win':'loss';

  const m=loadModel(),e=m.evals.slice(-30),n=e.length;
  el('learnmode').textContent=m.active?'ADAPTIVE':'SHADOW';
  el('learnmode').className=m.active?'win':'pending';
  el('learnrounds').textContent=m.verified_rounds||0;el('learnver').textContent=m.version||1;
  if(n){
    const ba=e.reduce((a,x)=>a+x.base_correct,0)/n,aa=e.reduce((a,x)=>a+x.adaptive_correct,0)/n;
    el('learndetail').textContent='Last '+n+': base '+(ba*100).toFixed(1)+'% vs adaptive '+(aa*100).toFixed(1)+'%'+(m.rollback_count?' • rollbacks '+m.rollback_count:'');
  }else el('learndetail').textContent='Learning only from strictly verified Kalshi test rounds.';

  const rows=h.slice(-10).reverse();
  el('history').innerHTML=rows.length?rows.map(x=>{
    const strict=x.verified&&x.verification_version===VERIFY_VERSION;
    const state=x.verification_conflict?'CONFLICT':strict?x.outcome+' ✓':x.late_test?'TEST • VERIFYING':'VERIFYING';
    const cls=x.verification_conflict?'loss':strict?(x.outcome==='WIN'?'win':'loss'):'pending';
    const payout=!x.value_entry?'NO VALUE':strict&&x.outcome==='WIN'&&Number(x.entry_price)>0?'$'+(1/Number(x.entry_price)).toFixed(2):strict?'$0.00':'—';
    return '<div class="hr"><span>'+x.contract_id+'</span><b class="'+(x.pick==='OVER'?'over':'under')+'">'+x.pick+'</b><b class="'+cls+'">'+state+'</b><span>'+payout+'</span></div>';
  }).join(''):'<div class="status">No Kalshi test predictions yet.</div>';
}

function render(s,row){
  last=s;const p=activePrice(s),ptb=Number(s.market.price_to_beat),d=p-ptb;
  const elapsed=(Date.now()-Date.parse(s.market.start_utc))/1000;
  el('price').textContent=money(p);el('ptb').textContent=money(ptb);el('yesask').textContent=Number.isFinite(Number(s.market.yes_ask))?Math.round(Number(s.market.yes_ask)*100)+'¢':'—';el('noask').textContent=Number.isFinite(Number(s.market.no_ask))?Math.round(Number(s.market.no_ask)*100)+'¢':'—';
  el('session').textContent=s.market.contract_id;el('remain').textContent=tm((Date.parse(s.market.end_utc)-Date.now())/1000);
  el('signals').innerHTML=Object.entries(s.prediction.signals).map(([k,v])=>'<div class="sig"><span class="small">'+k.replaceAll('_',' ')+'</span><b>'+v+'</b></div>').join('');
  el('kraken').textContent=s.spot.kraken_price?'Kraken cross-check: '+money(s.spot.kraken_price):'';
  renderPrice();
  const candidate=decision(s);
  const candidateEntry=candidate.pick==='OVER'?(s.market.yes_ask??s.market.yes_mid):(s.market.no_ask??s.market.no_mid);
  el('selentry').textContent=row&&row.entry_price!=null?Math.round(Number(row.entry_price)*100)+'¢':Number.isFinite(Number(candidateEntry))?Math.round(Number(candidateEntry)*100)+'¢':'—';
  if(row&&row.late_test){el('valuestate').textContent='TEST ONLY — not counted';
    el('pick').textContent=row.pick;el('pick').className='pick '+(row.pick==='OVER'?'over':'under');
    el('conf').textContent='MID-ROUND TEST PICK • will still be verified for WIN/LOSS • excluded from $1 P/L';
    el('status').textContent='This pick is saved and will be graded from the official Kalshi settlement. Next round returns to the normal 55-second lock.';
  }else if(!row){
    const cand=decision(s),left=Math.max(0,LOCK_AFTER_SEC-elapsed);
    el('pick').textContent='ANALYZING';el('pick').className='pick';el('valuestate').textContent=Number.isFinite(Number(candidateEntry))?(Number(candidateEntry)<=MAX_VALUE_ENTRY?'Value eligible now':'Above 67¢ cap'):'Waiting for market';
    el('conf').textContent='Current Kalshi candidate: '+cand.pick+' • locks in '+left.toFixed(0)+'s • PTB distance '+money(Math.abs(d));
    el('status').textContent='First-minute analysis • snapshots at 15 / 30 / 45 / 55 sec • $1 sim only enters at 67¢ or cheaper';
  }else{
    el('pick').textContent=row.pick;el('pick').className='pick '+(row.pick==='OVER'?'over':'under');el('valuestate').textContent=row.value_entry?'VALUE ENTRY':'NO VALUE ENTRY';
    el('conf').textContent='Locked '+new Date(row.locked_at).toLocaleTimeString()+' • model v'+row.model_version+' • strength '+row.confidence+'% • '+(row.value_entry?'$1 VALUE ENTRY @ '+Math.round(Number(row.entry_price)*100)+'¢':'NO VALUE ENTRY @ '+Math.round(Number(row.entry_price)*100)+'¢');
    el('status').textContent='Live • OVER '+(s.market.yes_mid!==null?(s.market.yes_mid*100).toFixed(1)+'¢':'—')+' • UNDER '+(s.market.no_mid!==null?(s.market.no_mid*100).toFixed(1)+'¢':'—');
  }
  el('dot').style.background='#32d583';el('feed').textContent='Live';renderStats();
}

async function tick(force=false){
  if(busy){if(force)forceAfter=true;return}
  busy=true;
  try{
    const r=await fetch('/api/state?ts='+Date.now(),{cache:'no-store'}),s=await r.json();
    if(!s.ok)throw Error(s.error||'Live feed error');
    seenContract=s.market.contract_id;captureShadow(s);
    const row=lockIfReady(s);if(row&&!row.late_test)track150(s,row);render(s,row);
    verifyHistory(s.market.contract_id).catch(()=>{});
  }catch(e){
    el('dot').style.background='#ff5a6f';el('feed').textContent='Feed error';el('status').textContent=String(e.message||e);renderStats();
  }finally{
    busy=false;if(forceAfter){forceAfter=false;setTimeout(()=>tick(true),0)}
  }
}

async function watchSession(){
  try{
    const r=await fetch('/api/session?ts='+Date.now(),{cache:'no-store'}),j=await r.json(),m=j.market;
    if(!m?.contract_id)return;
    if(seenContract&&m.contract_id!==seenContract){
      seenContract=m.contract_id;
      el('session').textContent=m.contract_id;el('ptb').textContent=money(m.price_to_beat);
      el('pick').textContent='ANALYZING';el('pick').className='pick';
      el('conf').textContent='New round • first-minute analysis • lock by 0:55';
      tick(true);
    }else if(!seenContract)seenContract=m.contract_id;
  }catch{}
}

function connectPrice(){
  try{
    if(priceStream)priceStream.close();
    priceStream=new EventSource('/api/price-stream');
    priceStream.onmessage=e=>{
      try{
        const m=JSON.parse(e.data),p=Number(m.price);
        liveBrti=Number(m.brti_proxy);liveSpread=Number(m.brti_spread);
        liveVenues=Array.isArray(m.venues)?m.venues:[];
        liveSpot=Number(m.spot_price);liveExchange=Number(m.exchange_price);
        if(!Number.isFinite(liveBrti))liveBrti=null;if(!Number.isFinite(liveSpread))liveSpread=null;
        if(!Number.isFinite(liveSpot))liveSpot=null;if(!Number.isFinite(liveExchange))liveExchange=null;
        if(Number.isFinite(p)){livePrice=p;liveAt=Date.now();renderPrice()}
      }catch{}
    };
    priceStream.onerror=()=>{el('cbmeta').textContent='BRTI proxy reconnecting…'};
  }catch{setTimeout(connectPrice,1500)}
}

setInterval(()=>{if(last){el('remain').textContent=tm((Date.parse(last.market.end_utc)-Date.now())/1000);renderPrice()}},250);
setInterval(()=>tick(false),1500);
setInterval(watchSession,750);
setInterval(()=>verifyHistory(seenContract).catch(()=>{}),10000);
connectPrice();watchSession();tick(true);renderStats();
