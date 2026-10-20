#!/usr/bin/env python3
"""Public data only. No trade, account, login, or private Oracle endpoint."""
import argparse
import base64
import concurrent.futures
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import time
import urllib.error
import urllib.parse
import urllib.request

ORACLE = "https://oraclesignals.trade/api/public/live"
KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
DATA_BRANCH = "oracle-public-study-data-20261020"
INTERVAL = 5
STOP = False

def utc(ts=None):
    return dt.datetime.fromtimestamp(time.time() if ts is None else ts, dt.timezone.utc).isoformat()

def compact(x):
    return json.dumps(x, separators=(",", ":"), sort_keys=True, allow_nan=False)

def request_json(url, *, headers=None, method="GET", data=None, timeout=8):
    started = time.time()
    h = {"User-Agent": "OraclePublicPaperStudy/1.0 (read-only research)", "Accept": "application/json", **(headers or {})}
    body = None if data is None else compact(data).encode()
    if body is not None:
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=h, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        result = json.loads(raw)
        meta = {"requested_at": started, "received_at": time.time(), "date": r.headers.get("Date"), "age": r.headers.get("Age"), "sha256": hashlib.sha256(raw).hexdigest()}
    return result, meta

def market(ticker):
    d, meta = request_json(KALSHI + "/markets/" + urllib.parse.quote(ticker, safe=""))
    m = d["market"]
    keys = ("ticker", "status", "result", "open_time", "close_time", "settlement_ts", "expiration_time", "yes_bid_dollars", "yes_ask_dollars", "no_bid_dollars", "no_ask_dollars", "price_level_structure", "price_ranges")
    return {"market": {k:m.get(k) for k in keys}, "fetch":meta}

class Sink:
    def __init__(self, folder, github):
        self.root = Path(folder); self.root.mkdir(parents=True, exist_ok=True)
        self.github = github; self.dirty = set()
        self.repo = os.environ.get("GITHUB_REPOSITORY", "RubysRealm/RubysRealm")
        self.token = os.environ.get("GITHUB_TOKEN") if github else None
        if github and not self.token:
            raise RuntimeError("Hosted checkpoint token is missing; cannot start an uncheckpointed study")
        if github:
            try:
                self.api("/git/ref/heads/"+DATA_BRANCH)
            except urllib.error.HTTPError as e:
                if e.code != 404: raise
                self.api("/git/refs", "POST", {"ref":"refs/heads/"+DATA_BRANCH, "sha":os.environ["GITHUB_SHA"]})

    def api(self, path, method="GET", data=None):
        url = "https://api.github.com/repos/"+self.repo+path
        return request_json(url, headers={"Authorization":"Bearer "+self.token, "X-GitHub-Api-Version":"2022-11-28"}, method=method, data=data, timeout=25)[0]

    def read(self, path, default=None):
        local = self.root/path
        if not local.exists() and self.github:
            try:
                d = self.api("/contents/"+path+"?ref="+DATA_BRANCH)
                if d.get("encoding") != "base64":
                    raise RuntimeError("Unexpected checkpoint file encoding")
                local.parent.mkdir(parents=True, exist_ok=True)
                local.write_bytes(base64.b64decode(d["content"]))
            except urllib.error.HTTPError as e:
                if e.code != 404: raise
        if not local.exists(): return default
        return json.loads(local.read_text())

    def append(self, path, value):
        local = self.root/path
        if not local.exists() and self.github:
            try:
                d = self.api("/contents/"+path+"?ref="+DATA_BRANCH)
                local.parent.mkdir(parents=True, exist_ok=True)
                local.write_bytes(base64.b64decode(d["content"]))
            except urllib.error.HTTPError as e:
                if e.code != 404: raise
        local.parent.mkdir(parents=True, exist_ok=True)
        with local.open("a") as f: f.write(compact(value)+"\n")
        self.dirty.add(path)

    def write(self, path, value):
        local = self.root/path; local.parent.mkdir(parents=True, exist_ok=True)
        local.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False)+"\n")
        self.dirty.add(path)

    def flush(self):
        if not self.github:
            self.dirty.clear(); return
        if not self.dirty: return
        ref = self.api("/git/ref/heads/"+DATA_BRANCH)
        parent = ref["object"]["sha"]
        prior = self.api("/git/commits/"+parent)
        tree = self.api("/git/trees", "POST", {"base_tree":prior["tree"]["sha"], "tree":[{"path":p,"mode":"100644","type":"blob","content":(self.root/p).read_text()} for p in sorted(self.dirty)]})
        c = self.api("/git/commits", "POST", {"message":"Save public Oracle paper-study observations "+utc(), "tree":tree["sha"], "parents":[parent]})
        self.api("/git/refs/heads/"+DATA_BRANCH, "PATCH", {"sha":c["sha"],"force":False})
        self.dirty.clear()

