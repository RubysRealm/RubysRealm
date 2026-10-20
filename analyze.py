#!/usr/bin/env python3
"""Counterfactual public-call paper results, not Oracle-account returns."""
import argparse
import datetime as dt
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

D = Decimal
TP = [None] + list(range(101))
SL = [None] + list(range(0,101,5))
CAPS = list(range(1,100)) + [None]
EASTERN = ZoneInfo("America/New_York")

def iso(ts):
    return dt.datetime.fromtimestamp(ts,EASTERN).isoformat()

def fee(q,p,multiplier):
    return (D("0.07")*multiplier*q*p*(1-p)).quantize(D("0.000001"),rounding=ROUND_CEILING)

def levels(book, side):
    raw=book.get(side+"_dollars",[]) if book else []
    result=[]
    for p,q in raw:
        p,q=D(str(p)),D(str(q))
        if 0<=p<=1 and q>0:result.append((p,q))
    return sorted(result,reverse=True)

def entry(book,side,budget,multiplier):
    opposite="no" if side=="yes" else "yes"
    offers=levels(book,opposite)
    if not offers:return None
    p=1-offers[0][0]
    if not 0<p<1:return None
    q=min((budget/p).to_integral_value(rounding=ROUND_FLOOR),offers[0][1].to_integral_value(rounding=ROUND_FLOOR))
    if q<1:return None
    spent=(q*p+fee(q,p,multiplier)).quantize(D("0.0001"),rounding=ROUND_CEILING)
    return p,q,spent

def sale(book,side,q,multiplier):
    bids=levels(book,side)
    if not bids:return None
    left=q;gross=D(0);fees=D(0)
    for p,volume in bids:
        fill=min(left,volume)
        gross+=fill*p;fees+=fee(fill,p,multiplier);left-=fill
        if left==0:break
    if left>0:return None
    return (gross-fees).quantize(D("0.0001"),rounding=ROUND_FLOOR)

def crosses_first(values, thresholds, greater):
    # Quotes have finite decimal ticks; avoid binary-float equality moving a trigger.
    test=values[:,None]+1e-12>=thresholds[None,:] if greater else values[:,None]<=thresholds[None,:]+1e-12
    return np.where(test.any(axis=0),test.argmax(axis=0),len(values))

