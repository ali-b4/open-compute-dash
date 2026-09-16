"""Small isolated capability probes; no external tools are actually executed."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
import html
import json
from pathlib import Path
import uuid
from manual_request import ROOT,load_dotenv,probe
from provider_config import PROVIDERS
from render_report import render_report

SCHEMA={'type':'object','properties':{'answer':{'type':'string','enum':['ok']}},'required':['answer'],'additionalProperties':False}
CASES={
 'structured_output':('Return an object with answer set to ok.',{'response_format':{'type':'json_schema','json_schema':{'name':'result','strict':True,'schema':SCHEMA}}}),
 'tool_calling':('Call record_number with value 7. Do not answer in text.',{'tools':[{'type':'function','function':{'name':'record_number','description':'Record the supplied number.','parameters':{'type':'object','properties':{'value':{'type':'integer'}},'required':['value'],'additionalProperties':False}}}], 'tool_choice':{'type':'function','function':{'name':'record_number'}}})}

CASES['tool_calling_auto'] = (CASES['tool_calling'][0], {**CASES['tool_calling'][1], 'tool_choice':'auto'})


def check(case,result):
    if not result['success']:return False,'Request rejected or failed; see raw error. This alone does not prove permanent lack of support.'
    try:
        message=result['response']['body']['choices'][0]['message']
        if case=='structured_output':passed=json.loads(message['content'])=={'answer':'ok'}
        else:
            calls=message['tool_calls']
            passed=len(calls)==1 and calls[0]['function']['name']=='record_number' and json.loads(calls[0]['function']['arguments'])=={'value':7}
        return passed,'Expected output shape observed.' if passed else 'Response did not match the requested output shape.'
    except (KeyError,IndexError,TypeError,ValueError):return False,'Expected output shape missing or malformed.'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--providers',nargs='+',choices=PROVIDERS,default=list(PROVIDERS))
    parser.add_argument("--cases",nargs="+",choices=CASES,default=list(CASES))
    args=parser.parse_args();load_dotenv()
    output=ROOT/'results/qualification'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]);output.mkdir(parents=True)
    rows=[]
    for case in dict.fromkeys(args.cases):
        prompt,options=CASES[case]
        directory=output/case;directory.mkdir()
        with ThreadPoolExecutor(max_workers=len(args.providers)) as pool:
            futures={pool.submit(probe,p,prompt,45,request_options=options):p for p in dict.fromkeys(args.providers)}
            for future in as_completed(futures):
                p=futures[future];result=future.result();passed,note=check(case,result)
                result['qualification']={'case':case,'observed_support':passed,'note':note,'exclude_from_benchmark':True}
                (directory/f'{p}.json').write_text(json.dumps(result,indent=2)+'\n')
                rows.append({'provider':p,'case':case,'observed_support':passed,'http_status':(result.get('response') or {}).get('status_code'),'note':note,'report':f'{case}/report.html'})
                print(f'{case} {p}: {"OBSERVED" if passed else "REVIEW"}',flush=True)
        render_report(directory)
    (output/'summary.json').write_text(json.dumps(rows,indent=2)+'\n')
    table=''.join('<tr>'+''.join('<td>'+html.escape(str(r[k]))+'</td>' for k in ['provider','case','observed_support','http_status','note'])+'<td><a href="'+r['report']+'">Details</a></td></tr>' for r in rows)
    (output/'index.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><title>Capability qualification</title><style>body{font:16px system-ui;margin:24px}td,th{padding:10px;border-bottom:1px solid #ddd;text-align:left}</style><h1>Capability qualification</h1><p>One non-streaming probe per capability/provider. No external function was executed. Success demonstrates the tested example, not general compliance. Diagnostics are excluded from benchmarks.</p><table><tr><th>Provider</th><th>Case</th><th>Observed</th><th>HTTP</th><th>Interpretation</th><th>Report</th></tr>'+table+'</table></html>')
    print(f'Qualification: {output}/index.html')

if __name__=='__main__':main()
