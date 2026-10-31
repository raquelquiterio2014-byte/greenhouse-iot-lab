"""Configuration shared by desktop and headless entry points; no Tk dependency."""
from pathlib import Path
import json
import os
import secrets

ROOT=Path(__file__).resolve().parent.parent
DATA_DIR=Path(os.environ.get('GREENHOUSE_DATA_DIR',str(ROOT/'data'))).expanduser().resolve()


def load_settings():
    path=DATA_DIR/'settings.json';path.parent.mkdir(parents=True,exist_ok=True)
    defaults=dict(token=secrets.token_urlsafe(24),device='greenhouse-01',host='127.0.0.1',
                  port=8765,stale_seconds=180,temperature_high=38.,soil_low=35.)
    if path.exists():
        loaded=json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(loaded,dict):raise ValueError('settings.json must contain an object')
        defaults.update({k:v for k,v in loaded.items() if k in defaults})
    token=defaults['token']
    if not isinstance(token,str) or len(token)<16:raise ValueError('Invalid local token; restore settings.json')
    if defaults['host'] not in ('127.0.0.1','0.0.0.0'):raise ValueError('Invalid receiver host')
    if type(defaults['port']) is not int or not 1<=defaults['port']<=65535:raise ValueError('Invalid port')
    if defaults['device']!='greenhouse-01':raise ValueError('This build uses device greenhouse-01')
    for key,low,high in [('stale_seconds',10,86400),('temperature_high',-40,80),('soil_low',0,100)]:
        v=defaults[key]
        if type(v) not in (int,float) or not low<=v<=high:raise ValueError(f'Invalid {key}')
    path.write_text(json.dumps(defaults,indent=2),encoding='utf-8')
    return defaults
