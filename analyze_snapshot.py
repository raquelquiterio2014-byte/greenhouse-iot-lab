"""Run a local example or explicitly opt into Gemini; no GUI or hardware needed."""
import argparse,json
from pathlib import Path
from greenhouse.analysis import AnalysisService,synthetic_case,format_report
from greenhouse.core import Store
from greenhouse.config import DATA_DIR,ROOT
from greenhouse.llm_gateway import GeminiGateway
from greenhouse.connectivity import summarize

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',choices=['demo','test','real'],default='demo')
    parser.add_argument('--example',choices=['Normal','Rising heat','Dry soil','Temperature spike','Stale readings','Uncalibrated soil','Saturated light'])
    parser.add_argument('--gemini',action='store_true',help='Explicitly send a controlled aggregate summary to Gemini')
    args=parser.parse_args()
    if args.example and args.source!='demo':parser.error('Examples must use --source demo')
    store=Store(DATA_DIR/'greenhouse.sqlite3');rows=synthetic_case(args.example) if args.example else None
    report=AnalysisService(store).run(args.source,rows=rows,use_gemini=args.gemini,
        gateway=GeminiGateway() if args.gemini else None,
        sensor_status=summarize(store,args.source)['sensor_status'] if args.source in ('real','test') else 'UNKNOWN',
        input_kind='synthetic_case: '+args.example if args.example else 'stored_history')
    folder=ROOT/'exports';folder.mkdir(exist_ok=True)
    path=folder/('v4_analysis_'+report['run_id']+'.json');path.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(format_report(report));print('\nSaved:',path)
