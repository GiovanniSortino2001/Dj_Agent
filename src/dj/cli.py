"""CLI entrypoint; optional libraries are imported only by relevant commands."""
import argparse
import json
import logging
import sys
import sqlite3
from pathlib import Path
from . import __version__
from .util import save_json, read_json
from .config import load
from .catalog import Catalog
from .planner import DeterministicPlanner, QwenPlanner
from .control import Safety, simulate


def parser():
    p=argparse.ArgumentParser(prog='dj',description='DJ offline lab — demo senza hardware')
    p.add_argument('--version',action='version',version=__version__)
    p.add_argument('--config',help='File JSON, es. configs/default.json')
    p.add_argument('--log',help='File log UTF-8 (stderr resta attivo)')
    s=p.add_subparsers(dest='command',required=True)
    a=s.add_parser('demo'); a.add_argument('--out',default='examples/demo')
    a=s.add_parser('synth'); a.add_argument('output'); a.add_argument('--bpm',type=float,default=120); a.add_argument('--root',type=int,default=0); a.add_argument('--seconds',type=float,default=24)
    a=s.add_parser('analyze'); a.add_argument('audio'); a.add_argument('--backend',choices=['numpy','auto','essentia']); a.add_argument('--out')
    a=s.add_parser('scan'); a.add_argument('inputs',nargs='+'); a.add_argument('--catalog',required=True); a.add_argument('--backend',choices=['numpy','auto','essentia'])
    a=s.add_parser('catalog'); a.add_argument('--catalog',required=True)
    a=s.add_parser('compare'); a.add_argument('a'); a.add_argument('b'); a.add_argument('--catalog',required=True)
    a=s.add_parser('plan'); a.add_argument('--catalog',required=True); a.add_argument('--out',required=True); a.add_argument('--qwen',action='store_true')
    for name in ('preview','simulate'):
        a=s.add_parser(name); a.add_argument('--catalog',required=True); a.add_argument('--plan',required=True); a.add_argument('--out',required=True); a.add_argument('--onnx',help='Controller ONNX opzionale, passa comunque attraverso safety')
    a=s.add_parser('dataset'); a.add_argument('--out',required=True); a.add_argument('--samples',type=int,default=256); a.add_argument('--seed',type=int,default=42)
    a=s.add_parser('train'); a.add_argument('--data',required=True); a.add_argument('--out',required=True); a.add_argument('--epochs',type=int,default=20)
    a=s.add_parser('export'); a.add_argument('--checkpoint',required=True); a.add_argument('--out',required=True)
    a=s.add_parser('infer'); a.add_argument('--model',required=True); a.add_argument('--data',required=True); a.add_argument('--out',required=True)
    a=s.add_parser('midi-serve'); a.add_argument('--seconds',type=float,default=60)
    a=s.add_parser('midi-fade'); a.add_argument('--seconds',type=float,default=8); a.add_argument('--setup-timeout',type=float,default=60)
    return p


def demo(out):
    from .audio import synth
    from .render import render
    out=Path(out); out.mkdir(parents=True,exist_ok=True)
    # Dedicated catalog only; reruns reproducible without stale tracks.
    db=out/'catalog.sqlite'
    if db.exists():
        db.unlink()
    truth=[]
    for i,(bpm,root) in enumerate([(120,0),(124,7),(128,2)]):
        truth.append(synth(out/f'track_{i+1}.wav',bpm,root,24,i))
        truth[-1]['path']=f'track_{i+1}.wav'
    save_json(out/'ground_truth.json',truth)
    with Catalog(db) as c:
        tracks=[c.add(out/t['path'],'numpy') for t in truth]
        planner=DeterministicPlanner(); plans=planner.plans(tracks); plan=planner.choose(plans)
        save_json(out/'analysis.json',tracks); save_json(out/'candidates.json',plans); save_json(out/'plan.json',plan)
        report,trace=render(c,plan,out/'preview.wav')
        save_json(out/'simulation.json',trace)
        save_json(out/'render.json',report)
    return dict(output=str(out),tracks=len(tracks),candidates=len(plans),preview=str(out/'preview.wav'),bpm_estimates=[round(t['bpm'],3) if t['bpm'] else None for t in tracks])


