"""Text/native tool translation and bounded request history. No execution."""
import json
import re

TEXT_INSTRUCTION = (
    'OFFLINE CODING SUBMISSION: Return the complete solution.ts in exactly one '
    '```typescript fenced block, with no explanation outside it. The harness saves it '
    'and returns compiler/public-example feedback so you can repair it. '
    'Alternatively return exactly {"name":"submit_solution","arguments":{"source":"complete TypeScript"}}. '
    'There is NO shell, browser, network or package manager available. Do not emit bash, '
    'npm, npx, curl, install commands, or requests for internet access. TypeScript is preinstalled. '
    'Never place your only solution in reasoning; put it in the final answer content.'
)


def text_content(message):
    content = message.get('content') or ''
    if isinstance(content, str):
        return content
    return '\n'.join(b.get('text', '') for b in content if isinstance(b, dict))


def validate_source(source):
    if not isinstance(source, str) or not source.strip() or len(source.encode('utf-8')) > 262144:
        raise ValueError('Supply a nonempty complete TypeScript source file of at most 256 KiB.')
    stripped = re.sub(r'/\*[\s\S]*?\*/|//[^\n]*', '', source).strip()
    if not stripped or re.fullmatch(r'export\s*\{\s*\}\s*;?', stripped):
        raise ValueError('The empty starter is not an implementation. Supply the requested exports.')


def source_from_text(content):
    """Only final content is eligible; never extract code from reasoning."""
    text = content.strip()
    match = re.fullmatch(r'```(?:typescript|ts)\s*\n([\s\S]*?)\n```', text)
    if match:
        source = match.group(1)
    elif re.match(r'^(?:export\b|(?:async\s+)?function\b|class\b|interface\b|type\b|const\b|let\b|/\*|//)', text):
        # Plain source is valid too; the compiler, not fence formatting, judges code.
        source = text
    else:
        try:
            value = json.loads(text)
        except ValueError:
            raise ValueError('Return exactly one complete ```typescript code block; no prose or shell commands.') from None
        if (not isinstance(value, dict) or set(value) != {'name', 'arguments'}
                or value['name'] != 'submit_solution' or not isinstance(value['arguments'], dict)
                or set(value['arguments']) != {'source'}):
            raise ValueError('Only submit_solution with exactly one source argument is supported.')
        source = value['arguments']['source']
    validate_source(source)
    return source


def native_source(calls):
    if len(calls) != 1:
        raise ValueError('Submit exactly one complete source file per request.')
    call = calls[0]
    if call.get('function', {}).get('name') != 'submit_solution':
        raise ValueError('Only submit_solution is available; there is no shell or network tool.')
    args = json.loads(call['function'].get('arguments') or '{}')
    if not isinstance(args, dict) or set(args) != {'source'}:
        raise ValueError('submit_solution accepts exactly source, not command or other arguments.')
    validate_source(args['source'])
    return args['source']


def request_messages(messages, protocol, context, output_tokens):
    """Retain original task, newest candidate/result, and latest correction.

    Full events stay on disk. The byte estimate is not an exact model tokenizer.
    """
    system = next((m for m in messages if m.get('role') == 'system'), {})
    first = next((i for i, m in enumerate(messages) if m.get('role') == 'user'), None)
    if first is None:
        raise ValueError('Missing original task message')
    base = [{'role': 'system', 'content': text_content(system) + ('\n' + TEXT_INSTRUCTION if protocol == 'text' else '')},
            {'role': 'user', 'content': text_content(messages[first])}]
    last_tool = next((i for i in range(len(messages)-1, first, -1) if messages[i].get('role') == 'tool'), None)
    if last_tool is not None:
        tool = messages[last_tool]
        prior = next((m for m in reversed(messages[first+1:last_tool]) if m.get('role') == 'assistant'
                      and any(c.get('id') == tool.get('tool_call_id') for c in m.get('tool_calls', []))), None)
        if prior:
            selected = [c for c in prior['tool_calls'] if c.get('id') == tool.get('tool_call_id')]
            if protocol == 'native':
                base.extend([{'role': 'assistant', 'content': None, 'tool_calls': selected},
                             {'role': 'tool', 'tool_call_id': tool['tool_call_id'], 'content': text_content(tool)[:3000]}])
            else:
                base.extend([{'role': 'assistant', 'content': json.dumps({'name': selected[0]['function']['name'],
                              'arguments': json.loads(selected[0]['function']['arguments'])})},
                             {'role': 'user', 'content': 'Public feedback:\n' + text_content(tool)[:3000]}])
    correction = next((m for m in reversed(messages[max(first, last_tool or first)+1:]) if m.get('role') == 'user'), None)
    if correction:
        base.append({'role': 'user', 'content': text_content(correction)[:1000]})
    # Conservative two-byte/token estimate with output and schema headroom.
    available_bytes = max(0, context-output_tokens-768) * 2
    size = len(json.dumps(base, ensure_ascii=False).encode('utf-8'))
    if size > available_bytes:
        raise ValueError(f'Context budget: {size} message bytes exceed {available_bytes}; increase context or reduce output limit. No source was silently truncated.')
    return base, {'history_policy': 'original_task_latest_candidate_feedback',
                  'original_messages': len(messages), 'sent_messages': len(base),
                  'message_bytes': size, 'message_byte_budget': available_bytes,
                  'output_tokens_reserved': output_tokens}


def collect_event(event, state):
    if event.get('usage'):
        state['usage'] = event['usage']
    for choice in event.get('choices', []):
        delta = choice.get('delta', {})
        state['reasoning_chars'] = state.get('reasoning_chars', 0) + len(delta.get('reasoning') or delta.get('reasoning_content') or '')
        state['content'] += delta.get('content') or ''
        for call in delta.get('tool_calls') or []:
            item = state['calls'].setdefault(call.get('index', 0), {'id': '', 'type': 'function', 'function': {'name': '', 'arguments': ''}})
            if call.get('id'):
                item['id'] = call['id']
            fn = call.get('function', {})
            item['function']['name'] += fn.get('name') or ''
            item['function']['arguments'] += fn.get('arguments') or ''
        if choice.get('finish_reason'):
            state['finish'] = choice['finish_reason']
