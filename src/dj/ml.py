"""Real GRU training on rule imitation; not a trained musical DJ."""
from pathlib import Path
import numpy as np
from .util import finite, save_json

FEATURES=['progress','energy_a','energy_b','phase_error','tempo_error']
STEPS=32
HIDDEN=16


def dataset(path,n=256,seed=42):
    n=int(finite(n,'n',10,100000))
    rng=np.random.default_rng(seed)
    x=np.zeros((n,STEPS,5),np.float32)
    # Independent trajectories, speed/noise and energies. Held-out whole sequences.
    for i in range(n):
        p=np.linspace(0,1,STEPS)**rng.uniform(.7,1.5)
        x[i,:,0]=p
        x[i,:,1:3]=rng.uniform(.03,.4,(1,2))
        x[i,:,3]=rng.uniform(-.1,.1,STEPS)
        x[i,:,4]=rng.uniform(-.08,.08)
    y=(2*x[:,:,:1]-1).astype(np.float32)
    split=max(1,int(n*.8))
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    with open(path,'wb') as f:
        np.savez_compressed(f,x_train=x[:split],y_train=y[:split],x_val=x[split:],y_val=y[split:])
    info=dict(seed=seed,n=n,train=split,validation=n-split,features=FEATURES,
              target='crossfader [-1,1] from deterministic rule; synthetic behavioral cloning only')
    save_json(str(path)+'.json',info)
    return info


def model():
    import torch
    class GRUController(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.gru=torch.nn.GRU(5,HIDDEN,batch_first=True)
            self.head=torch.nn.Linear(HIDDEN,1)
        def forward(self,x,h):
            out,hout=self.gru(x,h)
            return torch.tanh(self.head(out)),hout
    return GRUController()


def load_dataset(path):
    with np.load(path,allow_pickle=False) as data:
        arrays={k:np.array(data[k],dtype=np.float32) for k in ('x_train','y_train','x_val','y_val')}
    for split in ('train','val'):
        x,y=arrays['x_'+split],arrays['y_'+split]
        if x.ndim!=3 or x.shape[1:]!=(STEPS,5) or len(x)==0 or y.shape!=(len(x),STEPS,1):
            raise ValueError('Dataset: forma errata/vuoto')
        if not np.isfinite(x).all() or not np.isfinite(y).all() or np.max(abs(y))>1:
            raise ValueError('Dataset non finito o target fuori range')
        if np.any(x[:,:,0]<0) or np.any(x[:,:,0]>1) or np.any(x[:,:,1:3]<0) or np.any(x[:,:,1:3]>1) or np.max(abs(x[:,:,3:]))>1:
            raise ValueError('Feature fuori range')
    return arrays


def train(data_path,checkpoint,epochs=20,seed=42):
    import torch
    epochs=int(finite(epochs,'epochs',1,10000))
    torch.manual_seed(seed)
    torch.set_num_threads(1)
    data=load_dataset(data_path)
    x=torch.from_numpy(data['x_train']); y=torch.from_numpy(data['y_train'])
    xv=torch.from_numpy(data['x_val']); yv=torch.from_numpy(data['y_val'])
    net=model()
    opt=torch.optim.Adam(net.parameters(),lr=.01)
    history=[]
    for epoch in range(epochs):
        net.train()
        losses=[]
        for indices in torch.randperm(len(x)).split(32):
            opt.zero_grad()
            pred,_=net(x[indices],torch.zeros(1,len(indices),HIDDEN))
            loss=torch.nn.functional.mse_loss(pred,y[indices])
            loss.backward()
            torch.nn.utils.clip_grad_norm_(net.parameters(),1)
            opt.step(); losses.append(float(loss.detach()))
        net.eval()
        with torch.no_grad():
            pred,_=net(xv,torch.zeros(1,len(xv),HIDDEN))
            validation=float(torch.nn.functional.mse_loss(pred,yv))
        history.append(dict(epoch=epoch+1,train_mse=float(np.mean(losses)),validation_mse=validation))
    Path(checkpoint).parent.mkdir(parents=True,exist_ok=True)
    torch.save({'state_dict':net.state_dict(),'features':FEATURES,'steps':STEPS,'hidden':HIDDEN},checkpoint)
    result=dict(seed=seed,epochs=epochs,history=history,validation_mse=history[-1]['validation_mse'],
                limitation='Only imitation of synthetic crossfader ramps, not musical competence')
    save_json(str(checkpoint)+'.metrics.json',result)
    return result


def export(checkpoint,output):
    import torch
    import onnx
    import onnxruntime as ort
    net=model()
    saved=torch.load(checkpoint,map_location='cpu',weights_only=True)
    net.load_state_dict(saved['state_dict']); net.eval()
    x=torch.zeros(1,STEPS,5); x[0,:,0]=torch.linspace(0,1,STEPS)
    h=torch.zeros(1,1,HIDDEN)
    Path(output).parent.mkdir(parents=True,exist_ok=True)
    # Fixed shape, explicit h0. Opt-in legacy exporter avoids Dynamo GRU gaps.
    torch.onnx.export(net,(x,h),str(output),input_names=['features','h0'],
                      output_names=['crossfader','h1'],opset_version=17,dynamo=False)
    onnx.checker.check_model(onnx.load(str(output)))
    session=ort.InferenceSession(str(output),providers=['CPUExecutionProvider'])
    actual=session.run(None,{'features':x.numpy(),'h0':h.numpy()})[0]
    with torch.no_grad():
        expected=net(x,h)[0].numpy()
    error=float(np.max(abs(actual-expected)))
    if error > 1e-5:
        raise ValueError(f'ONNX parity fallita: {error}')
    report=dict(max_absolute_error=error,tolerance=1e-5,input_shape=[1,STEPS,5],hidden_shape=[1,1,HIDDEN],opset=17)
    save_json(str(output)+'.json',report)
    return report


class OnnxController:
    def __init__(self,path):
        import onnxruntime as ort
        options=ort.SessionOptions(); options.intra_op_num_threads=1
        self.session=ort.InferenceSession(str(path),sess_options=options,providers=['CPUExecutionProvider'])
        self.history=[]

    def predict(self,features):
        x=np.asarray(features,dtype=np.float32)
        if x.shape!=(1,STEPS,5) or not np.isfinite(x).all():
            raise ValueError('ONNX features devono essere finite [1,32,5]')
        out=self.session.run(['crossfader'],{'features':x,'h0':np.zeros((1,1,HIDDEN),np.float32)})[0]
        if out.shape!=(1,STEPS,1) or not np.isfinite(out).all():
            raise ValueError('Output ONNX non valido')
        return np.clip(out,-1,1)

    def target(self,progress,energy_a=0,energy_b=0,phase_error=0,tempo_error=0):
        row=[finite(progress,'progress',0,1),finite(energy_a,'energy_a',0,1),finite(energy_b,'energy_b',0,1),finite(phase_error,'phase_error',-1,1),finite(tempo_error,'tempo_error',-1,1)]
        self.history.append(row); self.history=self.history[-STEPS:]
        context=[self.history[0]]*(STEPS-len(self.history))+self.history
        predicted=float(self.predict(np.array([context],np.float32))[0,-1,0])
        # Guardrails: monotonic transition scheduling and exact endpoint override.
        # The learned prediction only perturbs the rule by <=0.1, then Safety applies slew.
        rule=-1+2*progress
        return rule if progress in (0,1) else float(np.clip(predicted,rule-.1,rule+.1))
