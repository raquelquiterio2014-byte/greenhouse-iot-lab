"""Optional Gemini REST adapter. Bounded retries; no tools, commands or raw notes."""
import json,os,re,time
from urllib.error import HTTPError,URLError
from urllib.request import Request,urlopen
from .analysis import strict_json,CHECKS


def request_gemini(model,key,body):
    request=Request('https://generativelanguage.googleapis.com/v1beta/models/'+model+':generateContent',
        data=json.dumps(body,allow_nan=False).encode(),headers={'Content-Type':'application/json','x-goog-api-key':key})
    try:
        with urlopen(request,timeout=12) as response:
            raw=response.read(131073)
            if len(raw)>131072:return 0,{}
            return response.status,strict_json(raw.decode())
    except HTTPError as exc:return exc.code,{}
    except (OSError,URLError,ValueError,UnicodeDecodeError):return 0,{}


class GeminiGateway:
    def __init__(self,key=None,model=None,transport=request_gemini,sleep=time.sleep):
        self.key=key if key is not None else os.environ.get('GEMINI_API_KEY','')
        self.model=model or os.environ.get('GEMINI_MODEL','gemini-2.5-flash')
        if not re.fullmatch(r'[A-Za-z0-9._-]{1,80}',self.model):raise ValueError('Invalid Gemini model identifier')
        self.transport,self.sleep=transport,sleep

    def select(self,summary):
        if not self.key:return dict(ok=False,reason='MISSING_KEY',attempts=0)
        schema={'type':'OBJECT','required':['priority_evidence','check_codes','limitations'],
            'properties':{
                'priority_evidence':{'type':'ARRAY','items':{'type':'STRING','enum':[f['id'] for f in summary['findings']]}},
                'check_codes':{'type':'ARRAY','items':{'type':'STRING','enum':list(CHECKS)}},
                'limitations':{'type':'ARRAY','items':{'type':'STRING','enum':summary['required_limitations']}}}}
        prompt=('You assist a human reviewing an educational greenhouse monitoring snapshot. '
                'Select an order of the supplied evidence IDs and suitable existing verification check codes. '
                'Include ALL required limitations. Never create evidence, numbers, diagnoses, actions or new fields. '
                'You cannot authorize or control equipment. Do not treat synthetic data as field validation. '
                'Return only the schema-conforming JSON selection. Snapshot: '+json.dumps(summary,allow_nan=False))
        body={'contents':[{'role':'user','parts':[{'text':prompt}]}],
            'generationConfig':{'responseMimeType':'application/json','responseSchema':schema,'maxOutputTokens':4096}}
        for attempt in (1,2):
            try:code,response=self.transport(self.model,self.key,body)
            except Exception:code,response=0,{}
            if code==200:
                try:
                    candidate=response['candidates'][0]
                    if candidate.get('finishReason')!='STOP':raise ValueError('Incomplete output')
                    parts=candidate['content']['parts']
                    text=''.join(p['text'] for p in parts if isinstance(p,dict) and 'text' in p and not p.get('thought'))
                    if len(text)>16000:raise ValueError('Oversized selection')
                    selection=strict_json(text)
                    returned=response.get('modelVersion')
                    if returned is not None and (not isinstance(returned,str) or len(returned)>120):raise ValueError('Invalid model metadata')
                    return dict(ok=True,selection=selection,attempts=attempt,requested_model=self.model,returned_model=returned)
                except (ValueError,KeyError,IndexError,TypeError):
                    return dict(ok=False,reason='INVALID_MODEL_OUTPUT',attempts=attempt)
            if code not in (0,429,500,502,503,504) or attempt==2:
                return dict(ok=False,reason=f'HTTP_{code}' if code else 'NETWORK_UNAVAILABLE',attempts=attempt)
            self.sleep(1)