def prepare_round(r,root,budget):
    call=r.get("call") or {}
    if call.get("side")=="SITOUT":return None,"sitout"
    if call.get("side") not in ("UP","DOWN"):return None,"no_locked_call"
    if r.get("call_revised"):return None,"revised_locked_call"
    official=r.get("official",{}).get("market",{})
    if official.get("status")!="finalized" or official.get("result") not in ("yes","no"):
        return None,"unverified_settlement"
    fo=r.get("fee_observation") or {}
    if fo.get("fee_type")!="quadratic" or fo.get("fee_multiplier") is None:
        return None,"unverified_fee_model"
    multiplier=D(str(fo["fee_multiplier"]))
    seal=call.get("sealed_at")
    if not isinstance(seal,(float,int)):return None,"missing_seal_timestamp"
    path=root/"data"/"rounds"/(r["ticker"]+".jsonl")
    if not path.exists():return None,"missing_quotes"
    rows=[json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    usable=[]
    for row in rows:
        bf=row.get("book_fetch") or {};of=row.get("oracle_fetch") or {};w=row.get("window") or {};c=row.get("call") or {}
        bt=bf.get("received_at")
        if not row.get("book") or not isinstance(bt,(int,float)):continue
        if c.get("side")!=call["side"] or not c.get("sealed"):continue
        if not (seal<=bt<r["close_ts"]):continue
        ot=of.get("received_at",row["ts"])
        if bt-ot>10 or ot-of.get("requested_at",ot)>10:continue
        if w.get("secs_left") is None or abs((r["close_ts"]-float(w["secs_left"]))-ot)>15:continue
        usable.append((bt,row))
    usable.sort(key=lambda x:x[0])
    if not usable or usable[0][0]-seal>15:return None,"late_or_missing_entry"
    times=[x[0] for x in usable]
    maxgap=max([b-a for a,b in zip(times,times[1:])]+[r["close_ts"]-times[-1]])
    if maxgap>20:return None,"quote_gap_over_20s"
    side="yes" if call["side"]=="UP" else "no"
    e=entry(usable[0][1]["book"],side,budget,multiplier)
    if not e:return None,"no_affordable_entry_depth"
    price,q,spent=e
    future=usable[1:]
    if not future:return None,"no_exit_observations"
    won=official["result"]==side
    settlement=float(q if won else 0)
    bids=np.array([float(levels(x[1]["book"],side)[0][0]) if levels(x[1]["book"],side) else np.nan for x in future])
    receipts=[]
    for _,row in future:
        net=sale(row["book"],side,q,multiplier)
        receipts.append(float(net) if net is not None else np.nan)
    # At a detected trigger, use the next observed book with enough displayed depth.
    n=len(future);next_value=np.full(n+1,settlement);next_time=np.full(n+1,r["close_ts"])
    value=settlement;exittime=r["close_ts"]
    for i in range(n-1,-1,-1):
        next_value[i]=value;next_time[i]=exittime
        if np.isfinite(receipts[i]):value=receipts[i];exittime=future[i][0]
    take_thresholds=np.array([np.inf if p is None else float(price)*(1+p/100) for p in TP])
    stop_thresholds=np.array([-np.inf if p is None else float(price)*(1-p/100) for p in SL])
    ti=crosses_first(bids,take_thresholds,True)
    si=crosses_first(bids,stop_thresholds,False)
    first=np.minimum(ti[:,None],si[None,:])
    returned=next_value[first]
    return {"ticker":r["ticker"],"open_ts":r["open_ts"],"close_ts":r["close_ts"],"side":call["side"],"entry_at":times[0],"price":float(price),"quantity":int(q),"spent":float(spent),"returned":returned,"profit":returned-float(spent),"exit_at":next_time[first],"settlement_won":won,"max_gap_seconds":maxgap},None

def run(root,budget):
    state=json.loads((root/"state.json").read_text())
    last=min(state.get("last_observation",0),state["study_stop"])
    start=state["study_start"]
    closed_cutoff=math.floor(last/900)*900
    finalized_closes=[r["close_ts"] for r in state["rounds"].values() if r["close_ts"]<=closed_cutoff and r.get("official",{}).get("market",{}).get("status")=="finalized" and r["official"]["market"].get("result") in ("yes","no")]
    # Do not let the most recently closed, still-unsettled round create a spurious gap.
    end=max(finalized_closes,default=min(closed_cutoff,start))
    report={"generated_at":dt.datetime.now(dt.timezone.utc).isoformat(),"study_start":iso(start),"as_of":iso(end),"label":"SAMPLED-QUOTE PAPER SIMULATION — NOT ACTUAL ORACLE RETURNS","stake_contract_cost_dollars":float(budget),"fees_additional":True,"whole_contracts":True,"next_sample_execution":True,"grid_size":len(CAPS)*len(TP)*len(SL),"sampling_limit":"5-second target sampling can miss intrainterval triggers and does not guarantee live fills","periods":[]}
    prepared={};excluded={}
    rounds=[r for r in state["rounds"].values() if r["open_ts"]>=start and r["close_ts"]<=end]
    for r in rounds:
        v,reason=prepare_round(r,root,budget)
        if v:prepared[r["ticker"]]=v
        else:excluded[r["ticker"]]=reason
    for h in (12,24,36):
        out={"hours":h,"start":iso(end-h*3600),"end":iso(end),"elapsed_ready":end-start>=h*3600,"no_trade_profit":0}
        if not out["elapsed_ready"]:
            out["status"]="collecting";report["periods"].append(out);continue
        chosen=[r for r in rounds if r["open_ts"]>=end-h*3600]
        selected=[prepared[r["ticker"]] for r in chosen if r["ticker"] in prepared]
        reasons={}
        for r in chosen:
            reason=excluded.get(r["ticker"])
            if reason:reasons[reason]=reasons.get(reason,0)+1
        out.update(expected_rounds=h*4,observed_rounds=len(chosen),missing_rounds=max(0,h*4-len(chosen)),included_call_opportunities=len(selected),excluded=reasons)
        incomplete=out["missing_rounds"]>0 or any(v for k,v in reasons.items() if k!="sitout")
        out["status"]="partial_sample" if incomplete else "complete_observed_call_sample"
        if not selected:
            out["best"]=None;report["periods"].append(out);continue
        profits=np.zeros((100,len(TP),len(SL)));returned=np.zeros_like(profits);wins=np.zeros_like(profits,dtype=int)
        spends=np.zeros(100);counts=np.zeros(100,dtype=int)
        for t in selected:
            lo=max(0,math.ceil(t["price"]*100-1e-10)-1)
            profits[lo:]+=t["profit"];returned[lo:]+=t["returned"];wins[lo:]+=(t["profit"]>1e-9)
            spends[lo:]+=t["spent"];counts[lo:]+=1
        eligible=np.broadcast_to(counts[:,None,None]>0,profits.shape)
        ranked=np.where(eligible,profits,-np.inf)
        best=float(ranked.max());ties=np.argwhere(np.isclose(ranked,best,rtol=0,atol=1e-7))
        ci,pi,si=map(int,ties[0]);n=int(counts[ci]);spent=float(spends[ci]);got=float(returned[ci,pi,si])
        bestout={"max_buy_cents":CAPS[ci],"take_profit_gain_pct":TP[pi],"stop_loss_pct":SL[si],"purchases":n,"profitable_purchases":int(wins[ci,pi,si]),"losing_purchases":0,"spent":round(spent,6),"returned":round(got,6),"net_profit":round(best,6),"roi_pct":round(best/spent*100,6) if spent else None,"tied_configurations":len(ties),"beats_no_trade":best>0,"trades":[]}
        hours={}
        for t in selected:
            if CAPS[ci] is not None and t["price"]>CAPS[ci]/100+1e-10:continue
            profit=float(t["profit"][pi,si]);bestout["losing_purchases"]+=int(profit< -1e-9)
            tr={k:t[k] for k in ("ticker","side","price","quantity","spent","settlement_won","max_gap_seconds")}
            tr.update(entry_at=iso(t["entry_at"]),exit_at=iso(float(t["exit_at"][pi,si])),returned=round(float(t["returned"][pi,si]),6),net_profit=round(profit,6))
            bestout["trades"].append(tr)
            local=dt.datetime.fromtimestamp(t["entry_at"],EASTERN);key=f"{local.hour//4*4:02d}:00–{local.hour//4*4+4:02d}:00 Eastern"
            bucket=hours.setdefault(key,{"purchases":0,"profitable":0,"net_profit":0.0})
            bucket["purchases"]+=1;bucket["profitable"]+=int(profit>1e-9);bucket["net_profit"]+=profit
        bestout["break_even_purchases"]=n-bestout["profitable_purchases"]-bestout["losing_purchases"]
        out["best"]=bestout;out["exploratory_time_buckets"]=hours
        out["time_bucket_note"]="Descriptive only; at most 1.5 days per window, too little to establish a recurring time-of-day advantage."
        report["periods"].append(out)
    return report

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--data",type=Path,required=True);p.add_argument("--stake",default="1");p.add_argument("--output",type=Path)
    a=p.parse_args();result=run(a.data,D(a.stake));text=json.dumps(result,indent=2,allow_nan=False)+"\n"
    if a.output:a.output.write_text(text)
    else:print(text)