def run(args,cfg):
    cmd=args.command
    if cmd=='demo':
        return demo(args.out)
    if cmd=='synth':
        from .audio import synth
        return synth(args.output,args.bpm,args.root,args.seconds)
    if cmd=='analyze':
        from .analysis import analyze
        data=analyze(args.audio,args.backend or cfg['analysis_backend'])
        if args.out: save_json(args.out,data)
        return data
    if cmd=='scan':
        paths=[]
        for name in args.inputs:
            path=Path(name)
            paths.extend(sorted(path.rglob('*.wav')) if path.is_dir() else [path])
        if not paths:
            raise ValueError('Nessun WAV trovato')
        errors=[]; tracks=[]
        with Catalog(args.catalog) as c:
            for path in paths:
                try:
                    tracks.append(c.add(path,args.backend or cfg['analysis_backend']))
                except (ValueError,OSError) as e:
                    errors.append(dict(path=str(path),error=str(e)))
        result=dict(imported=len(tracks),tracks=tracks,errors=errors)
        if errors:
            print(json.dumps(result,indent=2,allow_nan=False))
            raise ValueError(f'Scan parziale: {len(errors)} file non importati; vedere JSON stdout')
        return result
    if cmd in ('catalog','compare','plan','preview','simulate'):
        with Catalog(args.catalog) as c:
            if cmd=='catalog': return c.all()
            if cmd=='compare':
                from .transitions import compatibility,candidates
                a,b=c.get(args.a),c.get(args.b)
                return dict(compatibility=compatibility(a,b),candidates=candidates(a,b))
            if cmd=='plan':
                planner=QwenPlanner(cfg['qwen_endpoint'],cfg['qwen_model'],cfg['qwen_timeout']) if args.qwen else DeterministicPlanner()
                plans=planner.plans(c.all()); plan=planner.choose(plans)
                plan=dict(plan,planner_status=getattr(planner,'last_status','deterministic'))
                save_json(args.out,plan)
                return plan
            plan=read_json(args.plan); controller=None
            if args.onnx:
                from .ml import OnnxController
                controller=OnnxController(args.onnx)
            if cmd=='preview':
                from .render import render
                report,trace=render(c,plan,args.out,controller=controller,hz=cfg['controller_hz'],safety=Safety(cfg['max_crossfader_slew'],cfg['feedback_timeout']))
                save_json(str(args.out)+'.json',report)
                return report
            trace=simulate(plan,c.get(plan['a']),c.get(plan['b']),hz=cfg['controller_hz'],controller=controller,safety=Safety(cfg['max_crossfader_slew'],cfg['feedback_timeout']))
            save_json(args.out,trace)
            return dict(frames=len(trace),final_crossfader=trace[-1]['crossfader'])
    if cmd in ('dataset','train','export','infer'):
        from . import ml
        if cmd=='dataset': return ml.dataset(args.out,args.samples,args.seed)
        if cmd=='train': return ml.train(args.data,args.out,args.epochs)
        if cmd=='export': return ml.export(args.checkpoint,args.out)
        import numpy as np
        data=ml.load_dataset(args.data)
        controller=ml.OnnxController(args.model)
        pred=controller.predict(data['x_val'][:1])
        result=dict(predictions=pred.tolist(),mse=float(np.mean((pred-data['y_val'][:1])**2)))
        save_json(args.out,result); return result
    if cmd.startswith('midi-'):
        from . import midi
        if cmd=='midi-serve': midi.serve(args.seconds)
        else: midi.fade(args.seconds,args.setup_timeout,Safety(cfg['max_crossfader_slew'],cfg['feedback_timeout']))
        return dict(status='finished')
    raise ValueError('Comando sconosciuto')


def main(argv=None):
    args=parser().parse_args(argv)
    try:
        handlers=[logging.StreamHandler()]
        if args.log:
            Path(args.log).parent.mkdir(parents=True,exist_ok=True)
            handlers.append(logging.FileHandler(args.log,encoding='utf-8'))
        logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(name)s %(message)s',handlers=handlers,force=True)
        result=run(args,load(args.config))
        print(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False))
        return 0
    except KeyboardInterrupt:
        logging.warning('Interrotto: controlli congelati; controllare Mixxx manualmente')
        return 130
    except (ValueError,OSError,ImportError,KeyError,TypeError,RuntimeError,sqlite3.Error) as e:
        logging.error('%s: %s',type(e).__name__,e)
        return 2
