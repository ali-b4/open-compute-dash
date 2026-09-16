"""Read SSE incrementally, preserving events and partial output on failure."""
import json
import time


def read_stream(response, result, start):
    state = result['stream'] = dict(events=[], raw_lines=[], content='', reasoning='',
                                  first_token_seconds=None, last_token_seconds=None, complete=False)
    body = result['response']['body'] = {'choices': [{'message': {'content': '', 'reasoning_content': ''}}]}
    pending = []

    def dispatch():
        if not pending:
            return
        data = '\n'.join(pending)
        pending.clear()
        arrived = time.perf_counter() - start
        state['events'].append({'arrival_seconds': arrived, 'data': data})
        if data == '[DONE]':
            state['complete'] = True
            return
        event = json.loads(data)
        if not isinstance(event, dict):
            raise ValueError('Stream event is not a JSON object')
        if event.get('error'):
            raise ValueError('API stream error: ' + json.dumps(event['error']))
        for key in ('usage', 'model', 'id', 'system_fingerprint'):
            if event.get(key) is not None:
                body[key] = event[key]
        for choice in event.get('choices', []):
            if choice.get('index', 0) != 0:
                continue
            delta = choice.get('delta') or {}
            content = delta.get('content') or ''
            reasoning = delta.get('reasoning_content') or delta.get('reasoning') or ''
            if content or reasoning:
                if state['first_token_seconds'] is None:
                    state['first_token_seconds'] = arrived
                state['last_token_seconds'] = arrived
                state['content'] += content
                state['reasoning'] += reasoning
            body['choices'][0]['message'] = {'content': state['content'], 'reasoning_content': state['reasoning']}
            if choice.get('finish_reason') is not None:
                body['choices'][0]['finish_reason'] = choice['finish_reason']

    for raw in response:
        line = raw.decode('utf-8').rstrip('\r\n')
        state['raw_lines'].append(line)
        if line == '':
            dispatch()
            if state['complete']:
                break
        elif line.startswith('data:'):
            pending.append(line[5:].removeprefix(' '))
    dispatch()
    if not state['complete']:
        raise ValueError('Stream ended without [DONE]; partial output retained')
