from .util import read_json, finite

DEFAULT=dict(analysis_backend='auto',controller_hz=50,max_crossfader_slew=1.0,
             feedback_timeout=.5,qwen_endpoint='http://127.0.0.1:8000/v1/chat/completions',
             qwen_model='Qwen/Qwen3-4B',qwen_timeout=10)


def load(path=None):
    config=dict(DEFAULT)
    if path:
        supplied=read_json(path)
        if not isinstance(supplied,dict) or set(supplied)-set(DEFAULT):
            raise ValueError('Config non valida o chiavi sconosciute')
        config.update(supplied)
    if config['analysis_backend'] not in ('auto','numpy','essentia'):
        raise ValueError('Backend non valido')
    for key,lo,hi in [('controller_hz',10,100),('max_crossfader_slew',.01,10),('feedback_timeout',.05,10),('qwen_timeout',.1,60)]:
        config[key]=finite(config[key],key,lo,hi)
    return config
