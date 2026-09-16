"""Run fixed-model workload files across providers; preserve every observation."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import html
import json
import os
from pathlib import Path
import re
import sys
import time
import uuid
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from providers.venice import VeniceProvider
from providers.chutes import ChutesProvider
from providers.darkbloom import DarkbloomProvider
from providers.ionet import IonetProvider
from scripts.manual_request import load_dotenv
from scripts.measurements import normalize
from scripts.provider_config import MODEL, PROVIDERS
from scripts.render_report import render_report
from scripts.refresh_pricing import refresh

ADAPTERS={'venice':VeniceProvider,'chutes':ChutesProvider,'darkbloom':DarkbloomProvider,'ionet':IonetProvider}
DEFAULT_WORKLOADS=[ROOT/'tests/basic_chat.json']
FROZEN_PROVIDERS=['venice','chutes','darkbloom']
FROZEN_CASES=['short_factual','medium_explanation','longer_generation']
FROZEN_SETTINGS={'temperature':0,'top_p':1,'max_tokens':2048,'stream':True,
                 'timeout_seconds':180,'pause_between_requests_seconds':2,
                 'repetitions':1,'concurrency':1}


def load_frozen_workload(data, path, source):
    fields={'name','version','frozen_at','model','providers','provider_model_ids','settings','cases'}
    if set(data)!=fields or data['name']!='basic_chat' or data['version']!='0.1' or data['frozen_at']!='2026-09-15':
        raise ValueError(f'{path}: invalid frozen v0.1 workload identity or fields')
    digest=hashlib.sha256(source).hexdigest()
    try:lock=path.with_suffix('.sha256').read_text().split()
    except OSError as error:raise ValueError(f'{path}: frozen workload checksum file is required') from error
    if len(lock)!=2 or lock[0]!=digest or lock[1]!=path.name:
        raise ValueError(f'{path}: frozen workload checksum mismatch; preserve v0.1 and create a new version for changes')
    ids={p:PROVIDERS[p][1] for p in FROZEN_PROVIDERS}
    if data['model']!=MODEL or data['providers']!=FROZEN_PROVIDERS or data['provider_model_ids']!=ids:
        raise ValueError(f'{path}: frozen provider/model selection changed')
    settings=data['settings']
    if (not isinstance(settings,dict) or settings!=FROZEN_SETTINGS or
            any(type(settings[k]) is not type(v) for k,v in FROZEN_SETTINGS.items())):
        raise ValueError(f'{path}: frozen v0.1 settings changed')
    cases=data['cases']
    if not isinstance(cases,list) or len(cases)!=3:
        raise ValueError(f'{path}: frozen v0.1 requires exactly three cases')
    workloads=[]
    for case,name in zip(cases,FROZEN_CASES):
        if not isinstance(case,dict) or set(case)!={'name','messages'} or case['name']!=name:
            raise ValueError(f'{path}: frozen case names/order changed')
        messages=case['messages']
        if (not isinstance(messages,list) or len(messages)!=1 or not isinstance(messages[0],dict) or
                set(messages[0])!={'role','content'} or messages[0]['role']!='user' or
                not isinstance(messages[0]['content'],str) or not messages[0]['content'].strip()):
            raise ValueError(f'{path}: each frozen case requires one independent user prompt')
        workloads.append({**case,'model':MODEL,'providers':data['providers'],'provider_model_ids':ids,
                          'settings':settings,'source_path':str(path.resolve()),'source_sha256':digest,
                          'frozen_workload':{k:data[k] for k in ('name','version','frozen_at')} | {'source_sha256':digest}})
    return workloads


def validate_frozen_execution(workloads, selected, modes, repetitions, timeout, pause):
    frozen=[w for w in workloads if 'frozen_workload' in w]
    if not frozen:return
    if (len(frozen)!=len(workloads) or [w['name'] for w in workloads]!=FROZEN_CASES or
            selected not in (None,FROZEN_PROVIDERS) or modes!=[True] or repetitions!=1 or
            timeout!=180 or pause!=2):
        raise ValueError('Frozen v0.1 requires its three providers, streaming, one repetition, timeout 180 and pause 2; overrides/mixed workloads are not allowed')
    for w in workloads:
        if (w['settings']!=FROZEN_SETTINGS or w['providers']!=FROZEN_PROVIDERS or
                any(os.getenv(f'{p.upper()}_MODEL',PROVIDERS[p][1])!=w['provider_model_ids'][p] for p in FROZEN_PROVIDERS)):
            raise ValueError('Frozen v0.1 provider/model or request settings changed')
    source=Path(workloads[0]['source_path']).read_bytes()
    if any(hashlib.sha256(source).hexdigest()!=w['source_sha256'] for w in workloads):
        raise ValueError('Frozen workload changed after loading')


def load_workloads(paths):
    workloads=[];names=set()
    for path in paths:
        source=path.read_bytes()
        data=json.loads(source)
        if isinstance(data,dict) and ('version' in data or 'cases' in data):
            if len(paths)!=1:raise ValueError('Frozen v0.1 cannot be mixed with other workloads')
            return load_frozen_workload(data,path,source)
        if not isinstance(data,dict) or set(data)-{'name','model','providers','messages'}:
            raise ValueError(f'{path}: only name, model, providers, messages are allowed')
        name=data.get('name')
        if not isinstance(name,str) or not re.fullmatch(r'[a-zA-Z0-9_-]+',name) or name in names:
            raise ValueError(f'{path}: workload names must be unique and use letters, numbers, hyphens, or underscores')
        if data.get('model',MODEL)!=MODEL:raise ValueError(f'{path}: model must remain {MODEL}')
        providers=data.get('providers',list(PROVIDERS))
        if not isinstance(providers,list) or not providers or any(not isinstance(p,str) or p not in PROVIDERS for p in providers):
            raise ValueError(f'{path}: invalid providers')
        messages=data.get('messages')
        if not isinstance(messages,list) or not messages:raise ValueError(f'{path}: messages must be nonempty')
        for message in messages:
            if (not isinstance(message,dict) or set(message)!={'role','content'} or
                    message['role'] not in {'system','user','assistant'} or not isinstance(message['content'],str)):
                raise ValueError(f'{path}: messages require supported role and text content')
        if not any(m['role']=='user' for m in messages):raise ValueError(f'{path}: a user message is required')
        names.add(name)
        workloads.append({**data,'model':MODEL,'providers':list(dict.fromkeys(providers)),
                          'source_path':str(path.resolve()),'source_sha256':hashlib.sha256(source).hexdigest()})
    return workloads


def frozen_request_check(run_dir, manifest, records):
    """Compare saved requests with the exact frozen source, without provider calls."""
    frozen=manifest.get('frozen_workload')
    if not frozen:return None
    source=(run_dir/'workload.json').read_bytes()
    if hashlib.sha256(source).hexdigest()!=frozen['source_sha256']:
        return {'passed':False,'checked_requests':0,'reason':'Saved workload checksum mismatch'}
    data=json.loads(source);cases={c['name']:c['messages'] for c in data['cases']}
    mismatches=[]
    for r in records:
        p=r['provider'];case=r['benchmark']['workload']
        expected={'model':data['provider_model_ids'][p],'messages':cases[case],
                  **{k:data['settings'][k] for k in ('temperature','top_p','max_tokens','stream')},
                  'stream_options':{'include_usage':True}}
        if p=='venice':expected['venice_parameters']={'include_venice_system_prompt':False}
        if r['request']['json']!=expected or r['benchmark']['source_sha256']!=frozen['source_sha256']:
            mismatches.append(f'{case}/{p}')
    return {'passed':not mismatches,'checked_requests':len(records),'mismatches':mismatches,
            'source_sha256':frozen['source_sha256']}


def rebuild_summary(run_dir, summary_dir):
    manifest=json.loads((run_dir/'manifest.json').read_text())
    rows=[];records=[]
    for relative in manifest['record_paths']:
        path=run_dir/relative
        if not path.exists():continue
        r=json.loads(path.read_text())
        records.append(r)
        if any((r.get(k) or {}).get('exclude_from_benchmark') for k in ('diagnostic','validation','accounting_diagnostic','qualification')):
            raise ValueError('Diagnostic record cannot enter benchmark summary')
        m={key:item['value'] for key,item in r['metrics'].items()}
        choices=((r.get('response') or {}).get('body') or {})
        choices=choices.get('choices',[]) if isinstance(choices,dict) else []
        finish=choices[0].get('finish_reason') if choices else None
        rows.append({'workload':r['benchmark']['workload'],'repetition':r['benchmark']['repetition'],
                     'streaming':r['request']['json']['stream'],'provider':r['provider'],
                     'model':r['model'],'provider_model_id':r['provider_model_id'],
                     'record':relative,'finish_reason':finish,**m})
    summary={'run_id':run_dir.name,'complete':manifest.get('complete',False) and len(rows)==len(manifest['record_paths']),
             'expected_observations':len(manifest['record_paths']),'saved_observations':len(rows),
             'successful_observations':sum(r['success'] for r in rows),'observations':rows,
             'note':'Request-level observations only; no rankings or statistical claims. Null means unavailable.'}
    controls=frozen_request_check(run_dir,manifest,records)
    if controls is not None:summary['frozen_workload_check']=controls
    summary_dir.mkdir(parents=True,exist_ok=True)
    (summary_dir/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    cells=[]
    columns=['workload','repetition','streaming','provider','success','http_status','finish_reason','input_tokens',
             'output_tokens','ttft_seconds','total_latency_seconds','output_tokens_per_second','request_cost']
    labels=['Workload','Repeat','Streaming','Provider','Success','HTTP','Finish reason','Input tokens','Output tokens','TTFT (s)',
            'Total (s)','Output tokens/s','Est. cost (USD)']
    for row in rows:
        values=[]
        for col in columns:
            v=row[col]
            values.append('Unavailable' if v is None else f'{v:.6g}' if isinstance(v,float) else str(v))
        report=run_dir/Path(row['record']).parent/'report.html'
        link=Path(os.path.relpath(report,summary_dir)).as_posix()
        cells.append('<tr>'+''.join('<td>'+html.escape(v)+'</td>' for v in values)+
                     '<td><a href="'+html.escape(link)+'">Details</a></td></tr>')
    status='Complete' if summary['complete'] else 'In progress / interrupted'
    controls_html=''
    if controls is not None:
        controls_html=f'<p>Frozen v0.1 request check: {"PASS" if controls["passed"] else "REVIEW"} · {controls["checked_requests"]} saved requests checked against the frozen workload. '
        controls_html+='Three independent prompts, three providers, one request at a time, one pass. Temperature 0; top_p 1; max_tokens 2048; streaming.</p>'
    (summary_dir/'index.html').write_text('''<!doctype html><html lang="en"><meta charset="utf-8"><title>Benchmark summary</title>
<style>body{font:15px system-ui;margin:24px;color:#182434}table{border-collapse:collapse}td,th{padding:9px;border-bottom:1px solid #ddd;text-align:left}th{background:#eef2f6}a{color:#145bb0}</style>
<h1>Provider benchmark</h1>'''+f'<p>{html.escape(run_dir.name)} · {status} · {summary["saved_observations"]}/{summary["expected_observations"]} observations saved · {summary["successful_observations"]} successful</p>'+
        controls_html+'<p>Same requested workload and settings within each group. Serving builds and provider reasoning defaults may differ. Failed requests remain visible. Null metrics are unavailable, not zero. These small samples are not rankings.</p>'+
        '<p>Success describes the API request. Finish reason <b>length</b> means generation reached a limit; review the answer for truncation. <b>stop</b> means generation ended normally, not that answer quality was verified.</p>'+
        '<table><tr>'+''.join('<th>'+html.escape(x)+'</th>' for x in labels)+ '<th>Report</th></tr>'+''.join(cells)+'</table></html>')
    return summary


def execute(workloads, selected, modes, repetitions, timeout, run_dir, summary_dir, pause=2):
    validate_frozen_execution(workloads,selected,modes,repetitions,timeout,pause)
    frozen=workloads[0].get('frozen_workload')
    run_dir.mkdir(parents=True,exist_ok=False)
    groups=[]
    for w in workloads:
        providers=selected if selected is not None else w['providers']
        for rep in range(1,repetitions+1):
            for stream in modes:
                name=f"{w['name']}-r{rep}-{'streaming' if stream else 'non-streaming'}"
                groups.append((name,w,providers,rep,stream))
    manifest={'model':MODEL,'settings':{'temperature':0,'max_tokens':None,'timeout_seconds':timeout,'pause_between_groups_seconds':pause},
              'workloads':workloads,'pricing':json.loads((ROOT/'config/pricing.json').read_text()),
              'record_paths':[f'{name}/{p}.json' for name,w,ps,rep,stream in groups for p in ps], 'complete':False}
    if frozen:
        manifest['settings']=dict(FROZEN_SETTINGS)
        manifest['frozen_workload']=dict(frozen)
        manifest['provider_model_ids']=workloads[0]['provider_model_ids']
        manifest['provider_request_options']={'venice':{'venice_parameters':{'include_venice_system_prompt':False}}}
        source=Path(workloads[0]['source_path']).read_bytes()
        if hashlib.sha256(source).hexdigest()!=frozen['source_sha256']:
            raise ValueError('Frozen workload changed before snapshot')
        (run_dir/'workload.json').write_bytes(source)
        (run_dir/'workload.sha256').write_text(f'{frozen["source_sha256"]}  workload.json\n')
    (run_dir/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    rebuild_summary(run_dir,summary_dir)
    for index,(name,w,providers,rep,stream) in enumerate(groups):
        if index and pause:time.sleep(pause)
        directory=run_dir/name;directory.mkdir()
        options={k:w['settings'][k] for k in ('temperature','top_p','max_tokens')} if frozen else None
        with ThreadPoolExecutor(max_workers=1 if frozen else len(providers)) as pool:
            futures={}
            if not frozen:
                futures={pool.submit(ADAPTERS[p]().chat,w['messages'],streaming=stream,timeout=timeout):p for p in providers}
            for offset,item in enumerate(providers if frozen else as_completed(futures)):
                p=item if frozen else futures[item]
                if frozen and offset and pause:time.sleep(pause)
                try:
                    r=(ADAPTERS[p]().chat(w['messages'],streaming=stream,timeout=timeout,request_options=options)
                       if frozen else item.result())
                except Exception as error:
                    payload={'model':PROVIDERS[p][1],'messages':w['messages'],'temperature':0,'stream':stream,**(options or {})}
                    if stream:payload['stream_options']={'include_usage':True}
                    if p=='venice':payload['venice_parameters']={'include_venice_system_prompt':False}
                    r=normalize({'provider':p,'model':MODEL,'provider_model_id':PROVIDERS[p][1],
                                 'timestamp':datetime.now(timezone.utc).isoformat(),'request_sent':False,
                                 'request':{'json':payload},
                                 'success':False,'response':None,'total_latency_seconds':None,
                                 'error':{'type':'AdapterError','message':str(error)}})
                r['benchmark']={'workload':w['name'],'repetition':rep,'source_sha256':w['source_sha256']}
                (directory/f'{p}.json').write_text(json.dumps(r,indent=2)+'\n')
                print(f"{name} {p}: {'OK' if r['success'] else 'FAILED'}",flush=True)
                render_report(directory)
                rebuild_summary(run_dir,summary_dir)
    manifest['complete']=True
    (run_dir/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return rebuild_summary(run_dir,summary_dir)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workloads',nargs='+',type=Path,default=DEFAULT_WORKLOADS)
    parser.add_argument('--providers',nargs='+',choices=PROVIDERS)
    parser.add_argument('--mode',choices=('both','streaming','non-streaming'),default=None)
    parser.add_argument('--repetitions',type=int,default=None)
    parser.add_argument('--timeout',type=float,default=None)
    parser.add_argument('--pause',type=float,default=None,help='Seconds between requests for frozen v0.1, otherwise groups (default 2)')
    parser.add_argument('--skip-pricing-refresh',action='store_true',help='Explicitly use saved dated pricing')
    parser.add_argument('--rebuild',type=Path,help='Rebuild summary from a saved benchmark run; no API calls')
    parser.add_argument('--open',action='store_true')
    args=parser.parse_args()
    if args.rebuild:
        run_dir=args.rebuild.resolve();summary_dir=ROOT/'results/summary'/run_dir.name
        summary=rebuild_summary(run_dir,summary_dir)
    else:
        try:workloads=load_workloads(args.workloads)
        except (ValueError,OSError,TypeError) as error:parser.error(str(error))
        frozen=workloads[0].get('frozen_workload')
        args.mode=args.mode or ('streaming' if frozen else 'both')
        args.repetitions=1 if args.repetitions is None else args.repetitions
        args.timeout=180 if args.timeout is None else args.timeout
        args.pause=2 if args.pause is None else args.pause
        if args.repetitions<1 or not 0<args.timeout<float('inf') or not 0<=args.pause<=60:
            parser.error('Repetitions must be positive; timeout finite and positive; pause between 0 and 60')
        selected=list(dict.fromkeys(args.providers)) if args.providers else None
        modes=[False,True] if args.mode=='both' else [args.mode=='streaming']
        try:validate_frozen_execution(workloads,selected,modes,args.repetitions,args.timeout,args.pause)
        except ValueError as error:parser.error(str(error))
        active=selected or list(dict.fromkeys(p for w in workloads for p in w['providers']))
        load_dotenv()
        for p in active:
            if os.getenv(f'{p.upper()}_MODEL',PROVIDERS[p][1])!=PROVIDERS[p][1]:
                parser.error(f'{p}: restore fixed model ID {PROVIDERS[p][1]}')
        if not args.skip_pricing_refresh:
            try:print(f'Pricing refreshed: {refresh(active)}',flush=True)
            except Exception as error:parser.exit(1,f'Pricing refresh failed; no inference requests sent: {error}\nUse --skip-pricing-refresh only to explicitly accept saved prices.\n')
        else:print('Using saved dated pricing (--skip-pricing-refresh).',flush=True)
        run_id=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]
        run_dir=ROOT/'results/raw'/run_id;summary_dir=ROOT/'results/summary'/run_id
        summary=execute(workloads,selected,modes,args.repetitions,args.timeout,run_dir,summary_dir,args.pause)
    report=summary_dir/'index.html';print(f'Summary: {report}')
    if args.open:webbrowser.open(report.as_uri())
    raise SystemExit(0 if summary['complete'] and summary['successful_observations']==summary['expected_observations']
                     and summary.get('frozen_workload_check',{}).get('passed',True) else 1)

if __name__=='__main__':main()
