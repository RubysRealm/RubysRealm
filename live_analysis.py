"""Publish per-round paper results so browser lookbacks can roll every second."""
import datetime as dt
import json
from decimal import Decimal
from pathlib import Path
import time
import numpy as np
from analyze import prepare_round, top_configurations, TP, SL, CAPS

_cache = {}

def rank_summary(items, start, now, limit=1, expected=None):
    selected=[r for r in items if not r.get('excluded')]
    reasons={}
    for r in items:
        if r.get('excluded'):reasons[r['excluded']]=reasons.get(r['excluded'],0)+1
    if expected is None:expected=max(0,int(now//900)-int(np.ceil(start/900)))
    out={'start':start,'end':now,'elapsed_ready':True,'observed_rounds':len(items),
        'expected_rounds':expected,'missing_rounds':max(0,expected-len(items)),
        'included_call_opportunities':len(selected),'excluded':reasons,'top_setups':[],'best':None}
    out['status']='partial_sample' if out['missing_rounds'] or any(k!='sitout' for k in reasons) else 'complete_observed_call_sample'
    if not selected:return out
    n=len(TP)*len(SL)
    receipts=np.zeros((100,n),dtype=np.int64);spends=np.zeros(100,dtype=np.int64);counts=np.zeros(100,dtype=int)
    for t in selected:
        cap=max(0,int(np.ceil(t['price']*100-1e-10))-1)
        receipts[cap]+=t['returned_units'];spends[cap]+=t['spent_units'];counts[cap]+=1
    receipts=np.cumsum(receipts,axis=0);spends=np.cumsum(spends);counts=np.cumsum(counts)
    profit=receipts-spends[:,None]
    for config in top_configurations(profit.reshape((100,len(TP),len(SL))),counts,limit=limit):
        cap,pi,si=config['indices'];j=pi*len(SL)+si
        chosen=[t for t in selected if CAPS[cap] is None or t['price']<=CAPS[cap]/100+1e-10]
        win=sum(t['returned_units'][j]>t['spent_units'] for t in chosen)
        lose=sum(t['returned_units'][j]<t['spent_units'] for t in chosen)
        result={'rank':config['rank'],'tied_configurations':config['tied_configurations'],
            'max_buy_cents':CAPS[cap],'take_profit_gain_pct':TP[pi],'stop_loss_pct':SL[si],
            'purchases':int(counts[cap]),'profitable_purchases':win,'losing_purchases':lose,
            'break_even_purchases':int(counts[cap])-win-lose,'spent':float(spends[cap])/10000,
            'returned':float(receipts[cap,j])/10000,'net_profit':float(profit[cap,j])/10000,
            'roi_pct':float(profit[cap,j]/spends[cap]*100),'beats_no_trade':bool(profit[cap,j]>0)}
        out['top_setups'].append(result)
    out['best']=out['top_setups'][0]
    return out

def recent_beneficial(periods, previous, now):
    """Remember newly profitable top-five controls; don't duplicate each refresh."""
    old_active=set(previous.get('beneficial_active_keys',[]))
    history=list(previous.get('recent_beneficial',[]))
    candidates={}
    for p in periods:
        for setup in p['top_setups']:
            if setup['net_profit']<=0:continue
            key=json.dumps([setup['max_buy_cents'],setup['take_profit_gain_pct'],setup['stop_loss_pct']])
            item={**setup,'key':key,'lookback_hours':p['hours'],'start':p['start'],'end':p['end'],'identified_at':now}
            if key not in candidates or item['net_profit']>candidates[key]['net_profit']:
                candidates[key]=item
    new=[item for key,item in candidates.items() if key not in old_active]
    new.sort(key=lambda item:(-item['net_profit'],item['key']))
    new_keys={item['key'] for item in new}
    history=new+[item for item in history if item['key'] not in new_keys]
    return history[:5],list(candidates)

def build_input(root, state, now=None):
    now = time.time() if now is None else now
    root = Path(root)
    rounds = []
    active = set()
    for r in sorted(state["rounds"].values(), key=lambda r:r["close_ts"]):
        if r["open_ts"] < state["study_start"] or r["close_ts"] > now:
            continue
        key = (str(root), r["ticker"])
        active.add(key)
        # Recheck exclusions; a delayed settlement/fee/path may become available.
        # Valid complete paths are immutable after closure, except revisions.
        identity = (r.get("call_revised", False), str(r.get("call")),
                    str(r.get("official", {}).get("market", {}).get("result")),
                    str(r.get("fee_observation")), r.get("samples"))
        cached = _cache.get(key)
        if cached and cached[0] == identity:
            item = cached[1]
        else:
            trade, reason = prepare_round(r, root, Decimal("1"))
            item = {"ticker":r["ticker"], "open_ts":r["open_ts"], "close_ts":r["close_ts"]}
            if trade is None:
                item["excluded"] = reason
            else:
                item.update(price=trade["price"], spent_units=round(trade["spent"]*10000),
                    returned_units=np.rint(trade["returned"].ravel()*10000).astype(int).tolist())
                _cache[key] = (identity, item)
        rounds.append(item)
    for key in list(_cache):
        if key not in active:
            del _cache[key]
    periods=[]
    for h in (12,24,36):
        if now-state['study_start']<h*3600:continue
        p=rank_summary([r for r in rounds if r['close_ts']>now-h*3600],now-h*3600,now,limit=5,expected=h*4)
        p['hours']=h;periods.append(p)
    previous={}
    prior=root/'reports/rolling.json'
    if prior.exists():previous=json.loads(prior.read_text())
    history,active=recent_beneficial(periods,previous,now)
    return {"schema_version":1, "mode":"rolling", "generated_at":dt.datetime.now(dt.timezone.utc).isoformat(),
        "as_of":now, "study_start":state["study_start"], "last_observation":state.get("last_observation"),
        "settlements_through":max((r["close_ts"] for r in state["rounds"].values()
            if r["close_ts"]<=now and r.get("official",{}).get("market",{}).get("status")=="finalized"),default=None),
        "period_hours":[12,24,36], "caps":CAPS, "take_profit":TP, "stop_loss":SL,
        "money_scale":10000, "all_time":rank_summary(rounds,state['study_start'],now),
        "recent_beneficial":history,"beneficial_active_keys":active,
        "rounds":[r for r in rounds if r['close_ts']>now-37*3600]}
