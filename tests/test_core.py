import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import wave
import numpy as np
from dj.audio import synth, read_wav, write_wav, resample
from dj.analysis import fallback, analyze
from dj.catalog import Catalog
from dj.transitions import candidates, compatibility, validate_plan
from dj.planner import DeterministicPlanner,QwenPlanner
from dj.control import Safety,DeckState,Scheduler,simulate
from dj.midi import encode,Feedback
from dj.config import load
from dj.util import save_json,read_json
from dj.cli import main


class AudioTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
    def tearDown(self): self.tmp.cleanup()
    def test_roundtrip_stereo(self):
        x=np.array([[.5,-.5],[0,1]],np.float32)
        write_wav(self.root/'x.wav',x)
        y,sr=read_wav(self.root/'x.wav')
        self.assertEqual(sr,22050); np.testing.assert_allclose(x,y,atol=4e-5)
    def test_invalid_file(self):
        p=self.root/'bad.wav'; p.write_bytes(b'not audio')
        with self.assertRaises(ValueError): read_wav(p)
    def test_empty_wav(self):
        p=self.root/'empty.wav'
        with wave.open(str(p),'wb') as f: f.setparams((1,2,22050,0,'NONE','not compressed'))
        with self.assertRaises(ValueError): read_wav(p)
    def test_truncated(self):
        p=self.root/'short.wav'; write_wav(p,np.zeros(200))
        p.write_bytes(p.read_bytes()[:-4])
        with self.assertRaises(ValueError): read_wav(p)
    def test_nonfinite(self):
        for x in ([float('nan')],[float('inf')],[]):
            with self.assertRaises(ValueError): write_wav(self.root/'x.wav',x)
            with self.assertRaises(ValueError): fallback(np.array(x),22050)
    def test_silence(self):
        r=fallback(np.zeros(22050*4),22050)
        self.assertTrue(r['silent']); self.assertIsNone(r['bpm']); self.assertEqual(r['beats'],[])
    def test_tiny_valid_signal(self):
        r=fallback(np.ones(2)*.1,22050)
        self.assertIsNone(r['bpm']); self.assertIsNone(r['key'])
    def test_click_tempo(self):
        for bpm in (100,120,140):
            p=self.root/'s.wav'; synth(p,bpm=bpm,seconds=12)
            r=analyze(p,'numpy')
            self.assertLess(abs(r['bpm']-bpm),2)
            self.assertGreater(r['tempo_confidence'],.15)
            self.assertTrue(all(0<=b<12 for b in r['beats']))
            self.assertIsNone(r['vocals'])
    def test_antiphase(self):
        p=self.root/'s.wav'; synth(p,seconds=8)
        x,sr=read_wav(p); write_wav(p,np.column_stack((x[:,0],-x[:,0])),sr)
        self.assertFalse(analyze(p,'numpy')['silent'])
    def test_resample(self):
        y=resample(np.array([0.,1.,0.,1.]),2,4)
        self.assertEqual(len(y),8)
        with self.assertRaises(ValueError): resample(np.array([0]),0,4)
    def test_invalid_synth(self):
        for bpm in (0,float('nan'),float('inf')):
            with self.assertRaises(ValueError): synth(self.root/'x.wav',bpm=bpm)
    def test_pcm24_sign(self):
        p=self.root/'24.wav'
        with wave.open(str(p),'wb') as f:
            f.setparams((1,3,22050,0,'NONE','not compressed')); f.writeframes(bytes([0,0,128,255,255,127]))
        x,_=read_wav(p); self.assertEqual(float(x[0,0]),-1); self.assertGreater(x[1,0],.99)


class PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(); cls.root=Path(cls.tmp.name)
        cls.db=cls.root/'catalog.sqlite'
        with Catalog(cls.db) as c:
            synth(cls.root/'a.wav',120,0,12); synth(cls.root/'b.wav',124,7,12)
            cls.a=c.add(cls.root/'a.wav','numpy'); cls.b=c.add(cls.root/'b.wav','numpy')
        cls.plan=candidates(cls.a,cls.b)[0]
    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()
    def test_persistence_idempotent(self):
        with Catalog(self.db) as c:
            self.assertEqual(c.add(self.root/'a.wav','numpy')['id'],self.a['id'])
            self.assertEqual(len(c.all()),2)
            self.assertFalse(Path(c.get(self.a['id'])['path']).is_absolute())
    def test_modified_audio_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'x.wav'; synth(p,seconds=8)
            with Catalog(Path(d)/'x.sqlite') as c:
                t=c.add(p,'numpy')
                synth(p,bpm=130,seconds=8)
                with self.assertRaises(ValueError): c.audio_path(t)

    def test_empty_planner(self):
        with self.assertRaises(ValueError): DeterministicPlanner().choose([])
    def test_compatibility(self):
        self.assertTrue(compatibility(self.a,self.b)['eligible'])
        self.assertFalse(compatibility(self.a,self.a)['eligible'])
        self.assertFalse(compatibility(self.a,dict(self.b,silent=True))['eligible'])
        self.assertFalse(compatibility(self.a,dict(self.b,bpm=180))['eligible'])
    def test_plan_bounds(self):
        validate_plan(self.plan,self.a,self.b)
        for values in ({'duration':999},{'rate_b':float('nan')},{'start_b':12},{'a':'missing'}):
            with self.assertRaises(ValueError): validate_plan(dict(self.plan,**values),self.a,self.b)
    def test_simulation_endpoint(self):
        rows=simulate(self.plan,self.a,self.b)
        self.assertAlmostEqual(rows[-1]['crossfader'],1)
        self.assertFalse(rows[-1]['a']['playing']); self.assertTrue(rows[-1]['b']['playing'])
        self.assertTrue(all(-1<=r['crossfader']<=1 for r in rows))
        self.assertTrue(all(r['a']['playing'] or r['b']['playing'] for r in rows))
    def test_slow_safety_does_not_stop_a(self):
        rows=simulate(self.plan,self.a,self.b,safety=Safety(max_slew=.01))
        self.assertTrue(rows[-1]['a']['playing'])
    def test_preview(self):
        from dj.render import render
        with Catalog(self.db) as c: report,trace=render(c,self.plan,self.root/'preview.wav')
        x,sr=read_wav(self.root/'preview.wav')
        self.assertEqual(len(x),round(self.plan['duration']*sr))
        self.assertTrue(np.isfinite(x).all()); self.assertLessEqual(abs(x).max(),.981)
        self.assertGreater(np.sqrt(np.mean(x*x)),.01)
    def test_cli_plan_simulate(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(['plan','--catalog',str(self.db),'--out',str(self.root/'p.json')]),0)
            self.assertEqual(main(['simulate','--catalog',str(self.db),'--plan',str(self.root/'p.json'),'--out',str(self.root/'trace.json')]),0)
    def test_scan_empty_and_invalid(self):
        empty=self.root/'empty'; empty.mkdir(exist_ok=True)
        bad=self.root/'bad.wav'; bad.write_bytes(b'bad')
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(['scan',str(empty),'--catalog',str(self.db)]),2)
            self.assertEqual(main(['scan',str(bad),'--catalog',str(self.db)]),2)
    def test_qwen_network_timeout_fallback(self):
        with patch('urllib.request.OpenerDirector.open',side_effect=TimeoutError('test timeout')):
            q=QwenPlanner(timeout=.1)
            self.assertEqual(q.choose([self.plan]),self.plan)
            self.assertEqual(q.last_status,'deterministic_fallback')
    def test_qwen_valid_invalid_selection(self):
        for content,status in [('{"candidate":0}','qwen_selected'),('{"candidate":99}','deterministic_fallback'),('{"candidate":true}','deterministic_fallback'),('explanation','deterministic_fallback')]:
            response=json.dumps({'choices':[{'message':{'content':content}}]}).encode()
            with patch('urllib.request.OpenerDirector.open',return_value=io.BytesIO(response)):
                q=QwenPlanner(); self.assertEqual(q.choose([self.plan]),self.plan)
                self.assertEqual(q.last_status,status)
    def test_qwen_restrict_remote(self):
        with self.assertRaises(ValueError): QwenPlanner('https://example.com')


class SafetyTests(unittest.TestCase):
    def test_slew_and_clip(self):
        s=Safety(); self.assertAlmostEqual(s.crossfader(-1,100,.1),-.9)
        self.assertEqual(s.crossfader(1,100,.1),1)
    def test_nan_timeout(self):
        s=Safety()
        with self.assertRaises(ValueError): s.crossfader(0,float('nan'),.1)
        with self.assertRaises(TimeoutError): s.crossfader(0,1,.1,1)
        with self.assertRaises(ValueError): s.crossfader(0,1,-1)
    def test_deck(self):
        d=DeckState('a',1,.9,True,1,1,True); d.advance(.2)
        self.assertFalse(d.playing); self.assertEqual(d.position,1)
        with self.assertRaises(ValueError): DeckState(playing=True).validate()
    def test_scheduler_order(self):
        s=Scheduler(); values=[]
        s.at(.1,lambda:values.append(1)); s.at(.1,lambda:values.append(2)); s.run_due(.2)
        self.assertEqual(values,[1,2])
        with self.assertRaises(ValueError): s.run_due(.1)
    def test_midi_encoding(self):
        self.assertEqual(encode(-1,-1,1),0); self.assertEqual(encode(1,-1,1),127)
        with self.assertRaises(ValueError): encode(float('nan'))
        with self.assertRaises(ValueError): encode(2)
    def test_midi_complete_frames_timeout(self):
        f=Feedback(); f.receive(0,117,7,0)
        for ch,cc in f.REQUIRED: f.receive(ch,cc,127,0)
        f.receive(0,119,7,0)
        frame,age=f.snapshot(.2); self.assertEqual(len(frame),11)
        with self.assertRaises(TimeoutError): f.snapshot(1)
    def test_midi_incomplete_wrong_sequence(self):
        for wrong in (False,True):
            f=Feedback(); f.receive(0,117,1,0)
            if wrong:
                for ch,cc in f.REQUIRED: f.receive(ch,cc,127,0)
            f.receive(0,119,2 if wrong else 1,0)
            with self.assertRaises(TimeoutError): f.snapshot(.1)
    def test_invalid_config_json(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'x.json'
            for value in ({'bad':1},{'controller_hz':0},{'feedback_timeout':float('nan')}):
                p.write_text(json.dumps(value))
                with self.assertRaises(ValueError): load(p)
    def test_atomic_json_rejects_nan(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'x.json'; save_json(p,{'ok':1})
            with self.assertRaises(ValueError): save_json(p,{'x':float('nan')})
            self.assertEqual(read_json(p),{'ok':1})

if __name__=='__main__': unittest.main()
