import copy,json,tempfile,unittest
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from greenhouse.analysis import (analyze_rows,synthetic_case,AnalysisService,public_summary,
    validate_ai_selection,strict_json,format_report)
from greenhouse.core import Store,utcnow
from greenhouse.llm_gateway import GeminiGateway


def selection(summary):
    return dict(priority_evidence=[f['id'] for f in summary['findings']],
                check_codes=['CHECK_SENSOR_PLACEMENT','ASK_HUMAN_REVIEW'],limitations=summary['required_limitations'])


class AnalysisTests(unittest.TestCase):
    def setUp(self):self.now=utcnow();self.rows=synthetic_case('Normal',self.now)
    def analyze(self,rows=None,**kw):return analyze_rows(self.rows if rows is None else rows,'demo',now=self.now,**kw)

    def test_normal_is_not_crop_safety_claim(self):
        r=self.analyze();self.assertEqual(r['status'],'SCREENED')
        self.assertEqual(r['findings'][0]['code'],'NO_FLAG');self.assertEqual(r['authorization'],'NO_ACTION_AUTHORIZED')
        self.assertIn('does not prove optimal',r['findings'][0]['note'])

    def test_rising_heat_slope_and_configured_threshold(self):
        r=self.analyze(synthetic_case('Rising heat',self.now))
        self.assertEqual(r['status'],'REVIEW_REQUIRED');self.assertTrue(r['human_review_required'])
        self.assertAlmostEqual(r['metrics']['temperature']['slope_per_minute'],10.8)
        self.assertIn('ABOVE_LIMIT',[f['code'] for f in r['findings']])

    def test_dry_and_spike_flags(self):
        dry=self.analyze(synthetic_case('Dry soil',self.now))
        self.assertIn('BELOW_LIMIT',[f['code'] for f in dry['findings']])
        spike=self.analyze(synthetic_case('Temperature spike',self.now))
        self.assertIn('ABRUPT_CHANGE',[f['code'] for f in spike['findings']])

    def test_stale_uncalibrated_saturated_examples_block(self):
        for name in ['Stale readings','Uncalibrated soil','Saturated light']:
            with self.subTest(name=name):self.assertEqual(self.analyze(synthetic_case(name,self.now))['status'],'BLOCKED')

    def test_empty_and_short_window_block(self):
        for rows in [[],self.rows[:3],self.rows[-4:]]:
            with self.subTest(n=len(rows)):self.assertEqual(self.analyze(rows)['status'],'BLOCKED')
        rows=copy.deepcopy(self.rows)
        for i,row in enumerate(rows):row['measured_at']=(self.now-timedelta(seconds=11-i)).isoformat()
        self.assertIn('INSUFFICIENT_TIME_SPAN',self.analyze(rows)['gate_reasons'])

    def test_future_mixed_source_and_invalid_numbers_block(self):
        for update in [dict(measured_at=(self.now+timedelta(seconds=1)).isoformat()),
                       dict(source='real'),dict(temperature=float('nan')),dict(temperature=90)]:
            rows=copy.deepcopy(self.rows);rows[-1].update(update)
            with self.subTest(update=update):self.assertEqual(self.analyze(rows)['status'],'BLOCKED')

    def test_missing_provenance_and_false_calibration_block(self):
        for update in [dict(calibration_snapshot='{}'),dict(calibration_id='wrong'),dict(soil_moisture=50),
                       dict(temperature_raw=20),dict(light_raw=100)]:
            rows=copy.deepcopy(self.rows);rows[-1].update(update)
            with self.subTest(update=update):self.assertEqual(self.analyze(rows)['status'],'BLOCKED')

    def test_duplicate_times_and_large_gap_block(self):
        rows=copy.deepcopy(self.rows);rows[-1]['measured_at']=rows[-2]['measured_at']
        self.assertIn('DUPLICATE_MEASUREMENT_TIMES',self.analyze(rows)['gate_reasons'])
        rows=copy.deepcopy(self.rows[:6])
        for row,age in zip(rows,[900,895,890,885,880,0]):row['measured_at']=(self.now-timedelta(seconds=age)).isoformat()
        self.assertIn('LARGE_SAMPLING_GAP',self.analyze(rows)['gate_reasons'])

    def test_sensor_fault_blocks_even_with_valid_recent_measurements(self):
        self.assertIn('SENSOR_FAULT_HEARTBEAT',self.analyze(sensor_status='FAULT')['gate_reasons'])

    def test_quality_failure_is_not_bridged(self):
        rows=copy.deepcopy(self.rows);rows[-4]['quality']='CALIBRATION_REQUIRED'
        r=self.analyze(rows);self.assertEqual(r['status'],'BLOCKED');self.assertEqual(r['usable_sample_count'],3)

    def test_real_input_always_requires_human_review(self):
        rows=copy.deepcopy(self.rows)
        for row in rows:row['source']='real'
        r=analyze_rows(rows,'real',now=self.now)
        self.assertTrue(r['human_review_required']);self.assertEqual(r['hardware_validation'],'PENDING')

    def test_summary_excludes_raw_ids_and_reference_notes(self):
        rows=copy.deepcopy(self.rows);snapshot=json.loads(rows[0]['calibration_snapshot'])
        snapshot['reference']='PRIVATE_REFERENCE_NOTE'
        rows[0]['calibration_snapshot']=json.dumps(snapshot)
        summary=json.dumps(public_summary(self.analyze(rows)))
        self.assertNotIn('PRIVATE_REFERENCE_NOTE',summary);self.assertNotIn('analysis-case',summary)
        self.assertNotIn('device_id',summary);self.assertNotIn('calibration_snapshot',summary)

    def test_strict_json_rejects_duplicate_keys_and_nan(self):
        for text in ['{"a":1,"a":2}','{"a":NaN}']:
            with self.assertRaises(ValueError):strict_json(text)

    def test_ai_selection_rejects_invented_evidence_commands_and_missing_limits(self):
        report=self.analyze();valid=selection(public_summary(report));self.assertEqual(validate_ai_selection(valid,report),valid)
        variants=[]
        for key,value in [('priority_evidence',['E99']),('check_codes',['START_PUMP']),('limitations',['NO_ACTUATION'])]:
            candidate=copy.deepcopy(valid);candidate[key]=value;variants.append(candidate)
        candidate=copy.deepcopy(valid);candidate['summary']='Invented diagnosis';variants.append(candidate)
        candidate=copy.deepcopy(valid);candidate['priority_evidence']=['E01','E01'];variants.append(candidate)
        for candidate in variants:
            with self.subTest(candidate=candidate),self.assertRaises(ValueError):validate_ai_selection(candidate,report)


class GatewayAndAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(Path(self.tmp.name)/'test.sqlite3');self.service=AnalysisService(self.store)
        self.rows=synthetic_case('Rising heat')

    def provider(self,model,key,body):
        self.assertEqual(body['generationConfig']['responseMimeType'],'application/json')
        prompt=body['contents'][0]['parts'][0]['text'];summary=json.loads(prompt.split('Snapshot: ',1)[1])
        return 200,{'modelVersion':'test-model','candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps(selection(summary))}]}}]}

    def test_valid_mock_response_preserves_gate_and_local_findings(self):
        gateway=GeminiGateway(key='secret-test-key',transport=self.provider)
        r=self.service.run('demo',rows=self.rows,gateway=gateway,use_gemini=True)
        self.assertEqual(r['ai']['engine'],'GEMINI');self.assertEqual(r['status'],'REVIEW_REQUIRED')
        self.assertEqual(r['authorization'],'NO_ACTION_AUTHORIZED');self.assertEqual(r['ai']['returned_model'],'test-model')
        with self.store.connect() as db:stored=db.execute('SELECT report_json FROM analysis_runs').fetchone()[0]
        self.assertNotIn('secret-test-key',stored);self.assertEqual(json.loads(stored)['input_sha256'],r['input_sha256'])

    def test_blocked_never_calls_gateway(self):
        class Never:
            def select(self,*args):raise AssertionError('Gate failed to block model call')
        r=self.service.run('demo',rows=synthetic_case('Stale readings'),gateway=Never(),use_gemini=True)
        self.assertEqual(r['ai']['engine'],'BLOCKED');self.assertEqual(r['ai']['attempts'],0)

    def test_missing_key_is_explicit_local_fallback(self):
        r=self.service.run('demo',rows=self.rows,gateway=GeminiGateway(key=''),use_gemini=True)
        self.assertEqual(r['ai']['engine'],'LOCAL_FALLBACK');self.assertEqual(r['ai']['reason'],'MISSING_KEY')

    def test_rate_limit_is_bounded_and_no_exception_leak(self):
        calls=[]
        def limited(*args):calls.append(1);return 429,{}
        r=self.service.run('demo',rows=self.rows,gateway=GeminiGateway(key='x',transport=limited,sleep=lambda _:None),use_gemini=True)
        self.assertEqual(len(calls),2);self.assertEqual(r['ai']['reason'],'HTTP_429');self.assertEqual(r['ai']['engine'],'LOCAL_FALLBACK')

    def test_auth_failure_is_not_retried(self):
        gateway=GeminiGateway(key='x',transport=lambda *args:(401,{}),sleep=lambda _:self.fail('Should not retry'))
        r=self.service.run('demo',rows=self.rows,gateway=gateway,use_gemini=True)
        self.assertEqual(r['ai']['attempts'],1);self.assertEqual(r['ai']['reason'],'HTTP_401')

    def test_invalid_json_and_incomplete_response_fall_back(self):
        for candidate in [dict(finishReason='STOP',content={'parts':[{'text':'not JSON'}]}),dict(finishReason='MAX_TOKENS',content={'parts':[]})]:
            gateway=GeminiGateway(key='x',transport=lambda *args:(200,{'candidates':[candidate]}))
            r=self.service.run('demo',rows=self.rows,gateway=gateway,use_gemini=True)
            self.assertEqual(r['ai']['engine'],'LOCAL_FALLBACK')

    def test_invented_model_actions_are_not_displayed(self):
        class Bad:
            def select(self,*args):return dict(ok=True,selection=dict(priority_evidence=['E01'],check_codes=['START_PUMP'],limitations=['NO_ACTUATION']))
        r=self.service.run('demo',rows=self.rows,gateway=Bad(),use_gemini=True)
        self.assertEqual(r['ai']['engine'],'LOCAL_FALLBACK');self.assertNotIn('START_PUMP',format_report(r))

    def test_history_and_source_isolation(self):
        r=self.service.run('demo',rows=self.rows)
        self.assertEqual(self.service.history('demo')[0]['run_id'],r['run_id'])
        self.assertEqual(self.service.history('real'),[]);self.assertEqual(self.store.count('real'),0)

    def test_gateway_exception_uses_local_fallback(self):
        class Broken:
            def select(self,*args):raise RuntimeError('sensitive detail must not appear')
        r=self.service.run('demo',rows=self.rows,gateway=Broken(),use_gemini=True)
        self.assertEqual(r['ai']['reason'],'GATEWAY_ERROR');self.assertNotIn('sensitive detail',json.dumps(r))

    def test_model_identifier_blocks_url_injection(self):
        with self.assertRaises(ValueError):GeminiGateway(key='x',model='a/../../path?key=secret')


if __name__=='__main__':unittest.main()
