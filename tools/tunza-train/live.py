#!/usr/bin/env python3
"""Live page for Tunza decision-model training: the plan, the method grid, the loss curves, the layers and the hardware.

Read-only. It never starts, stops or changes a run. Standard library only.

  python tools/tunza-train/live.py [--runs runs] [--plan tools/tunza-train/plan-status.json] [--port 8790]

Each run is a folder under --runs:
  meta.json         method, seed, size, mode (lora|full), total_steps, pid (optional), done/failed flags
  telemetry.jsonl   one JSON object per line: step, loss, lr, grad_norm, tok_per_s, gpu_mem_gb, elapsed_s, examples_seen
  layerstats.json   optional: {step, steps, loss, rows:[{layer, mod, rel_change, grad}], recent:[{text, probs, label, options, danger}]}

Nothing is invented. With no runs the page says so. The hardware panel shows the exact error when the GPU cannot be read.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import re
import shutil
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

METHODS = ("ce", "pair", "list", "rl", "hybrid", "cost", "sft_rl", "dpo", "rft")
SEEDS = (0, 1, 2)
TARGET_LOW, TARGET_HIGH = 85, 92  # full-use band for GPU busy percent, same as tunza-adw
STALE_SECONDS = 120


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def read_telemetry(path: Path, limit: int = 6000) -> list[dict]:
    rows: list[dict] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return rows
    for line in lines[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict) and isinstance(obj.get("step"), (int, float)):
            rows.append(obj)
    return rows


def downsample(values: list[float], n: int = 80) -> list[float]:
    if len(values) <= n:
        return values
    step = (len(values) - 1) / (n - 1)
    return [values[round(i * step)] for i in range(n)]


def run_state(meta: dict, rows: list[dict], mtime: float, now: float) -> str:
    total = meta.get("total_steps") or (rows[-1].get("total_steps") if rows else 0) or 0
    last = rows[-1]["step"] if rows else 0
    if meta.get("failed"):
        return "failed"
    if meta.get("done") or (rows and rows[-1].get("done")) or (total and last >= total):
        return "done"
    if not rows:
        return "queued"
    return "running" if now - mtime < STALE_SECONDS else "stalled"


def summarize_run(folder: Path, now: float) -> dict:
    meta = read_json(folder / "meta.json", {})
    tele = folder / "telemetry.jsonl"
    rows = read_telemetry(tele)
    mtime = tele.stat().st_mtime if tele.is_file() else (folder.stat().st_mtime if folder.exists() else 0)
    total = int(meta.get("total_steps") or (rows[-1].get("total_steps") if rows else 0) or 0)
    last = int(rows[-1]["step"]) if rows else 0
    losses = [float(r["loss"]) for r in rows if isinstance(r.get("loss"), (int, float))]
    state = run_state(meta, rows, mtime, now)
    eta_min = None
    if state == "running" and total and last and len(rows) > 2:
        recent = rows[-21:]
        span = (recent[-1].get("elapsed_s") or 0) - (recent[0].get("elapsed_s") or 0)
        steps = recent[-1]["step"] - recent[0]["step"]
        if span > 0 and steps > 0:
            eta_min = round((total - last) * span / steps / 60)
    return {
        "tag": folder.name,
        "method": meta.get("method"),
        "seed": meta.get("seed"),
        "size": meta.get("size"),
        "mode": meta.get("mode", "lora"),
        "pid": meta.get("pid"),
        "state": state,
        "step": last,
        "total": total,
        "loss": losses[-1] if losses else None,
        "loss_pts": downsample(losses),
        "tok_per_s": rows[-1].get("tok_per_s") if rows else None,
        "gpu_mem_gb": rows[-1].get("gpu_mem_gb") if rows else None,
        "examples_seen": rows[-1].get("examples_seen") if rows else None,
        "eta_min": eta_min,
        "mtime": mtime,
    }


def load_plan(path: Path | None) -> dict:
    if path is None or not path.is_file():
        return {"phases": [], "note": "no plan file"}
    if path.suffix == ".json":
        return read_json(path, {"phases": [], "note": "plan file unreadable"})
    return parse_plan_html(path.read_text(encoding="utf-8", errors="replace"))


def parse_plan_html(text: str) -> dict:
    """Read phase names and checkbox counts from a plan page. Names and counts only."""
    phases = []
    for block in re.split(r'<div class="phase">', text)[1:]:
        title = re.search(r"<h3>(.*?)</h3>", block, re.S)
        if not title:
            continue
        raw = title.group(1)
        status = re.search(r"\[(x|wip|f)?\]", raw)
        name = re.sub(r"<[^>]+>", "", raw)
        name = re.sub(r"^\s*\[(?:x|wip|f)?\]\s*", "", name).strip()
        marks = re.findall(r'class="status">\[(x|wip|f)?\]', block)
        phases.append({
            "name": name,
            "status": {"x": "done", "wip": "running", "f": "failed"}.get(status.group(1) if status else None, "idle"),
            "done": sum(1 for m in marks if m == "x"),
            "total": len(marks),
        })
    return {"phases": phases}


def ram_info() -> dict | None:
    try:
        if os.name == "nt":
            class MS(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            ms = MS()
            ms.dwLength = ctypes.sizeof(MS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms))
            total, avail = ms.ullTotalPhys, ms.ullAvailPhys
        elif sys.platform == "darwin":
            total = int(subprocess.check_output(["sysctl", "-n", "hw.memsize"], timeout=3).strip())
            vm = subprocess.check_output(["vm_stat"], timeout=3).decode()
            page = int(re.search(r"page size of (\d+)", vm).group(1))
            free = sum(int(re.search(rf"{k}:\s+(\d+)", vm).group(1)) for k in ("Pages free", "Pages inactive", "Pages speculative"))
            avail = free * page
        else:
            info = {l.split(":")[0]: int(l.split()[1]) * 1024 for l in Path("/proc/meminfo").read_text().splitlines() if ":" in l}
            total, avail = info["MemTotal"], info["MemAvailable"]
        return {"total_gb": round(total / 1e9, 1), "used_gb": round((total - avail) / 1e9, 1),
                "used_pct": round(100 * (total - avail) / total)}
    except Exception:
        return None


_GPU_CACHE: dict = {"t": 0.0, "v": None}


def _run(cmd: list[str]) -> tuple[int, str]:
    kw = {}
    if os.name == "nt":
        kw["creationflags"] = 0x08000000
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=5, **kw)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def gpu_info() -> dict:
    now = time.time()
    if _GPU_CACHE["v"] is not None and now - _GPU_CACHE["t"] < 2:
        return _GPU_CACHE["v"]
    try:
        rc, text = _run(["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,memory.total,power.draw,temperature.gpu,driver_version",
                         "--format=csv,noheader,nounits"])
        if rc != 0 or not text.strip():
            out = {"ok": False, "error": text.strip()[:300] or f"nvidia-smi exited {rc}"}
        else:
            f = [x.strip() for x in text.strip().splitlines()[0].split(",")]

            def num(s):
                return float(s) if re.fullmatch(r"[0-9.]+", s or "") else None

            out = {"ok": True, "name": f[0], "util": num(f[1]), "mem_used_mb": num(f[2]), "mem_total_mb": num(f[3]),
                   "power_w": num(f[4]), "temp_c": num(f[5]), "driver": f[6], "apps": []}
            rc2, apps = _run(["nvidia-smi", "--query-compute-apps=pid,process_name,used_memory", "--format=csv,noheader,nounits"])
            if rc2 == 0:
                for line in apps.strip().splitlines():
                    p = [x.strip() for x in line.split(",")]
                    if len(p) >= 3 and p[0].isdigit():
                        out["apps"].append({"pid": int(p[0]), "name": os.path.basename(p[1]), "mem_mb": num(p[2])})
    except FileNotFoundError:
        out = {"ok": False, "error": "nvidia-smi not found on this machine"}
    except Exception as exc:  # timeout or driver fault: show it, do not guess
        out = {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:300]}
    _GPU_CACHE.update(t=now, v=out)
    return out


def dedication(gpu: dict, active: dict | None) -> dict:
    """Plain verdict on whether the card is used by training and nothing else."""
    if not gpu.get("ok"):
        return {"tone": "bad", "text": "GPU cannot be read: " + gpu.get("error", "unknown")}
    if not active:
        return {"tone": "idle", "text": "Nothing is training. The card is idle."}
    others = [a for a in gpu.get("apps", []) if active.get("pid") and a["pid"] != active["pid"]]
    util = gpu.get("util")
    if others:
        names = ", ".join(f'{a["name"]} ({a["pid"]})' for a in others[:4])
        return {"tone": "warn", "text": "Other programs are on the GPU: " + names}
    if util is None:
        return {"tone": "warn", "text": "GPU busy percent not reported."}
    if util < TARGET_LOW:
        return {"tone": "warn", "text": f"Under-using the card: {util:.0f}% busy. Target {TARGET_LOW} to {TARGET_HIGH}%."}
    return {"tone": "ok", "text": f"Card in full use: {util:.0f}% busy, no other GPU programs."}


def build_state(runs_dir: Path, plan: Path | None, now: float | None = None) -> dict:
    now = now or time.time()
    runs = []
    if runs_dir.is_dir():
        runs = [summarize_run(d, now) for d in sorted(runs_dir.iterdir()) if d.is_dir()]
    active_runs = [r for r in runs if r["state"] == "running"]
    newest = max(runs, key=lambda r: r["mtime"]) if runs else None
    current = max(active_runs, key=lambda r: r["mtime"]) if active_runs else newest
    gpu = gpu_info()
    try:
        free_gb = round(shutil.disk_usage(runs_dir if runs_dir.exists() else Path(".")).free / 1e9, 1)
    except OSError:
        free_gb = None
    return {
        "now": now,
        "methods": list(METHODS),
        "seeds": list(SEEDS),
        "runs": runs,
        "current": current["tag"] if current else None,
        "plan": load_plan(plan),
        "gpu": gpu,
        "ram": ram_info(),
        "disk_free_gb": free_gb,
        "dedication": dedication(gpu, current if current and current["state"] == "running" else None),
        "target": [TARGET_LOW, TARGET_HIGH],
    }


PAGE = r"""<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Tunza training</title>
<style>:root{--bg:#07050a;--fg:#fbeeee;--mut:#b49a9a;--glass:rgba(24,10,12,.66);--edge:rgba(255,120,110,.26);--ok:#5af0b4;--bad:#ff6b6b;--warn:#ffc15a;--brand:#e5483b}
html,body{margin:0;height:100%;background:var(--bg);color:var(--fg);font:14px/1.4 -apple-system,"Segoe UI",system-ui,sans-serif;overflow:hidden}
#gl{position:fixed;inset:0;width:100%;height:100%;display:block}
.glass{position:fixed;background:var(--glass);border:1px solid var(--edge);border-radius:14px;backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);padding:10px 14px;box-sizing:border-box}
.lab{font-size:11px;letter-spacing:1.4px;color:var(--mut);text-transform:uppercase;margin-bottom:6px}
#top{top:12px;left:12px;right:12px;display:flex;gap:18px;align-items:center;flex-wrap:wrap}
#top h1{font-size:15px;margin:0;font-weight:650;color:var(--brand)}#sub{color:var(--mut);font-size:13px;flex:1;min-width:260px}
#bar{position:absolute;left:0;bottom:0;height:3px;border-radius:0 0 14px 14px;background:linear-gradient(90deg,#e5483b,#f59e0b,#fff3d6);width:0;transition:width .8s}
#left{left:12px;top:72px;bottom:260px;width:min(370px,30vw);display:flex;flex-direction:column;gap:10px;position:fixed}
#right{right:12px;top:72px;bottom:260px;width:min(330px,28vw);display:flex;flex-direction:column;gap:10px;position:fixed}
#left .glass,#right .glass{position:relative;overflow:auto}
#plan{flex:1}#inp{flex:0 0 auto;max-height:34%}#hw{flex:0 0 auto}#out{flex:1}
.ph{display:flex;gap:8px;align-items:baseline;margin:3px 0;font-size:13px}.ph b{font-weight:600}.ph .c{color:var(--mut);margin-left:auto;white-space:nowrap}
.dot{width:10px;height:10px;border-radius:50%;flex:none;border:1px solid var(--mut);align-self:center}.dot.done{background:var(--ok);border-color:var(--ok)}.dot.running{background:var(--warn);border-color:var(--warn)}.dot.failed{background:var(--bad);border-color:var(--bad)}
#txt{font-size:13px;color:#ffe3e0;max-height:15vh;overflow:hidden;white-space:pre-wrap;word-break:break-word}
.g{margin:5px 0 9px}.g .t{display:flex;justify-content:space-between;font-size:12px}.g .t span:last-child{color:var(--mut)}
.pbar{position:relative;height:9px;border-radius:5px;background:rgba(255,255,255,.09);overflow:hidden;margin-top:3px}.pbar i{display:block;height:100%;width:0;transition:width .6s;background:var(--brand)}
.pbar u{position:absolute;top:0;bottom:0;background:rgba(90,240,180,.28);border-left:1px solid var(--ok);border-right:1px solid var(--ok)}
#ded{font-weight:650;margin-top:4px;font-size:13px}.ok{color:var(--ok)}.warn{color:var(--warn)}.bad{color:var(--bad)}.idle{color:var(--mut)}
#bot{left:12px;right:12px;bottom:12px;height:236px;display:flex;gap:18px;align-items:stretch}
#grid{display:grid;grid-template-columns:auto repeat(3,22px);gap:3px 4px;align-items:center;font-size:12px}#grid .m{color:var(--mut);white-space:nowrap;padding-right:6px}
#grid i{width:22px;height:15px;border-radius:3px;display:block;background:rgba(255,255,255,.1)}
#grid i.running{background:var(--warn);animation:p 1.2s infinite}#grid i.done{background:var(--ok)}#grid i.failed{background:var(--bad)}#grid i.stalled{background:#9a6b00}
@keyframes p{50%{opacity:.35}}
#curv{flex:1;min-width:0;display:flex;flex-direction:column}#curv svg{flex:1;width:100%;min-height:0}
#kp{display:flex;flex-direction:column;gap:6px;justify-content:center;min-width:112px}.k{font-size:19px;font-weight:650}.m2{font-size:11px;color:var(--mut)}
#leg{font-size:11px;color:var(--mut);display:flex;gap:10px;flex-wrap:wrap}#leg b{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:4px}
#empty{position:fixed;left:50%;top:44%;transform:translate(-50%,-50%);text-align:center;color:var(--mut);display:none;pointer-events:none}
</style>
<canvas id=gl></canvas>
<div id=top class=glass><h1>Tunza decision model training</h1><div id=sub>loading</div><div id=bar></div></div>
<div id=left><div id=plan class=glass><div class=lab>Plan</div><div id=phases>loading</div></div>
<div id=inp class=glass><div class=lab>Example being read</div><div id=txt>waiting for the first example</div></div></div>
<div id=right><div id=hw class=glass><div class=lab>This PC</div><div id=hwb>loading</div><div id=ded></div></div>
<div id=out class=glass><div class=lab>Model answer</div><div id=opts></div><div id=verdict style="font-weight:650;margin-top:6px"></div></div></div>
<div id=empty><div style="font-size:18px;color:var(--fg)">No training run has started</div><div>The page fills in as soon as a run writes its first step.</div></div>
<div id=bot class=glass><div id=grid></div><div id=curv><div class=lab>Loss by method</div><svg id=loss viewBox="0 0 400 100" preserveAspectRatio=none></svg><div id=leg></div></div>
<div id=kp><div><div class=k id=k_loss>-</div><div class=m2>loss</div></div><div><div class=k id=k_step>-</div><div class=m2>step</div></div><div><div class=k id=k_tok>-</div><div class=m2>tokens per second</div></div></div></div>
<script type="importmap">{"imports":{"three":"https://cdn.jsdelivr.net/npm/three@0.160.1/build/three.module.js","three/addons/":"https://cdn.jsdelivr.net/npm/three@0.160.1/examples/jsm/"}}</script>
<script type=module>
import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {EffectComposer} from 'three/addons/postprocessing/EffectComposer.js';
import {RenderPass} from 'three/addons/postprocessing/RenderPass.js';
import {UnrealBloomPass} from 'three/addons/postprocessing/UnrealBloomPass.js';
const cv=document.getElementById('gl'),R=new THREE.WebGLRenderer({canvas:cv,antialias:true});R.setPixelRatio(Math.min(devicePixelRatio,2));
const scene=new THREE.Scene();scene.fog=new THREE.FogExp2(0x04060d,0.018);
const cam=new THREE.PerspectiveCamera(48,1,.1,400);cam.position.set(-9,8,42);
const ctl=new OrbitControls(cam,cv);ctl.enableDamping=true;ctl.autoRotate=true;ctl.autoRotateSpeed=0.7;ctl.target.set(0,0,0);
const comp=new EffectComposer(R);comp.addPass(new RenderPass(scene,cam));const bloom=new UnrealBloomPass(new THREE.Vector2(1,1),1.4,0.8,0.0);comp.addPass(bloom);
function size(){const w=innerWidth,h=innerHeight;R.setSize(w,h,false);comp.setSize(w,h);cam.aspect=w/h;cam.updateProjectionMatrix()}addEventListener('resize',size);size();
// starfield
{const g=new THREE.BufferGeometry(),n=900,a=new Float32Array(n*3);for(let i=0;i<n;i++){a[i*3]=(Math.random()-.5)*160;a[i*3+1]=(Math.random()-.5)*90;a[i*3+2]=(Math.random()-.5)*120}
g.setAttribute('position',new THREE.BufferAttribute(a,3));scene.add(new THREE.Points(g,new THREE.PointsMaterial({size:.09,color:0x6f8cc4,transparent:true,opacity:.55})))}
const FAM=[m=>m==='q_proj'||m==='k_proj',m=>m==='v_proj'||m==='o_proj',m=>m.startsWith('in_proj'),m=>m==='out_proj',m=>m==='gate_proj'||m==='up_proj',m=>m==='down_proj'];
const FN=['attention q,k','attention v,o','linear-attn in','linear-attn out','MLP up','MLP down'];
const COLS=8,DX=5.2;let built=false,nodes=[],edges=[],inst,lines,lineCol,parts,pos,partEdge,partPh,L=[],RECENT=[],cur=0,swapT=0,outNodes=[],inNodes=[],tgt=new Map();
const tmp=new THREE.Object3D(),colr=new THREE.Color();
function ramp(t){t=Math.sqrt(Math.max(0,Math.min(1,t)));const a=new THREE.Color(0x2f6bff),m=new THREE.Color(0xb44cff),b=new THREE.Color(0xffa23a);return t<.5?a.lerp(m,t*2):m.lerp(b,(t-.5)*2)}
function build(){const layers=[...new Set(L.filter(r=>r.layer>=0).map(r=>r.layer))].sort((a,b)=>a-b);if(!layers.length)return false;
const per=Math.ceil(layers.length/COLS);
for(let c=0;c<COLS;c++){const ls=layers.slice(c*per,(c+1)*per),x=(c-(COLS-1)/2)*DX,rad=2.2+4.6*Math.sin(Math.PI*(c+.5)/COLS),n=ls.length*6;
ls.forEach((l,li)=>FAM.forEach((f,fi)=>{const j=li*6+fi,ang=2*Math.PI*j/n+c*.35,r=rad*(0.82+0.18*Math.sin(j*1.7));
nodes.push({c,layer:l,fam:fi,x,y:Math.sin(ang)*r,z:Math.cos(ang)*r,ch:0,gr:0,sch:0,sgr:0,idx:nodes.length,f})}))}
const hx=((COLS)-(COLS-1)/2)*DX;['q','k'].forEach((m,i)=>nodes.push({c:COLS,layer:-1,fam:i,mod:m,x:hx,y:(i?1:-1)*1.2,z:0,ch:0,gr:0,sch:0,sgr:0,idx:nodes.length}));
for(let i=0;i<14;i++){const a=2*Math.PI*i/14;inNodes.push({x:-(COLS+1)/2*DX-1.6,y:Math.sin(a)*2.4,z:Math.cos(a)*2.4})}
outNodes.push({x:hx+DX*0.95,y:2.6,z:0},{x:hx+DX*0.95,y:-2.6,z:0});
const byCol=[];nodes.forEach(n=>(byCol[n.c]=byCol[n.c]||[]).push(n));
for(let c=0;c<COLS;c++){const A=byCol[c],B=byCol[c+1];A.forEach((a,i)=>{const m=Math.round(i*(B.length-1)/Math.max(1,A.length-1));for(const d of [-2,-1,0,1,2]){const k=m+d;if(k>=0&&k<B.length)edges.push([a,B[k]])}
if(B.length>2)edges.push([a,B[(i*13+c*5)%B.length]])})}
byCol[COLS].forEach(h=>{outNodes.forEach(o=>edges.push([h,o]))});
inNodes.forEach((o,i)=>{for(let k=0;k<byCol[0].length;k+=4)edges.push([o,byCol[0][(k+i)%byCol[0].length]])});
// instanced spheres
const geo=new THREE.SphereGeometry(1,16,16),mat=new THREE.MeshBasicMaterial({toneMapped:false});inst=new THREE.InstancedMesh(geo,mat,nodes.length+inNodes.length+outNodes.length);inst.instanceColor=new THREE.InstancedBufferAttribute(new Float32Array(inst.count*3),3);scene.add(inst);
// edges
const lp=new Float32Array(edges.length*6);edges.forEach((e,i)=>{lp.set([e[0].x,e[0].y,e[0].z,e[1].x,e[1].y,e[1].z],i*6)});
const lg=new THREE.BufferGeometry();lg.setAttribute('position',new THREE.BufferAttribute(lp,3));lineCol=new Float32Array(edges.length*6);lg.setAttribute('color',new THREE.BufferAttribute(lineCol,3));
lines=new THREE.LineSegments(lg,new THREE.LineBasicMaterial({vertexColors:true,transparent:true,opacity:.55,blending:THREE.AdditiveBlending,depthWrite:false}));scene.add(lines);
// particles riding the edges
const NP=2600;partEdge=new Uint32Array(NP);partPh=new Float32Array(NP);pos=new Float32Array(NP*3);const pc=new Float32Array(NP*3);
for(let i=0;i<NP;i++){partEdge[i]=Math.floor(Math.random()*edges.length);partPh[i]=Math.random()}
const pg=new THREE.BufferGeometry();pg.setAttribute('position',new THREE.BufferAttribute(pos,3));pg.setAttribute('color',new THREE.BufferAttribute(pc,3));
parts=new THREE.Points(pg,new THREE.PointsMaterial({size:.16,vertexColors:true,transparent:true,opacity:.95,blending:THREE.AdditiveBlending,depthWrite:false}));scene.add(parts);
return true}
function ingest(){const by=new Map();for(const r of L)by.set(r.layer+'|'+r.mod,r);
for(const n of nodes){if(n.layer<0){const r=by.get('-1|'+n.mod);if(r){n.ch=r.rel_change;n.gr=r.grad}continue}
let ch=0,g=0,k=0;for(const r of L)if(r.layer===n.layer&&n.f(r.mod)){ch+=r.rel_change;g+=r.grad;k++}n.ch=k?ch/k:0;n.gr=k?g/k:0}
n_maxC=Math.max(1e-9,...nodes.map(n=>n.ch));n_maxG=Math.max(1e-9,...nodes.map(n=>n.gr))}
let n_maxC=1,n_maxG=1;
const clock=new THREE.Clock();
let lastT=0;function frame(){const t=clock.getElapsedTime(),dt=Math.min(Math.max(t-lastT,0),.05);lastT=t;
if(!built&&L.length){built=build();if(built)ingest()}
if(built){const all=nodes.length;
for(let i=0;i<all;i++){const n=nodes[i];n.sch+=(n.ch/n_maxC-n.sch)*.08;n.sgr+=(n.gr/n_maxG-n.sgr)*.08;const pulse=.5+.5*Math.sin(t*5+n.c*1.1+i*.37),s=.13+.2*n.sgr*(.6+.4*pulse)+(n.layer<0?.2:0);
tmp.position.set(n.x,n.y,n.z);tmp.scale.setScalar(s);tmp.updateMatrix();inst.setMatrixAt(i,tmp.matrix);colr.copy(ramp(n.sch)).multiplyScalar(.7+1.6*n.sgr);inst.setColorAt(i,colr)}
const ex=RECENT.length?RECENT[cur%RECENT.length]:null,pu=ex?PU(ex):0;
inNodes.forEach((o,i)=>{const k=all+i;tmp.position.set(o.x,o.y,o.z);tmp.scale.setScalar(.14+.07*Math.sin(t*6+i));tmp.updateMatrix();inst.setMatrixAt(k,tmp.matrix);inst.setColorAt(k,colr.set(0x5af0d4).multiplyScalar(1.6))});
outNodes.forEach((o,j)=>{const k=all+inNodes.length+j,p=j===0?pu:1-pu;tmp.position.set(o.x,o.y,o.z);tmp.scale.setScalar(.35+.9*p);tmp.updateMatrix();inst.setMatrixAt(k,tmp.matrix);inst.setColorAt(k,colr.set(j===0?0x5af0b4:0x8fa0b8).multiplyScalar(.5+2*p))});
inst.instanceMatrix.needsUpdate=true;inst.instanceColor.needsUpdate=true;
for(let i=0;i<edges.length;i++){const a=edges[i][0],b=edges[i][1],g=(b.sgr!==undefined?b.sgr:.5),c=ramp(a.sch!==undefined?a.sch:.3),w=.10+.6*g;
lineCol.set([c.r*w,c.g*w,c.b*w,c.r*w,c.g*w,c.b*w],i*6)}lines.geometry.attributes.color.needsUpdate=true;
const pa=parts.geometry.attributes.position.array,pcl=parts.geometry.attributes.color.array;
for(let i=0;i<partEdge.length;i++){let ph=partPh[i]+dt*(.9+1.2*(edges[partEdge[i]][1].sgr||0));if(ph>1){ph-=1;partEdge[i]=Math.floor(Math.random()*edges.length)}partPh[i]=ph;
const e=edges[partEdge[i]],a=e[0],b=e[1],g=b.sgr!==undefined?b.sgr:.6;pa[i*3]=a.x+(b.x-a.x)*ph;pa[i*3+1]=a.y+(b.y-a.y)*ph;pa[i*3+2]=a.z+(b.z-a.z)*ph;
const c=ramp(a.sch!==undefined?a.sch:.3),k=g>.15?1.4:.15;pcl[i*3]=c.r*k;pcl[i*3+1]=c.g*k;pcl[i*3+2]=c.b*k}
parts.geometry.attributes.position.needsUpdate=true;parts.geometry.attributes.color.needsUpdate=true;
if(t-swapT>4&&RECENT.length){cur=(cur+1)%RECENT.length;swapT=t;showEx()}}
ctl.update();comp.render();requestAnimationFrame(frame)}
const OPTS=['go_now','get_care_today','need_one_more_answer','monitor_at_home'];
function PU(ex){return ex&&ex.probs?(ex.probs[ex.danger==null?0:ex.danger]||0):0}
const COLORS={ce:'#7aa2ff',pair:'#b48cff',list:'#4fd1c5',rl:'#ff8a5c',hybrid:'#ffd166',cost:'#ff5c8a',sft_rl:'#a3e635',dpo:'#38bdf8',rft:'#f0abfc'};
const $=id=>document.getElementById(id);
function mk(tag,cls,text){const e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e}
function showEx(){const ex=RECENT[cur%RECENT.length];if(!ex)return;let txt=ex.text;try{const o=JSON.parse(ex.text);txt=typeof o==='string'?o:(o.request||JSON.stringify(o))}catch(e){}
$('txt').textContent=String(txt).replace(/\\n/g,'\n');
const names=ex.options||OPTS,box=$('opts');box.textContent='';let best=0;ex.probs.forEach((p,i)=>{if(p>ex.probs[best])best=i});
ex.probs.forEach((p,i)=>{const g=mk('div','g'),t=mk('div','t'),a=mk('span',null,names[i]||('option '+i)),b=mk('span',null,Math.round(p*100)+'%');t.append(a,b);
const bar=mk('div','pbar'),f=mk('i');f.style.width=(p*100)+'%';f.style.background=i===(ex.danger==null?0:ex.danger)?'var(--bad)':(i===best?'var(--brand)':'#7b6f6f');bar.append(f);g.append(t,bar);box.append(g)});
const dz=ex.danger==null?0:ex.danger,v=$('verdict');
if(ex.label===dz&&best!==dz){v.textContent='MISSED DANGER · true answer: '+names[ex.label];v.style.color='var(--bad)'}
else{const ok=best===ex.label;v.textContent=(ok?'correct':'wrong')+' · true answer: '+names[ex.label];v.style.color=ok?'var(--ok)':'var(--warn)'}}
async function nets(){try{const d=await (await fetch('/layers')).json();L=d.rows||[];const first=!RECENT.length;RECENT=d.recent||[];if(built)ingest();if(first&&RECENT.length)showEx()}catch(e){}}
function gauge(label,pct,right,band){const g=mk('div','g'),t=mk('div','t'),a=mk('span',null,label),b=mk('span',null,right);t.append(a,b);
const bar=mk('div','pbar'),f=mk('i');f.style.width=Math.max(0,Math.min(100,pct||0))+'%';bar.append(f);
if(band){const u=mk('u');u.style.left=band[0]+'%';u.style.width=(band[1]-band[0])+'%';bar.append(u)}g.append(t,bar);return g}
function renderHw(d){const b=$('hwb');b.textContent='';const g=d.gpu;
if(g.ok){b.append(mk('div',null,g.name+' · driver '+g.driver));
b.append(gauge('GPU busy',g.util,g.util==null?'n/a':Math.round(g.util)+'%',d.target));
const mp=g.mem_total_mb?100*g.mem_used_mb/g.mem_total_mb:0;b.append(gauge('GPU memory',mp,(g.mem_used_mb/1024).toFixed(1)+' of '+(g.mem_total_mb/1024).toFixed(1)+' GB'));
b.append(mk('div','m2','power '+(g.power_w==null?'n/a':Math.round(g.power_w)+' W')+' · '+(g.temp_c==null?'n/a':g.temp_c+' C')))}
else b.append(mk('div','m2','GPU: no reading'));
if(d.ram)b.append(gauge('System memory',d.ram.used_pct,d.ram.used_gb+' of '+d.ram.total_gb+' GB'));
if(d.disk_free_gb!=null){const low=d.disk_free_gb<50;const e=mk('div',low?'bad':'m2','disk free '+d.disk_free_gb+' GB'+(low?' · too low for training':''));b.append(e)}
const ded=$('ded');ded.textContent=d.dedication.text;ded.className=d.dedication.tone}
function renderPlan(p){const box=$('phases');box.textContent='';if(!p.phases.length){box.append(mk('div','idle',p.note||'no plan loaded'));return}
p.phases.forEach(ph=>{const r=mk('div','ph');r.append(mk('span','dot '+ph.status),mk('b',null,ph.name),mk('span','c',ph.total?ph.done+'/'+ph.total:''));box.append(r)})}
function renderGrid(d){const cur=d.runs.find(r=>r.tag===d.current),size=cur?cur.size:null;const by={};
d.runs.filter(r=>!size||r.size===size).forEach(r=>{const k=r.method+'|'+r.seed;if(!by[k]||r.mtime>by[k].mtime)by[k]=r});
const g=$('grid');g.textContent='';g.append(mk('span','m',size?'size '+size:'method'));d.seeds.forEach(s=>g.append(mk('span','m2','s'+s)));
d.methods.forEach(m=>{g.append(mk('span','m',m));d.seeds.forEach(s=>{const r=by[m+'|'+s],i=mk('i',r?r.state:'');
i.title=r?`${m} seed ${s}: ${r.state}, step ${r.step}/${r.total||'?'}${r.loss==null?'':', loss '+r.loss.toFixed(3)}`:`${m} seed ${s}: not started`;g.append(i)})})}
function renderLoss(d){const cur=d.runs.find(r=>r.tag===d.current),size=cur?cur.size:null,rs=d.runs.filter(r=>r.loss_pts.length>1&&(!size||r.size===size));
const svg=$('loss');svg.textContent='';const leg=$('leg');leg.textContent='';if(!rs.length)return;
const all=rs.flatMap(r=>r.loss_pts),mx=Math.max(...all),mn=Math.min(...all),sp=mx-mn||1,NS='http://www.w3.org/2000/svg';
rs.forEach(r=>{const p=document.createElementNS(NS,'path');p.setAttribute('d',r.loss_pts.map((v,i)=>(i?'L':'M')+(400*i/(r.loss_pts.length-1)).toFixed(1)+' '+(94-88*(v-mn)/sp).toFixed(1)).join(' '));
p.setAttribute('fill','none');p.setAttribute('stroke',COLORS[r.method]||'#fff');p.setAttribute('stroke-width',r.tag===d.current?'2.2':'1');p.setAttribute('opacity',r.tag===d.current?'1':'.55');p.setAttribute('vector-effect','non-scaling-stroke');svg.append(p)});
[...new Set(rs.map(r=>r.method))].forEach(m=>{const s=mk('span');const b=mk('b');b.style.background=COLORS[m]||'#fff';s.append(b,document.createTextNode(m));leg.append(s)})}
async function tick(){try{const d=await (await fetch('/api/state')).json();const cur=d.runs.find(r=>r.tag===d.current);
$('empty').style.display=d.runs.length?'none':'block';
if(cur){const left=cur.state==='done'?'done':(cur.eta_min==null?'':(cur.eta_min>=60?Math.floor(cur.eta_min/60)+' h '+cur.eta_min%60+' min left':cur.eta_min+' min left'));
$('sub').textContent=[cur.tag,cur.method+' · seed '+cur.seed+' · '+cur.size+' · '+cur.mode,cur.state,left,d.runs.filter(r=>r.state==='done').length+' of '+d.runs.length+' runs done'].filter(Boolean).join(' · ');
$('bar').style.width=(cur.total?100*cur.step/cur.total:0)+'%';
$('k_loss').textContent=cur.loss==null?'-':cur.loss.toFixed(3);$('k_step').textContent=cur.step+(cur.total?' / '+cur.total:'');$('k_tok').textContent=cur.tok_per_s==null?'-':Math.round(cur.tok_per_s)}
else{$('sub').textContent='no run yet · engineering runs only, not clinical';$('bar').style.width='0'}
renderPlan(d.plan);renderHw(d);renderGrid(d);renderLoss(d)}catch(e){$('sub').textContent='cannot reach the page server'}}
nets();setInterval(nets,1000);tick();setInterval(tick,2000);requestAnimationFrame(frame);
</script>"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", default="runs")
    ap.add_argument("--plan", default=str(Path(__file__).with_name("plan-status.json")))
    ap.add_argument("--port", type=int, default=8790)
    ap.add_argument("--host", default="127.0.0.1")
    a = ap.parse_args()
    runs_dir, plan = Path(a.runs), Path(a.plan)

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            path = self.path.split("?")[0]
            if path == "/api/state":
                body, kind = json.dumps(build_state(runs_dir, plan)).encode(), "application/json"
            elif path == "/layers":
                st = build_state(runs_dir, plan)
                folder = runs_dir / st["current"] if st["current"] else None
                empty = {"rows": [], "recent": []}
                data = read_json(folder / "layerstats.json", empty) if folder else empty
                body, kind = json.dumps(data).encode(), "application/json"
            elif path in ("/", "/index.html"):
                body, kind = PAGE.encode(), "text/html; charset=utf-8"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    print(f"http://{a.host}:{a.port}", flush=True)
    ThreadingHTTPServer((a.host, a.port), H).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
