"""A local LLM may choose a validated candidate ID, never issue controls."""
import json
import logging
import urllib.request
import urllib.parse
from .transitions import candidates
from .util import finite

LOG = logging.getLogger(__name__)


class DeterministicPlanner:
    def plans(self, tracks):
        plans = [p for a in tracks for b in tracks for p in candidates(a,b)]
        return sorted(plans, key=lambda p: (-p['score'], p['a'], p['b'], p['duration']))

    def choose(self, plans):
        if not plans:
            raise ValueError('Nessuna transizione ammissibile nel catalogo')
        return plans[0]


class QwenPlanner(DeterministicPlanner):
    def __init__(self, endpoint='http://127.0.0.1:8000/v1/chat/completions', model='Qwen/Qwen3-4B', timeout=10):
        u = urllib.parse.urlsplit(endpoint)
        if u.scheme != 'http' or u.hostname not in ('127.0.0.1','localhost','::1') or u.username or u.password:
            raise ValueError('Qwen endpoint deve essere HTTP loopback locale')
        self.endpoint, self.model = endpoint, model
        self.timeout = finite(timeout, 'timeout', .1, 60)
        self.last_status = 'not_called'

    def choose(self, plans):
        fallback = super().choose(plans)
        subset = plans[:20]
        summary = [dict(candidate=i, score=p['score'], duration=p['duration'], confidence=p['confidence']) for i,p in enumerate(subset)]
        body = dict(model=self.model, temperature=0, max_tokens=64, messages=[
            dict(role='system',content='Select one DJ transition candidate. Return only JSON {"candidate": integer}. Do not issue controls.'),
            dict(role='user',content=json.dumps(summary))])
        try:
            # Explicitly forbid redirects away from loopback.
            class NoRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, *args, **kwargs):
                    return None
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
            req = urllib.request.Request(self.endpoint, data=json.dumps(body).encode(), headers={'Content-Type':'application/json'})
            with opener.open(req, timeout=self.timeout) as response:
                raw = response.read(65537)
            if len(raw)>65536:
                raise ValueError('Risposta troppo grande')
            message = json.loads(raw)['choices'][0]['message']['content']
            choice = json.loads(message)['candidate']
            if type(choice) is not int or not 0 <= choice < len(subset):
                raise ValueError('ID candidato non valido')
            self.last_status = 'qwen_selected'
            return subset[choice]
        except (OSError, ValueError, KeyError, IndexError, TypeError) as e:
            self.last_status = 'deterministic_fallback'
            LOG.warning('Planner Qwen non disponibile/valido, fallback: %s', e)
            return fallback
