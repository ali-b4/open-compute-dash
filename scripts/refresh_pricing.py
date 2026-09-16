"""Fetch exact-model pricing/metadata and archive dated evidence before updating config."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]
if __package__:
    from .provider_config import PROVIDERS, MODEL
else:
    from provider_config import PROVIDERS, MODEL

URLS = {'venice':'https://api.venice.ai/api/v1/models',
        'chutes':'https://llm.chutes.ai/v1/models',
        'darkbloom':'https://api.darkbloom.dev/v1/models',
        'ionet':'https://api.intelligence.io.solutions/api/v1/models'}


def fetch(url, provider, timeout=30):
    headers = {'User-Agent':'provider-eval/0.1', 'Accept':'application/json'}
    if provider in {'darkbloom','ionet'}:
        key=os.getenv(f'{provider.upper()}_API_KEY')
        if not key:
            raise ValueError(f'Missing {provider.upper()}_API_KEY for catalog refresh')
        headers['Authorization']='Bearer '+key
    with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=timeout) as response:
        return json.load(response)


def select_model(data, model):
    matches = [r for r in data['data'] if r.get('id') == model]
    if len(matches) != 1:
        raise ValueError(f'Expected exactly one catalog entry for {model}')
    return matches[0]


def number(value):
    if isinstance(value,bool):raise ValueError('Invalid price')
    value=float(value)
    if not math.isfinite(value) or value < 0:raise ValueError('Invalid price')
    return value


def parse(provider, record, old, checked):
    entry = dict(old)
    entry.update(provider_model_id=record['id'], checked_at=checked, source=URLS[provider])
    entry.pop('cache_input_per_1m_tokens',None)
    if provider=='venice':
        spec=record['model_spec'];price=spec['pricing']
        inp,out=price['input']['usd'],price['output']['usd']
        cache=price.get('cache_input',{}).get('usd')
        context=record.get('context_length');quant=spec.get('capabilities',{}).get('quantization')
    elif provider=='chutes':
        price=record['pricing'];inp,out=price['prompt'],price['completion']
        cache=price.get('input_cache_read');context=record.get('context_length');quant=record.get('quantization')
    elif provider=='darkbloom':
        price=record['pricing'];inp,out=number(price['prompt'])*1e6,number(price['completion'])*1e6
        # A zero catalog cache price does not establish free cached input billing.
        cache=None;context=record.get('context_length');quant=record.get('quantization')
    else:
        inp,out=number(record['input_token_price'])*1e6,number(record['output_token_price'])*1e6
        cache=number(record['cache_read_token_price'])*1e6 if record.get('cache_read_token_price') is not None else None
        context=record.get('context_window');quant=record.get('precision')
    entry.update(input_per_1m_tokens=number(inp),output_per_1m_tokens=number(out),context_window=context,quantization=quant)
    if cache is not None:entry['cache_input_per_1m_tokens']=number(cache)
    return entry


def refresh(providers=None, root=ROOT):
    providers = list(PROVIDERS) if providers is None else providers
    path=root/'config/pricing.json';old=json.loads(path.read_text())
    checked=datetime.now(timezone.utc).isoformat()
    def get(provider):
        model=os.getenv(f'{provider.upper()}_MODEL',PROVIDERS[provider][1])
        if model != PROVIDERS[provider][1]:
            raise ValueError(f'{provider}: configure the fixed model ID {PROVIDERS[provider][1]} before refreshing')
        records=[];page=1
        while True:
            url=URLS[provider]+(f'?page_size=100&page={page}' if provider=='ionet' else '')
            data=fetch(url,provider);records.extend(data['data'])
            if provider!='ionet' or not (data.get('pagination') or {}).get('has_next'):break
            page+=1
            if page>100:raise ValueError('Catalog pagination exceeded safety bound')
        record=select_model({'data':records},model)
        evidence={'checked_at':checked,'source':URLS[provider],'record':record}
        return provider,parse(provider,record,old.get(provider,{}),checked),evidence
    # All downloads and parsing must succeed before changing active pricing.
    with ThreadPoolExecutor(max_workers=len(providers)) as pool:
        updates=list(pool.map(get,providers))
    updated=dict(old)
    archive=root/'config/pricing-history'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8])
    archive.mkdir(parents=True,exist_ok=False)
    (archive/'previous-pricing.json').write_text(json.dumps(old,indent=2)+'\n')
    for provider,entry,evidence in updates:
        entry['snapshot']=str((archive/f'{provider}.json').relative_to(root))
        updated[provider]=entry
        (archive/f'{provider}.json').write_text(json.dumps(evidence,indent=2)+'\n')
    (archive/'pricing.json').write_text(json.dumps(updated,indent=2)+'\n')
    temporary=path.with_suffix('.json.tmp');temporary.write_text(json.dumps(updated,indent=2)+'\n');temporary.replace(path)
    return archive


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--providers',nargs='+',choices=PROVIDERS,default=list(PROVIDERS))
    args=parser.parse_args()
    if __package__:
        from .manual_request import load_dotenv
    else:
        from manual_request import load_dotenv
    load_dotenv()
    try:print(f'Pricing evidence: {refresh(list(dict.fromkeys(args.providers)))}')
    except Exception as error:parser.exit(1,f'Pricing not refreshed: {error}\n')

if __name__=='__main__':main()
