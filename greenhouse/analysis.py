"""Snapshot-based trend screening. Heuristics are not trained predictive models."""
from datetime import datetime,timezone,timedelta
from dataclasses import replace
from pathlib import Path
import hashlib,json,math,statistics,uuid
from .core import Reading,Simulator,utcnow
from .sensors import Calibration

METRICS={'temperature':('°C',2.),'humidity':('percentage points RH',8.),
         'soil_moisture':('relative index points',10.),'light_lux':('lux',500.)}
CHECKS={
 'CHECK_SENSOR_PLACEMENT':'Check sensor placement, shielding and exposure with a responsible person.',
 'VERIFY_CALIBRATION':'Review the installed sensor calibration references and verification record.',
 'CHECK_TIMESTAMP':'Verify measurement timestamps, sampling cadence and communication history.',
 'REVIEW_LOCAL_CONDITIONS':'Ask a person to check local greenhouse conditions before interpreting the change.',
 'COLLECT_MORE_DATA':'Collect more valid observations before extending this analysis.',
 'ASK_HUMAN_REVIEW':'Request human review; this report authorizes no equipment action.'}
LIMITATIONS=['NO_CROP_CONTEXT','NO_FIELD_VALIDATION','NO_ACTUATION']


def strict_json(text):
    def invalid_constant(value):raise ValueError('Non-finite JSON constant')
    def pairs(items):
        out={}
        for key,value in items:
            if key in out:raise ValueError('Duplicate JSON key')
            out[key]=value
        return out
    return json.loads(text,parse_constant=invalid_constant,object_pairs_hook=pairs)


def digest(rows):
    data=json.dumps(rows,sort_keys=True,separators=(',',':'),allow_nan=False)
    return hashlib.sha256(data.encode()).hexdigest()


