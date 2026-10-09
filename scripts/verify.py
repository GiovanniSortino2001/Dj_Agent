#!/usr/bin/env python3
"""Repeatable verification, no hardware actions. Run from repository root."""
import argparse
import importlib.util
import importlib.metadata
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--extras',action='store_true')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    out=root/'results'/'rerun'; out.mkdir(parents=True,exist_ok=True)
    records=[]
    def run(name,argv,timeout=120):
        start=time.monotonic()
        try:
            r=subprocess.run(argv,cwd=root,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout)
            code,log=r.returncode,r.stdout
        except subprocess.TimeoutExpired as e:
            code,log=124,str(e)
        (out/f'{name}.log').write_text(log)
        records.append(dict(name=name,argv=argv,exit_code=code,seconds=round(time.monotonic()-start,3)))
        print(name,'PASS' if code==0 else 'FAIL',flush=True)
        return code==0
    py=sys.executable
    run('unittest',[py,'-m','unittest','discover','-s','tests','-v'])
    if shutil.which('node'): run('mapping',['node','tests/test_mapping.js'])
    demo=out/'demo'
    run('demo',[py,'-m','dj','demo','--out',str(demo)])
    run('simulate',[py,'-m','dj','simulate','--catalog',str(demo/'catalog.sqlite'),'--plan',str(demo/'plan.json'),'--out',str(out/'trace.json')])
    if args.extras:
        if importlib.util.find_spec('essentia'):
            run('essentia',[py,'-m','dj','analyze',str(demo/'track_1.wav'),'--backend','essentia','--out',str(out/'essentia.json')])
        if all(importlib.util.find_spec(x) for x in ('torch','onnx','onnxruntime')):
            ml=out/'ml'; ml.mkdir(exist_ok=True)
            run('dataset',[py,'-m','dj','dataset','--out',str(ml/'data.npz'),'--samples','128'])
            if run('train',[py,'-m','dj','train','--data',str(ml/'data.npz'),'--out',str(ml/'model.pt'),'--epochs','5'],300):
                if run('export',[py,'-m','dj','export','--checkpoint',str(ml/'model.pt'),'--out',str(ml/'model.onnx')],180):
                    run('infer',[py,'-m','dj','infer','--model',str(ml/'model.onnx'),'--data',str(ml/'data.npz'),'--out',str(ml/'inference.json')])
                    run('gru-preview',[py,'-m','dj','preview','--catalog',str(demo/'catalog.sqlite'),'--plan',str(demo/'plan.json'),'--onnx',str(ml/'model.onnx'),'--out',str(ml/'preview.wav')])
    versions={}
    for package in ('numpy','torch','onnx','onnxruntime','essentia','mido','python-rtmidi'):
        try: versions[package]=importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError: versions[package]=None
    result=dict(python=sys.version,platform=platform.platform(),versions=versions,commands=records,
                unverified=['real Mixxx/ALSA routing and audio','actual Qwen model','musical quality'])
    (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    return 0 if all(r['exit_code']==0 for r in records) else 1

if __name__=='__main__': raise SystemExit(main())
