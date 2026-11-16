#!/usr/bin/env python3
"""Offline admission triage. 0=no blocking signal, 1=A/B, 2=unreadable/unreviewed input.

A/B are review candidates, not proof of contamination. C is informational.
No network, model calls, pickle execution, or mutations. Scan ALL regular files,
including references, scripts, hidden files, test fixtures and old SKILL copies.
Optional --questions accepts JSON records with question/task_id or CSV question fields.
--reviewed-binary accepts {sha256: reason} reviewed binary hashes; changed files block.
"""
import argparse,csv,hashlib,json,re,sys
from pathlib import Path
BENCH=re.compile(r'\b(?:BixBench|bix-\d+(?:-q\d+)?|LAB[-_ ]?Bench2?|BioCoder|ScienceAgentBench|BLADE|DiscoveryBench|BioASQ|MedQA|PubMedQA|GPQA|HLE|BioMed[-_ ]?AQA|MESINESP)\b',re.I)
DIRECTION=re.compile(r'coverage|patterns?|answer extraction|answering|designed (?:for|to)|questions?|expected outputs|validated on|support|solve',re.I)
KEYWORDS=re.compile(r'expected\s+answer|correct\s+answer|\banswer\s*:|\bexam\b|试题|答案|the question asks|这道题',re.I)
RULES=[
 ('A','specific-worked-workflow',re.compile(r'Complete Example: bix-\d+ Workflow',re.I)),
 ('A','worked-exam-solutions',re.compile(r'Worked (?:Exam )?Solutions|Gold records|gold 全部\s*\d+\s*个|TaskB Q[1-9].*漏|答案格式从密封答案的 ideal',re.I)),
 ('A','fixed-answer-correction',re.compile(r'correct answer[^\n]{0,200}\bis\s*\**\d+\**\s*,?\s*not\s+\d+|正确答案[^\n]{0,50}(?:不是|而非)',re.I)),
 ('A','explicit-exam-answer',re.compile(r'Q\d+\s+(?:Qsymia|sonidegib|儿科脑肿瘤)|Claude:.*identifies CD14 Monocytes',re.I)),
 ('B','exam-gold-calibration',re.compile(r'exam gold answers|gold.*(?:必含|宁多勿少)|判分陷阱|参考 gold 分布|typical exam size|rely on gold IDs directly|金标准.*人口学|benchmark.*评判陷阱',re.I)),
]
def normalized(t):return re.findall(r'[a-z0-9]+',t.lower())
def corpus_index(path,n=12):
 if not path:return {}
 p=Path(path)
 if p.suffix=='.csv':rows=list(csv.DictReader(p.open(encoding='utf8-sig')))
 else:
  rows=json.loads(p.read_text());rows=rows.get('questions',rows.get('records',[])) if isinstance(rows,dict) else rows
 idx={}
 for row in rows:
  ts=normalized(str(row.get('question',''))+' '+str(row.get('mcq_question','')))
  for i in range(len(ts)-n+1):idx.setdefault(tuple(ts[i:i+n]),set()).add(str(row.get('task_id',row.get('question_id',row.get('id','unknown')))))
 return idx

def scan_text(text,path='<text>',corpus=None):
 out=[];lines=text.splitlines();bench_present=bool(BENCH.search(text))
 for i,line in enumerate(lines,1):
  hits=[]
  for level,rule,rx in RULES:
   if rx.search(line):hits.append((level,rule))
  if re.search(r'Expected:\s*[\d.]+[-–][\d.]+',line,re.I) and re.search(r'bix-\d+', '\n'.join(lines[max(0,i-5):i]),re.I):hits.append(('A','question-specific-expected-range'))
  if BENCH.search(line):
   if re.search(r'BioASQ format',line,re.I):hits.append(('C','generic-QA-format'))
   elif re.search(r'\bbix-\d+',line,re.I) or DIRECTION.search(line):hits.append(('B','benchmark-directed'))
   else:hits.append(('C','benchmark-mention'))
  elif KEYWORDS.search(line) and not hits:hits.append(('C','generic-answer-or-exam-word'))
  for level,rule in hits:out.append(dict(file=str(path),line=i,level=level,pattern=rule,excerpt=line[:1000]))
 # Filename is contextual evidence, not enough to label arbitrary test fixtures.
 if re.search(r'[/\\]qrels[/\\]test\.(?:tsv|txt)$',str(path),re.I) and re.match(r'query-id\tcorpus-id\tscore',text):out.append(dict(file=str(path),line=1,level='A',pattern='evaluation-relevance-labels',excerpt=text[:300]))
 if '23479819' in text and '"Luminescence", "Vibrio", "Luciferases"' in text:out.append(dict(file=str(path),line=next((i for i,l in enumerate(lines,1) if '"Luminescence", "Vibrio"' in l),1),level='A',pattern='known-taskA-answer',excerpt='TaskA PMID 23479819 seven-label answer'))
 if corpus:
  words=list(re.finditer(r'[a-z0-9]+',text.lower()));ts=[m.group() for m in words]
  seen=set()
  for i in range(len(ts)-11):
   key=tuple(ts[i:i+12])
   if key in corpus:
    q=','.join(sorted(corpus[key]));ln=text[:words[i].start()].count('\n')+1
    if q not in seen:out.append(dict(file=str(path),line=ln,level='B',pattern='question-overlap-12gram:'+q,excerpt=' '.join(key)));seen.add(q)
 return out

def scan_paths(roots,corpus=None,reviewed=None):
 out=[];counts={'files':0,'bytes':0,'binary_reviewed':0};reviewed=reviewed or {}
 for root in roots:
  root=Path(root)
  if not root.exists():out.append(dict(file=str(root),line=0,level='U',pattern='missing-input',excerpt=''));continue
  files=[root] if root.is_file() else sorted(root.rglob('*'))
  for p in files:
   if p.is_symlink():out.append(dict(file=str(p),line=0,level='U',pattern='symlink-needs-review',excerpt=''));continue
   if not p.is_file():continue
   counts['files']+=1
   try:b=p.read_bytes();counts['bytes']+=len(b)
   except OSError as e:out.append(dict(file=str(p),line=0,level='U',pattern='read-error',excerpt=type(e).__name__));continue
   try:t=b.decode('utf8')
   except UnicodeDecodeError:
    if hashlib.sha256(b).hexdigest() in reviewed:counts['binary_reviewed']+=1
    else:out.append(dict(file=str(p),line=0,level='U',pattern='binary-needs-review',excerpt='No semantic pass inferred from raw-byte keyword absence.'))
    t=b.decode('utf8',errors='replace')
   out.extend(scan_text(t,p,corpus))
 return out,counts

def main(argv=None):
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('roots',nargs='+');ap.add_argument('--questions');ap.add_argument('--reviewed-binary');a=ap.parse_args(argv)
 reviewed=json.loads(Path(a.reviewed_binary).read_text()) if a.reviewed_binary else {}
 hits,counts=scan_paths(a.roots,corpus_index(a.questions),reviewed)
 print(json.dumps(dict(counts=counts,hits=hits),ensure_ascii=False,indent=1))
 return 2 if any(x['level']=='U' for x in hits) else 1 if any(x['level'] in ('A','B') for x in hits) else 0
if __name__=='__main__':sys.exit(main())