def analyze_rows(rows,source,now=None,stale_seconds=180,temperature_high=38.,soil_low=35.,
                 input_kind='stored_history',sensor_status='UNKNOWN',window_minutes=30):
    now=now or utcnow()
    if source not in ('demo','test','real'):raise ValueError('Unknown source')
    if not 10<=stale_seconds<=86400:raise ValueError('Invalid freshness threshold')
    for v in (temperature_high,soil_low):
        if type(v) not in (int,float) or not math.isfinite(v):raise ValueError('Invalid monitoring threshold')
    report=dict(version='4.0.0',run_id=uuid.uuid4().hex,created_at=now.isoformat(),cutoff=now.isoformat(),
        source=source,input_kind=input_kind,synthetic=source!='real',status='BLOCKED',human_review_required=True,
        authorization='NO_ACTION_AUTHORIZED',hardware_validation='PENDING',gate_reasons=[],metrics={},findings=[],
        observations=[],excluded_rows=0,config=dict(stale_seconds=stale_seconds,temperature_high=temperature_high,
        soil_low=soil_low,min_samples=5,min_span_seconds=20,window_minutes=window_minutes,
        trend_method='ordinary_least_squares_per_minute',jump_method='median_MAD_last_vs_previous'),
        limitations=LIMITATIONS+(['SYNTHETIC_DATA'] if source!='real' else []),
        ai=dict(engine='NOT_REQUESTED',reason='LOCAL_ANALYSIS_ONLY',attempts=0))
    def block(reason):
        if reason not in report['gate_reasons']:report['gate_reasons'].append(reason)
    normalized=[]
    for row in rows:
        try:
            if row['source']!=source:raise ValueError('mixed source')
            time=datetime.fromisoformat(row['measured_at'])
            if time.tzinfo is None:raise ValueError('missing timezone')
            if time>now:block('FUTURE_TIMESTAMP')
            for key in METRICS:
                val=row[key]
                if type(val) not in (int,float) or not math.isfinite(val):raise ValueError('invalid metric')
            if not -40<=row['temperature']<=80 or not 0<=row['humidity']<=100 or not 0<=row['soil_moisture']<=100 or not 0<=row['light_lux']<=54612.5:
                raise ValueError('outside selected sensor range')
            if row.get('quality')=='OK' and row.get('schema_version')==2:
                cal=Calibration(**strict_json(row['calibration_snapshot'])).validate()
                if not cal.confirmed or cal.revision!=row['calibration_id']:raise ValueError('Unverified calibration')
                raw=row['soil_raw'];light=row['light_raw']
                if type(raw) not in (int,float) or not math.isfinite(raw) or not 0<raw<4095:raise ValueError('Invalid raw ADC')
                index,_,flags=cal.soil_index(raw)
                if flags or abs(index-row['soil_moisture'])>.05:raise ValueError('Soil provenance mismatch')
                if type(light) is not int or not 0<=light<65535 or abs(light/1.2-row['light_lux'])>.05:raise ValueError('Light provenance mismatch')
                for metric,offset in [('temperature',cal.temperature_offset),('humidity',cal.humidity_offset)]:
                    raw_dht=row[metric+'_raw']
                    if type(raw_dht) not in (int,float) or not math.isfinite(raw_dht) or abs(round(raw_dht+offset,1)-row[metric])>.05:
                        raise ValueError('DHT provenance mismatch')
            normalized.append((time,dict(row)))
        except (ValueError,KeyError,TypeError,OverflowError):block('MALFORMED_OR_MIXED_INPUT')
    normalized.sort(key=lambda x:x[0])
    selected=[r for t,r in normalized if t>=now-timedelta(minutes=window_minutes)]
    report['excluded_rows']=len(normalized)-len(selected)
    report['observations']=selected
    report['input_sha256']=digest(selected)
    report['sample_count']=len(selected)
    if not selected:block('NO_RECENT_DATA')
    if sensor_status=='FAULT':block('SENSOR_FAULT_HEARTBEAT')
    if selected:
        if len({r.get('device_id') for r in selected})!=1:block('MIXED_DEVICES')
        latest=selected[-1]
        if (now-datetime.fromisoformat(latest['measured_at'])).total_seconds()>stale_seconds:block('STALE_DATA')
        if latest.get('quality')!='OK' or latest.get('schema_version')!=2:block('LATEST_MEASUREMENT_QUALITY')
        # Never bridge a quality failure or calibration transition in a trend.
        trailing=[]
        for row in reversed(selected):
            if row.get('quality')!='OK' or row.get('schema_version')!=2 or row.get('calibration_id')!=latest.get('calibration_id'):break
            trailing.append(row)
        usable=list(reversed(trailing));report['excluded_rows']+=len(selected)-len(usable)
        report['usable_sample_count']=len(usable)
        if len(usable)<5:block('INSUFFICIENT_VALID_SAMPLES')
        if usable:
            stamps=[datetime.fromisoformat(r['measured_at']) for r in usable]
            span=(stamps[-1]-stamps[0]).total_seconds()
            if span<20:block('INSUFFICIENT_TIME_SPAN')
            gaps=[(b-a).total_seconds() for a,b in zip(stamps,stamps[1:])]
            positive=[x for x in gaps if x>0]
            if len(positive)!=len(gaps):block('DUPLICATE_MEASUREMENT_TIMES')
            if gaps and max(gaps)>max(180,5*statistics.median(positive or [0])):block('LARGE_SAMPLING_GAP')
    else:usable=[]
    if report['gate_reasons']:return report
    report['status']='SCREENED';report['human_review_required']=source=='real'
    def finding(code,metric,value,note):
        report['findings'].append(dict(id=f"E{len(report['findings'])+1:02d}",code=code,metric=metric,value=value,note=note))
    times=[(datetime.fromisoformat(r['measured_at'])-datetime.fromisoformat(usable[0]['measured_at'])).total_seconds()/60 for r in usable]
    xmean=statistics.mean(times);den=sum((x-xmean)**2 for x in times)
    for key,(unit,floor) in METRICS.items():
        vals=[float(r[key]) for r in usable];average=statistics.mean(vals)
        slope=sum((x-xmean)*(y-average) for x,y in zip(times,vals))/den
        delta=vals[-1]-vals[0];prior=vals[:-1];med=statistics.median(prior)
        mad=statistics.median(abs(x-med) for x in prior)
        jump_limit=max(floor,6*1.4826*mad)
        report['metrics'][key]=dict(unit=unit,n=len(vals),latest=vals[-1],minimum=min(vals),maximum=max(vals),
            mean=average,delta=delta,slope_per_minute=slope,span_seconds=times[-1]*60,jump_limit=jump_limit)
        if abs(vals[-1]-med)>jump_limit:
            finding('ABRUPT_CHANGE',key,vals[-1]-med,'Last value differs from the prior median; verify the reading before inferring a cause.')
        if abs(delta)>=floor and abs(slope)>=floor/30:
            finding('RISING' if slope>0 else 'FALLING',key,slope,'Descriptive change in this snapshot; not a forecast or agricultural diagnosis.')
    if usable[-1]['temperature']>temperature_high:
        finding('ABOVE_LIMIT','temperature',usable[-1]['temperature'],'Above the configured demonstration/monitoring threshold, not a crop safety limit.')
    if usable[-1]['soil_moisture']<soil_low:
        finding('BELOW_LIMIT','soil_moisture',usable[-1]['soil_moisture'],'Below the configured relative soil index threshold; physical watering is not authorized.')
    if not report['findings']:finding('NO_FLAG','window',len(usable),'No configured screening flag in this window. This does not prove optimal growing conditions.')
    if any(f['code']!='NO_FLAG' for f in report['findings']):
        report['status']='REVIEW_REQUIRED';report['human_review_required']=True
    report['suggested_checks']=list(CHECKS)
    return report


