"""Prepare files for manual DSH/Ollama setup. Never launches or downloads anything."""
import hashlib
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parent

def export(args, models, options):
    if not re.fullmatch(r'[A-Za-z0-9_-]+',args.export):
        raise SystemExit('--export accepts letters, digits, underscores and hyphens')
    if args.kv_cache_type!='f16' and args.flash_attention!='on':
        raise SystemExit('Quantized KV cache requires Flash Attention; use --flash-attention on or --kv-cache-type f16')
    if args.thinking=='on' and any(not m.get('thinking',False) for m in models):
        raise SystemExit('Thinking-on export requires thinking:true for every selected model in models.json')
    out=ROOT/'exports'/args.export
    if out.exists():
        raise SystemExit('Export already exists. Choose a new --export name to preserve the old configuration.')
    out.mkdir(parents=True)
    routes=[]
    setup=["$ErrorActionPreference = 'Stop'", "Set-Location -LiteralPath $PSScriptRoot"]
    for model in models:
        source=model['name']
        if not re.fullmatch(r'[A-Za-z0-9_./:-]+',source):
            raise SystemExit('Unsupported model tag for Modelfile: '+source)
        suffix=hashlib.sha256(source.encode()).hexdigest()[:8]
        alias=f"bench-{args.export}-{re.sub('[^a-z0-9-]','-',source.lower())}-{suffix}"
        filename=alias+'.Modelfile'
        lines=['FROM '+source]+[f'PARAMETER {key} {value}' for key,value in options.items()]
        (out/filename).write_text('\n'.join(lines)+'\n',encoding='utf-8')
        setup.extend([f"ollama create '{alias}' -f '{filename}'",
                      "if ($LASTEXITCODE -ne 0) { throw 'Model creation failed. Pull its base model first.' }"])
        entry={'id':alias,'name':source+' / '+args.export,'contextWindow':args.context,
               'maxTokens':args.tokens,'input':['text'],
               'reasoningEfforts':{'off':'none','high':'high'} if model.get('thinking') else False}
        routes.append(entry)
    provider={'displayName':'Local benchmark presets','api':'openai-completions',
        'baseURL':'http://127.0.0.1:11434/v1','apiKeyEnv':'OLLAMA_API_KEY',
        'reasoning':'high' if args.thinking=='on' else 'off',
        'compat':{'supportsStore':False,'supportsDeveloperRole':False,
                  'supportsReasoningEffort':True,'maxTokensField':'max_tokens'},
        'models':routes}
    # JSON is valid YAML 1.2; this is a SETTINGS SECTION, not a full composition.
    settings={'llm-pi-ai':{'providers':{'ollama-bench':provider}}}
    (out/'dsh-settings.yaml').write_text(json.dumps(settings,indent=2)+'\n',encoding='utf-8')
    (out/'create-models.ps1').write_text('\n'.join(setup)+'\n',encoding='utf-8')
    server=["# First quit Ollama from the Windows tray. Keep this terminal open.",
            "$ErrorActionPreference = 'Stop'",
            f"$env:OLLAMA_FLASH_ATTENTION = '{'1' if args.flash_attention=='on' else '0'}'",
            f"$env:OLLAMA_KV_CACHE_TYPE = '{args.kv_cache_type}'",
            f"$env:OLLAMA_CONTEXT_LENGTH = '{args.context}'",
            "$env:OLLAMA_NUM_PARALLEL = '1'",
            "ollama serve"]
    (out/'serve-ollama.ps1').write_text('\n'.join(server)+'\n',encoding='utf-8')
    (out/'settings-snapshot.json').write_text(json.dumps({'models':[m['name'] for m in models],
        'options':options,'thinking':args.thinking,'flash_attention':args.flash_attention,
        'kv_cache_type':args.kv_cache_type},indent=2)+'\n',encoding='utf-8')
    print('Prepared:',out)
    print('No model downloaded/created, no server started, no benchmark run.')
    print('See USAGE.md section DSH. Generated DSH settings must be merged into your existing settings.')
