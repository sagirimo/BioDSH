"""Build a bounded, public-only contract/code/output review packet. No grader imports."""
import argparse,collections,csv,hashlib,json,sys
from pathlib import Path
from delivery_check import table_specs,safe_path

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def packet(root,snapshot):
 root=Path(root);docs=snapshot['contracts'];sem=snapshot['semantic'];specs,_=table_specs(docs)
 definitions={};sources={};code={};outputs={};required=[]
 for name,expected in sem['public_files'].items():
  p=safe_path(root,name)
  if p.is_symlink() or digest(p)!=expected:raise ValueError('public snapshot changed: '+name)
  if name in docs or name=='prompt.md':
   if name=='TABLE_CONTRACT.json':
    contract=json.loads(p.read_text(encoding='utf-8-sig'))
    contract['tables']={t:{k:v for k,v in spec.items() if k!='row_set'} for t,spec in contract.get('tables',{}).items()}
    contract['review_omission_notice']='Enumerated row_set identities omitted from model packet; the deterministic contract validator checks them in full.'
    definitions[name]=json.dumps(contract,ensure_ascii=False)
   elif name=='ROW_SETS.json':definitions[name]='Enumerated row identity document checked by deterministic validator; not duplicated in model context.'
   else:definitions[name]=p.read_text(encoding='utf-8-sig')
   continue
  if p.suffix.lower() in ('.csv','.tsv'):
   with p.open(encoding='utf-8-sig',newline='') as f:
    reader=csv.reader(f,delimiter='\t' if p.suffix.lower()=='.tsv' else ',')
    preview=[];width=0;indices=[]
    for i,row in enumerate(reader):
     if i==4:break
     if i==0:
      width=len(row);indices=list(range(width)) if width<=32 else list(range(12))+list(range(width-4,width))
     preview.append([row[j] for j in indices])
   sources[name]={'preview_rows_including_header':preview,'sampled':True,'columns_total':width,'column_indices_shown':indices,'bytes':p.stat().st_size}
   if p.stat().st_size<=4000 and width<=32:sources[name]={'text':p.read_text(encoding='utf-8-sig'),'sampled':False,'bytes':p.stat().st_size}
  elif p.suffix.lower() in ('.txt','.md','.json') and p.stat().st_size<=40000:
   sources[name]={'text':p.read_text(encoding='utf-8-sig'),'sampled':False}
  else:sources[name]={'omitted':True,'bytes':p.stat().st_size}
 submission=safe_path(root,'submission')
 for p in sorted(submission.rglob('*.py')):
  if not p.resolve().is_relative_to(submission.resolve()) or p.is_symlink():raise ValueError('code path outside submission')
  code[p.relative_to(submission).as_posix()]=p.read_text(encoding='utf-8-sig')
 if not code:raise ValueError('no analysis code for coverage review')
 for name,spec in specs.items():
  required.extend({'table':name,'column':c} for c in spec['columns'] if c not in spec.get('key',[]))
  counts={c:collections.Counter() for c in spec['columns']};overflow=collections.Counter();examples=[];n=0
  with safe_path(submission,name).open(encoding='utf-8-sig',newline='') as f:
   for row in csv.DictReader(f):
    n+=1
    if len(examples)<1:examples.append(row)
    for c in counts:
     v=row[c]
     if v in counts[c] or len(counts[c])<4:counts[c][v]+=1
     else:overflow[c]+=1
  outputs[name]={'rows':n,'first_rows':examples,'values':{c:{'observed_counts':dict(counts[c]),'other_value_rows':overflow[c]} for c in counts}}
 result={'version':15,'public_definitions':definitions,'original_source_previews':sources,'submission_code':code,'output_profiles':outputs,'required_columns':required,'source_check_result':snapshot.get('check_result'),
 'limits':'Input CSVs and output profiles are explicit samples/summaries. Review code-to-contract consistency; do not claim independent numerical verification or that unseen rows were inspected.'}
 if len(json.dumps(result,ensure_ascii=False).encode('utf-8'))>650000:raise ValueError('review packet exceeds bound: '+str({k:len(json.dumps(v,ensure_ascii=False).encode('utf-8')) for k,v in result.items()})+'; simplify generated code, never silently omit a required column')
 return result

if __name__=='__main__':
 sys.stdin.reconfigure(encoding='utf-8');sys.stdout.reconfigure(encoding='utf-8')
 ap=argparse.ArgumentParser();ap.add_argument('--public',required=True);a=ap.parse_args()
 print(json.dumps(packet(a.public,json.load(sys.stdin)),ensure_ascii=False))