def validate_ai_selection(value,report):
    if not isinstance(value,dict) or set(value)!={'priority_evidence','check_codes','limitations'}:raise ValueError('Unexpected AI fields')
    allowed={f['id'] for f in report['findings']}
    for key,choices,maximum in [('priority_evidence',allowed,12),('check_codes',set(CHECKS),6),
                                ('limitations',set(report['limitations']),6)]:
        seq=value[key]
        if not isinstance(seq,list) or not 1<=len(seq)<=maximum or any(type(x) is not str for x in seq):raise ValueError('Invalid selection list')
        if len(set(seq))!=len(seq) or not set(seq)<=choices:raise ValueError('Invented or duplicate AI selection')
    if not set(report['limitations'])<=set(value['limitations']):raise ValueError('AI omitted required limitations')
    # No arbitrary model prose, numbers, commands or new diagnoses reach the report.
    return dict(priority_evidence=value['priority_evidence'],check_codes=value['check_codes'],limitations=value['limitations'])


def public_summary(report):
    """Only aggregates and controlled evidence, never IDs, calibration notes or secrets."""
    return dict(source=report['source'],synthetic=report['synthetic'],status=report['status'],
        sample_count=report.get('usable_sample_count',0),metrics=report['metrics'],findings=report['findings'],
        allowed_checks=CHECKS,required_limitations=report['limitations'],authorization='NO_ACTION_AUTHORIZED')


class AnalysisService:
    def __init__(self,store):
        self.store=store
        with store.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS analysis_runs(run_id TEXT PRIMARY KEY,created_at TEXT,source TEXT,status TEXT,engine TEXT,report_json TEXT)')

    def run(self,source,rows=None,gateway=None,use_gemini=False,**kwargs):
        report=analyze_rows(self.store.recent(source,500) if rows is None else rows,source,**kwargs)
        if use_gemini:
            if report['status']=='BLOCKED':report['ai']=dict(engine='BLOCKED',reason='QUALITY_GATE',attempts=0)
            elif gateway is None:report['ai']=dict(engine='LOCAL_FALLBACK',reason='MISSING_GATEWAY',attempts=0)
            else:
                try:result=gateway.select(public_summary(report))
                except Exception:result=dict(ok=False,reason='GATEWAY_ERROR',attempts=0)
                if not isinstance(result,dict):result=dict(ok=False,reason='INVALID_MODEL_OUTPUT',attempts=0)
                try:
                    if result.get('ok') is not True:raise ValueError(result.get('reason','PROVIDER_ERROR'))
                    selection=validate_ai_selection(result['selection'],report)
                    report['ai']=dict(engine='GEMINI',reason='VALIDATED_SELECTION',attempts=result.get('attempts',1),
                        requested_model=result.get('requested_model'),returned_model=result.get('returned_model'),selection=selection)
                except (ValueError,KeyError,TypeError):
                    report['ai']=dict(engine='LOCAL_FALLBACK',reason='INVALID_MODEL_OUTPUT' if result.get('ok') else result.get('reason','PROVIDER_ERROR'),attempts=result.get('attempts',0))
        # Deterministic status, all findings and authorization are never replaced by AI.
        with self.store.connect() as db:
            db.execute('INSERT INTO analysis_runs VALUES(?,?,?,?,?,?)',(report['run_id'],report['created_at'],source,
                report['status'],report['ai']['engine'],json.dumps(report,allow_nan=False)))
        return report

    def history(self,source,limit=20):
        with self.store.connect() as db:
            return [dict(r) for r in db.execute('SELECT run_id,created_at,source,status,engine FROM analysis_runs WHERE source=? ORDER BY rowid DESC LIMIT ?',(source,limit))]


