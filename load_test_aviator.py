#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Aviator SSE Load Test â€” pure asyncio, no threads. Corrected."""
import asyncio, json, sys, time, subprocess

HOST="127.0.0.1"; PORT=8080
PATH=b"/api/aviator/stream?uid=loadtest"
STAGES=[50,100,200,300,500]
RESULTS={}

def stats():
    try:
        load=subprocess.run(['cat','/proc/loadavg'],capture_output=True,text=True).stdout.split()[0]
        mem=subprocess.run(['free','-m'],capture_output=True,text=True).stdout
        ln=[l for l in mem.splitlines() if l.startswith('Mem:')][0].split()
        return float(load),int(ln[2]),int(ln[6])
    except Exception:
        return None,None,None

async def read_events(reader, duration):
    events=0; buf=b''; end=time.time()+duration
    try:
        while time.time()<end:
            chunk=await asyncio.wait_for(reader.read(256),timeout=4.0)
            if not chunk: break
            buf+=chunk
            while b'\n\n' in buf:
                buf=buf.split(b'\n\n',1)[1]; events+=1
    except Exception:
        pass
    return events

async def connect_one(i, res):
    st=time.time(); r=None; w=None; ok=False; ev=0
    try:
        r,w=await asyncio.open_connection(HOST,PORT)
        w.write(b"GET "+PATH+b" HTTP/1.1\r\nHost: localhost\r\nAccept: text/event-stream\r\nCache-Control: no-cache\r\nConnection: keep-alive\r\n\r\n")
        await w.drain()
        ev=await read_events(r,5)
        ok=ev>=1
    except Exception:
        ok=False
    finally:
        if w:
            try:
                w.close(); await w.wait_closed()
            except Exception:
                pass
    res.append({"idx":i,"ok":ok,"events":ev,"latency":round(time.time()-st,2)})

async def stage(n):
    res=[]; t0=time.time()
    await asyncio.gather(*[asyncio.create_task(connect_one(i,res)) for i in range(n)])
    return res, time.time()-t0

def run_stage(n):
    print(f"\n=== STAGE {n} concurrent SSE ===",flush=True)
    loop=asyncio.new_event_loop(); asyncio.set_event_loop(loop)
    res,tt=loop.run_until_complete(stage(n)); loop.close()
    ok=sum(1 for x in res if x['ok']); ev=sum(x['events'] for x in res)
    lat=sorted(x['latency'] for x in res)
    p50=lat[len(lat)//2] if lat else 0; p95=lat[int(len(lat)*0.95)] if lat else 0
    load,used,avail=stats(); pct=round(ok/n*100,1) if n else 0
    print(f"  Success {ok}/{n} ({pct}%)  Events {ev}  Time {tt:.1f}s",flush=True)
    print(f"  Lat p50 {p50:.2f}s p95 {p95:.2f}s  CPU load {load}  RAM used {used}MB avail {avail}MB",flush=True)
    RESULTS[n]={"requests":n,"success":ok,"success_pct":pct,"total_time":round(tt,1),
        "events_total":ev,"p50":p50,"p95":p95,"server_load":load,"ram_used_mb":used,"ram_avail_mb":avail}

if __name__=="__main__":
    if len(sys.argv)>1: STAGES=[int(x) for x in sys.argv[1].split(',')]
    print(f"SSE Load Test -> {HOST}:{PORT}{PATH.decode()}")
    crashed=None
    for s in STAGES:
        run_stage(s)
        if RESULTS[s]['success_pct']<100:
            crashed=s; print(f"\nâš ï¸ CAPACITY < 100% at {s}",flush=True); break
    out={"crashed_at":crashed,
         "max_sustained_100pct":STAGES[STAGES.index(crashed)-1] if crashed else STAGES[-1],
         "stages":RESULTS}
    open('load_test_results.json','w').write(json.dumps(out,indent=2))
    print("\n=== SUMMARY ==="); print(json.dumps(out,indent=2))