def new_state():
    now=time.time(); start=math.ceil(now/900)*900
    return {"schema_version":1,"created_at":now,"created_at_utc":utc(now),"study_start":start,"study_stop":start+40*3600,"poll_seconds":INTERVAL,"source":ORACLE,"market_source":KALSHI,"data_branch":DATA_BRANCH,"rounds":{},"samples":0,"error_count":0,"segments":[],"fees":[],"paper_stake_dollars":1,"personal_account_data":False}

def status(state, running):
    rounds=list(state["rounds"].values())
    official=[r for r in rounds if r.get("official",{}).get("market",{}).get("status")=="finalized" and r["official"]["market"].get("result") in ("yes","no")]
    called=[r for r in rounds if r.get("call",{}).get("side") in ("UP","DOWN")]
    settled=[r for r in called if r in official]
    wins=sum((r["call"]["side"]=="UP")== (r["official"]["market"]["result"]=="yes") for r in settled)
    recent=[]
    for r in sorted(rounds,key=lambda x:x["open_ts"],reverse=True)[:20]:
        m=r.get("official",{}).get("market",{})
        recent.append({"ticker":r["ticker"],"open_ts":r["open_ts"],"close_ts":r["close_ts"],"call":r.get("call"),"call_observed_at":r.get("call_observed_at"),"result":m.get("result") if m.get("status")=="finalized" else None,"samples":r.get("samples",0),"revised":r.get("call_revised",False)})
    elapsed=max(0,min(time.time(),state["study_stop"])-state["study_start"])
    return {"status":"recording" if running else "segment_complete","updated_at":utc(),"last_observation":state.get("last_observation"),"study_start":utc(state["study_start"]),"study_stop":utc(state["study_stop"]),"hours_elapsed":elapsed/3600,"samples":state["samples"],"errors":state["error_count"],"observed_rounds":len(rounds),"locked_calls":len(called),"verified_settled_calls":len(settled),"wins":wins,"losses":len(settled)-wins,"profit_status":"NOT YET VERIFIED — sampled-quote paper analysis required","recent":recent,"source":ORACLE,"data_branch":DATA_BRANCH,"run_url":state.get("run_url"),"periods":[{"hours":h,"elapsed_ready":elapsed>=h*3600} for h in (12,24,36)]}