def synthetic_case(name,now=None):
    now=now or utcnow();sim=Simulator(seed=7);rows=[]
    for i in range(12):
        r=sim.sample(advance=False)
        temp=24.8;soil=38.
        if name=='Rising heat':temp=30+i*.9
        if name=='Dry soil':soil=45-i*1.4
        if name=='Temperature spike' and i==11:temp=34.
        age=600 if name=='Stale readings' else 0
        stamp=now-timedelta(seconds=(11-i)*5+age)
        r=replace(r,temperature=round(temp,1),temperature_raw=round(temp,1),soil_moisture=soil,
            soil_raw=3000-soil*18,soil_mv=(3000-soil*18)/4095*3300,soil_unclamped=soil,
            measured_at=stamp.isoformat(),received_at=stamp.isoformat(),sample_id=f'analysis-case-{name.replace(" ","-")}:{i}')
        if name=='Uncalibrated soil':r=replace(r,quality='CALIBRATION_REQUIRED')
        if name=='Saturated light':r=replace(r,light_raw=65535,light_lux=54612.5,quality='LIGHT_SATURATED')
        from dataclasses import asdict
        rows.append(asdict(r))
    return rows


def format_report(report):
    lines=[f"GREENHOUSE V4 | {report['status']}",f"Source: {report['source']} | Input: {report['input_kind']}",
        f"Snapshot cutoff (UTC): {report['cutoff']}",f"Analysis engine: {report['ai']['engine']} ({report['ai']['reason']})",
        'Authorization: NO ACTION AUTHORIZED','Hardware validation: PENDING',
        'Synthetic data' if report['synthetic'] else 'Physical input route; field accuracy is unverified',
        f"Human review required: {report['human_review_required']}"]
    if report['gate_reasons']:lines+=['','ANALYSIS WITHHELD']+report['gate_reasons']
    for key,m in report['metrics'].items():
        lines+=['',f"{key} | last {m['latest']:.2f} | delta {m['delta']:+.2f} {m['unit']}",
                f"  Linear slope {m['slope_per_minute']:+.3f} {m['unit']}/min over {m['span_seconds']:.0f} s"]
    lines+=['','EVIDENCE (all deterministic findings are retained)']
    lines += [f"{f['id']} | {f['metric']} | {f['code']} | {f['note']}" for f in report['findings']]
    selection=report['ai'].get('selection')
    if selection:
        lines+=['','GEMINI-SELECTED REVIEW ORDER: '+', '.join(selection['priority_evidence'])]
        lines += [CHECKS[x] for x in selection['check_codes']]
        lines+=['Model selects existing evidence and check templates; it cannot issue actuator commands.']
    elif report['status']!='BLOCKED':
        lines+=['','LOCAL SUGGESTED CHECKS']+[CHECKS[x] for x in ('CHECK_SENSOR_PLACEMENT','VERIFY_CALIBRATION','ASK_HUMAN_REVIEW')]
    lines+=['','LIMITATIONS: '+', '.join(report['limitations']),
        'Heuristic screening, not a trained anomaly model, crop diagnosis, prediction or irrigation instruction.',
        'This report refers only to the captured snapshot; later readings require another explicit analysis.']
    return '\n'.join(lines)
