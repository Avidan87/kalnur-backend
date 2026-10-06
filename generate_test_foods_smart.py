# Smart resumable Kalnur food generator.
# See chat response for the design and how to replace the old script.
import json, os, sqlite3, time, uuid
from pathlib import Path
from typing import Any
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
SOURCE_FILE=Path(r'C:\Users\avifr\Downloads\nigerian_foods.json')
OUTPUT_FILE=Path(r'C:\Users\avifr\KAI\knowledge-base\test\kalnur_foods_500.jsonl')
CACHE_DB=Path(r'C:\Users\avifr\KAI\knowledge-base\test\food_generation_cache.db')
TARGET=500
NAME_BATCH=20
RECORD_BATCH=5
MAX_ATTEMPTS=300
MODEL=os.getenv('OPENAI_GENERATION_MODEL','gpt-4o-mini')
client=OpenAI(api_key=os.environ['OPENAI_API_KEY'])

def norm(x):
    if not isinstance(x,str): return ''
    return ' '.join(''.join(c if c.isalnum() or c.isspace() else ' ' for c in x.lower()).split())

def load(path):
    text=path.read_text(encoding='utf-8-sig').strip()
    try: data=json.loads(text); return data if isinstance(data,list) else data.get('foods',data.get('data',data.get('records',data.get('items',[]))))
    except json.JSONDecodeError: return [json.loads(x) for x in text.splitlines() if x.strip()]

def save(records):
    OUTPUT_FILE.parent.mkdir(parents=True,exist_ok=True)
    tmp=OUTPUT_FILE.with_suffix('.tmp')
    with tmp.open('w',encoding='utf-8') as f:
        for r in records: f.write(json.dumps(r,ensure_ascii=False)+'\n')
        f.flush(); os.fsync(f.fileno())
    tmp.replace(OUTPUT_FILE)

def cache_init():
    CACHE_DB.parent.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(CACHE_DB)
    c.execute('CREATE TABLE IF NOT EXISTS names (n TEXT PRIMARY KEY, original TEXT, status TEXT)'); c.commit(); return c

def cache_add(c,name,status):
    n=norm(name)
    if n: c.execute('INSERT OR IGNORE INTO names VALUES (?,?,?)',(n,name,status)); c.commit()

def cached(c,name): return c.execute('SELECT 1 FROM names WHERE n=?',(norm(name),)).fetchone() is not None

def candidates(existing):
    prompt=f'''Generate up to {NAME_BATCH} real, distinct food dishes from any country. No fictional foods, drinks, ingredients, aliases, or trivial variations. Avoid these known names: {json.dumps(sorted(existing)[-300:])}. Return ONLY JSON: {{"foods":["name",...]}}'''
    r=client.chat.completions.create(model=MODEL,temperature=.9,response_format={'type':'json_object'},messages=[{'role':'system','content':'You are a food dataset candidate-name generator.'},{'role':'user','content':prompt}])
    return json.loads(r.choices[0].message.content).get('foods',[])

def records_for(names,keys,example):
    prompt=f'''Create complete Kalnur records for EXACTLY these foods: {json.dumps(names,ensure_ascii=False)}. Use EXACTLY these schema keys: {json.dumps(sorted(keys))}. Reference: {json.dumps(example,ensure_ascii=False)}. Values are synthetic test nutrition values but plausible. Do not add/remove fields. Return ONLY JSON {{"foods":[...]}}.'''
    r=client.chat.completions.create(model=MODEL,temperature=.7,response_format={'type':'json_object'},messages=[{'role':'system','content':'You generate structured nutrition knowledge-base records.'},{'role':'user','content':prompt}])
    return json.loads(r.choices[0].message.content).get('foods',[])

def main():
    source=load(SOURCE_FILE)
    if not source: raise RuntimeError('No source records found')
    keys=set(source[0])
    c=cache_init()
    used=set()
    for r in source:
        if r.get('name'): used.add(norm(r['name'])); cache_add(c,r['name'],'existing')
    # Resume from checkpoint if it already exists; otherwise initialize it.
    current=load(OUTPUT_FILE) if OUTPUT_FILE.exists() else []
    if len(current)<len(source): current=source.copy(); save(current)
    for r in current:
        if r.get('name'): used.add(norm(r['name'])); cache_add(c,r['name'],'generated')
    print(f'Loaded source: {len(source)} | Current checkpoint: {len(current)} | Target: {TARGET}')
    attempts=0
    while len(current)<TARGET:
        attempts+=1
        if attempts>MAX_ATTEMPTS:
            print(f'Max attempts reached. SAFE checkpoint: {len(current)}/{TARGET}')
            return
        try:
            raw=candidates(used)
            unique=[]
            for name in raw:
                if not isinstance(name,str) or not name.strip(): continue
                if cached(c,name) or norm(name) in used:
                    print(f'CACHE/DUPLICATE SKIP: {name}')
                    cache_add(c,name,'duplicate')
                    continue
                unique.append(name); used.add(norm(name)); cache_add(c,name,'candidate')
                if len(unique)>=min(RECORD_BATCH,TARGET-len(current)): break
            if not unique:
                continue
            print(f'Enriching {len(unique)} unique names: {unique}')
            batch=records_for(unique,keys,source[:3])
            for r in batch:
                if not isinstance(r,dict) or set(r)!=keys or not isinstance(r.get('name'),str):
                    print('REJECTED malformed record'); continue
                n=norm(r['name'])
                if n in {norm(x.get('name')) for x in current}:
                    print(f'DUPLICATE RETURNED: {r["name"]}'); cache_add(c,r['name'],'duplicate'); continue
                r['food_id']=f'test-{uuid.uuid4().hex[:12]}'
                current.append(r); cache_add(c,r['name'],'generated'); save(current)
                print(f'SAVED: {r["name"]} -> {len(current)}/{TARGET}')
        except KeyboardInterrupt:
            print(f'Interrupted. SAFE checkpoint: {len(current)}/{TARGET}'); return
        except Exception as e:
            print(f'ERROR: {type(e).__name__}: {e}'); time.sleep(3)
    print(f'SUCCESS: {len(current)} records saved to {OUTPUT_FILE}')
    print(f'Cache: {CACHE_DB}')

if __name__=='__main__': main()