def run(args):
    sink=Sink(args.directory,args.github)
    state=sink.read("state.json") or new_state()
    state.setdefault("fee_sources",["https://kalshi.com/docs/kalshi-fee-schedule.pdf","https://docs.kalshi.com/getting_started/fee_rounding"])
    now=time.time()
    segment={"segment":str(args.segment),"start":now,"end":None,"errors":0}
    state["segments"].append(segment)
    if os.environ.get("GITHUB_RUN_ID"):
        state["run_url"]="https://github.com/"+sink.repo+"/actions/runs/"+os.environ["GITHUB_RUN_ID"]
    sink.write("state.json",state); sink.write("status.json",status(state,True)); sink.flush()
    deadline=min(now+args.seconds,state["study_stop"]+1800)
    next_flush=time.monotonic()+120; next_metadata=0; next_fees=0
    pool=concurrent.futures.ThreadPoolExecutor(max_workers=4)
    while not STOP and time.time()<deadline:
        cycle=time.monotonic()
        try:
            d,fetch=request_json(ORACLE)
            w=d.get("window") or {}; c=d.get("call") or {}; ticker=w.get("ticker")
            if not isinstance(ticker,str) or not re.fullmatch(r"KXBTC15M-[A-Z0-9-]+",ticker):
                raise ValueError("Unexpected or missing BTC15 market identifier")
            now=time.time(); open_ts=float(w["open_ts"]); close_ts=float(w["close_ts"])
            if close_ts<=open_ts or close_ts-open_ts>901: raise ValueError("Invalid round times")
            if now>=state["study_stop"] and open_ts>=state["study_stop"]:
                book=None; book_meta=None
            else:
                try:
                    b,book_meta=request_json(KALSHI+"/markets/"+ticker+"/orderbook?depth=20")
                    book=b.get("orderbook_fp")
                    if not isinstance(book,dict): raise ValueError("Missing fixed-point book")
                except Exception as e:
                    book=None;book_meta={"received_at":time.time(),"error":type(e).__name__+": "+str(e)[:180]}
            r=state["rounds"].setdefault(ticker,{"ticker":ticker,"open_ts":open_ts,"close_ts":close_ts,"first_observed_at":fetch["received_at"],"samples":0})
            r["samples"]+=1;r["last_observed_at"]=fetch["received_at"]
            if c.get("sealed") and c.get("side") in ("UP","DOWN","SITOUT"):
                if not r.get("call"):
                    r["call"]=c.copy();r["call_observed_at"]=fetch["received_at"]
                    r["fee_observation"]=state["fees"][-1] if state["fees"] else None
                elif (r["call"].get("side"),r["call"].get("sealed_at")) != (c.get("side"),c.get("sealed_at")):
                    r["call_revised"]=True
            if time.time()>=next_fees:
                try:
                    f,fm=request_json(KALSHI+"/series/KXBTC15M")
                    fs=f["series"]
                    state["fees"].append({"at":fm["received_at"],"fee_type":fs.get("fee_type"),"fee_multiplier":fs.get("fee_multiplier")})
                    if r.get("call") and not r.get("fee_observation"):r["fee_observation"]=state["fees"][-1]
                    next_fees=time.time()+3600
                except Exception as e:
                    sink.append("data/errors/"+str(args.segment)+".jsonl",{"ts":time.time(),"source":"series","error":str(e)[:180]});next_fees=time.time()+60
            keys=("ticker","open_ts","close_ts","secs_left","spot","strike","yes_ask","no_ask","yes_bid","no_bid","p_up")
            row={"ts":fetch["received_at"],"oracle_fetch":fetch,"window":{k:w.get(k) for k in keys},"call":c,"metrics":w.get("metrics"),"book_fetch":book_meta,"book":book}
            if open_ts<state["study_stop"]:
                sink.append("data/rounds/"+ticker+".jsonl",row)
            state["samples"]+=1;state["last_observation"]=fetch["received_at"]
            if time.time()>=next_metadata:
                pending=[x for x in state["rounds"].values() if not (x.get("official",{}).get("market",{}).get("status")=="finalized" and x["official"]["market"].get("result") in ("yes","no"))]
                jobs={pool.submit(market,x["ticker"]):x for x in pending[-10:]}
                for f,x in jobs.items():
                    try:x["official"]=f.result()
                    except Exception as e:sink.append("data/errors/"+str(args.segment)+".jsonl",{"ts":time.time(),"source":"market","ticker":x["ticker"],"error":str(e)[:180]})
                next_metadata=time.time()+60
        except Exception as e:
            state["error_count"]+=1;segment["errors"]+=1
            sink.append("data/errors/"+str(args.segment)+".jsonl",{"ts":time.time(),"source":"poll","error":type(e).__name__+": "+str(e)[:250]})
        if time.monotonic()>=next_flush:
            sink.write("state.json",state);sink.write("status.json",status(state,True))
            try:
                sink.flush();print(compact({"checkpoint":utc(),"samples":state["samples"],"rounds":len(state["rounds"]),"errors":state["error_count"]}),flush=True)
            except Exception as e:
                print(compact({"checkpoint_error":type(e).__name__+": "+str(e)[:200]}),flush=True)
            next_flush=time.monotonic()+120
        wait=max(0,INTERVAL-(time.monotonic()-cycle))
        if wait:time.sleep(min(wait,max(0,deadline-time.time())))
    segment["end"]=time.time()
    state["finished"]=time.time()>=state["study_stop"]
    sink.write("state.json",state);sink.write("status.json",status(state,False));sink.flush()
    pool.shutdown(wait=True)
    print(compact(status(state,False)),flush=True)

def interrupted(*_):
    global STOP
    STOP=True

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--seconds",type=int,default=18000);p.add_argument("--segment",default="local");p.add_argument("--directory",default="observations");p.add_argument("--github",action="store_true")
    a=p.parse_args()
    signal.signal(signal.SIGTERM,interrupted);signal.signal(signal.SIGINT,interrupted)
    run(a)
