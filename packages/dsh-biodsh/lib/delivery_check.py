"""Deterministic public-contract validation and clean-directory replay. No model or grader imports."""
import argparse, csv, hashlib, json, math, operator, os, re, shutil, signal, subprocess, sys, tempfile, time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from compare_outputs import expected_keys, load_table, equal
from semantic_check import check as check_semantics

CONTRACT_FILES = ('TABLE_CONTRACT.json','ROW_SETS.json','PUBLIC_OUTPUT_NAMING_AND_TYPES.json','CLAIMS.json')
NUMERIC = {'float','int','number','integer'}

def read_json(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))

def safe_path(root, name):
    p = (Path(root)/name).resolve()
    if not p.is_relative_to(Path(root).resolve()):
        raise ValueError('path escapes supplied directory')
    return p

def contracts(public):
    return {n: read_json(safe_path(public,n)) for n in CONTRACT_FILES if (Path(public)/n).is_file()}

def table_specs(docs):
    contract=docs.get('TABLE_CONTRACT.json',{})
    rows=docs.get('ROW_SETS.json',{})
    naming=docs.get('PUBLIC_OUTPUT_NAMING_AND_TYPES.json',{})
    specs={n:dict(s) for n,s in contract.get('tables',{}).items()}
    for n,s in naming.get('tables',{}).items():
        spec=specs.setdefault(n,{'columns':s['columns'],'key':s.get('key_columns',[]),'types':{}})
        for c in s.get('numeric_columns',[]):spec.setdefault('types',{}).setdefault(c,'float')
        spec['fields']=s.get('fields',{})
    for n,s in specs.items():
        if n in rows.get('tables',{}):
            # Both public expressions are checked, rather than silently overwriting one.
            s['external_row_set']=rows['tables'][n]
        s.setdefault('row_set',rows.get('tables',{}).get(n,{}))
        if not s.get('key') or not set(s['key'])<=set(s['columns']):raise ValueError('invalid key declaration: '+n)
    definitions={}
    for src in (contract,rows):
        for k in ('row_set_definitions','sets','definitions'):
            for name,value in src.get(k,{}).items():
                if name in definitions and definitions[name]!=value:raise ValueError('conflicting row-set definition: '+name)
                definitions[name]=value
    return specs,{'definitions':definitions}

def check_json_schema(value,spec,where,issues):
    kind=spec.get('json_type')
    ok={'object':lambda:isinstance(value,dict),'array':lambda:isinstance(value,list),
        'number':lambda:type(value) in (int,float),'integer':lambda:type(value) is int,
        'string':lambda:isinstance(value,str),'boolean':lambda:type(value) is bool}
    if kind in ok and not ok[kind]():issues.append(where+': JSON type '+kind);return
    if spec.get('finite') and (type(value) not in (int,float) or not math.isfinite(value)):issues.append(where+': nonfinite')
    if spec.get('numeric_flag_0_or_1') and value not in (0,1):issues.append(where+': expected numeric 0/1')
    if spec.get('nonempty_after_whitespace_strip') and not value.strip():issues.append(where+': empty string')
    if isinstance(value,dict):
        if 'keys_exact' in spec and set(value)!=set(spec['keys_exact']):issues.append(where+': exact keys mismatch')
        for k in spec.get('required_members',[]):
            if k not in value:issues.append(where+': missing member '+k)
        for k,s in spec.get('fields',{}).items():
            if k not in value:issues.append(where+': missing field '+k)
            else:check_json_schema(value[k],s,where+'.'+k,issues)
        for k,t in spec.get('types',{}).items():
            if k not in value:issues.append(where+': missing typed member '+k)
            else:check_json_schema(value[k],{'json_type':t},where+'.'+k,issues)
        # Only use field/type declarations, never public_expected_members or answer-like constants.
        for k,s in spec.items():
            if isinstance(s,dict) and 'json_type' in s and k in value:check_json_schema(value[k],s,where+'.'+k,issues)

def binding_value(binding,tables):
    _,rows=tables[binding['table']]
    keys=binding.get('keys',{binding.get('key_column'):binding.get('key')})
    found=[r for r in rows.values() if all(r.get(k)==str(v) for k,v in keys.items())]
    if len(found)!=1:raise ValueError('binding must select exactly one row')
    return float(found[0][binding['column']])

def validate(public,submission,docs=None):
    docs=contracts(public) if docs is None else docs
    result={'triggered':bool(docs),'ok':True,'errors':[],'warnings':[],'tables':{}}
    if not docs:return result
    errors=result['errors'];warn=result['warnings'];loaded={}
    try:specs,defs=table_specs(docs)
    except (KeyError,ValueError,TypeError) as e:
        result.update(ok=False,errors=['invalid public contract: '+str(e)]);return result
    if not specs:warn.append('No machine-readable table schema; only declared JSON checks apply.')
    for name,spec in specs.items():
        try:
            header,rows,issues=load_table(safe_path(submission,name),spec)
            loaded[name]=(spec,rows)
            errors.extend(name+': '+i for i in issues[:10])
            entry={'rows':len(rows),'key_set_checked':False};result['tables'][name]=entry
            for r in [spec.get('row_set',{}),spec.get('external_row_set',{})]:
                if not r:continue
                try:expected=expected_keys(dict(spec,row_set=r),defs)
                except (KeyError,ValueError,TypeError,RecursionError) as e:
                    errors.append(name+': cannot expand declared row set: '+str(e));continue
                if expected is not None:
                    entry['key_set_checked']=True;actual=set(rows)
                    if actual!=expected:
                        errors.append(name+': key_set mismatch '+json.dumps({'missing_count':len(expected-actual),'extra_count':len(actual-expected),'missing':sorted(expected-actual)[:5],'extra':sorted(actual-expected)[:5]},ensure_ascii=False))
                if type(r.get('row_count')) is int and r['row_count']!=len(rows):errors.append(name+': row_count mismatch')
                elif 'row_count' in r and type(r['row_count']) is not int:warn.append(name+': prose row-count rule not executable')
            if not entry['key_set_checked']:warn.append(name+': no public exact key set; uniqueness only')
            cell_errors=[];unspecified_missing=set()
            for key,row in rows.items():
                for col in spec['columns']:
                    v=row.get(col);typ=spec.get('types',{}).get(col,'text');field=spec.get('fields',{}).get(col,{})
                    missing=spec.get('missing_values',{});markers=missing.get(col,[]) if isinstance(missing,dict) else missing
                    declared=(isinstance(missing,dict) and col in missing) or (isinstance(missing,list))
                    global_missing=docs.get('TABLE_CONTRACT.json',{}).get('missing')
                    if not declared and isinstance(global_missing,str):
                        token=re.split(r'[;；]',global_missing)[0].strip()
                        if token in ('NA','NaN','nan','null','__NA__'):
                            markers=[token];declared=True
                    if isinstance(markers,str):markers=[markers]
                    # Missing markers require an explicit machine-readable declaration; do not infer prose.
                    if v in markers and col not in spec['key']:continue
                    if not declared and typ in NUMERIC and col not in spec['key'] and v in ('','NA','NaN','nan','null','__NA__'):
                        unspecified_missing.add((col,v));continue
                    error=None
                    if v is None:error='missing cell'
                    elif col in spec['key'] and v=='':error='empty key'
                    elif typ in NUMERIC:
                        try:
                            number=Decimal(v)
                            if not number.is_finite():error='nonfinite or undeclared missing marker'
                            elif typ in ('int','integer') and number!=number.to_integral_value():error='not an integer'
                        except (ValueError,OverflowError,InvalidOperation):error='not numeric or undeclared missing marker'
                    elif typ in ('bool','boolean') and v not in ('true','false','0','1'):error='not boolean'
                    elif typ not in ('text','string','bool','boolean'):error='unsupported declared type '+str(typ)
                    options=field.get('allowed_values',spec.get('enums',{}).get(col))
                    if options is not None and v not in list(map(str,options)):error='not in declared enum'
                    if error and len(cell_errors)<10:cell_errors.append(f'{name}: {key!r} {col}: {error} ({v!r})')
            errors.extend(cell_errors)
            if unspecified_missing:warn.append(name+': missing marker applicability is unspecified in machine-readable contracts; not validated: '+repr(sorted(unspecified_missing)))
        except (OSError,ValueError,TypeError,KeyError) as e:errors.append(name+': '+str(e))
    naming=docs.get('PUBLIC_OUTPUT_NAMING_AND_TYPES.json',{})
    for name in naming.get('delivery',{}).get('required_csv_files',[]):
        if not safe_path(submission,name).is_file():errors.append(name+': missing_file')
    for name,spec in naming.get('delivery',{}).items():
        if not name.endswith('.json') or not isinstance(spec,dict):continue
        try:check_json_schema(read_json(safe_path(submission,name)),spec,name,errors)
        except (OSError,ValueError):errors.append(name+': missing or invalid JSON')
    if 'CLAIMS.json' in docs:
        try:
            c=read_json(safe_path(submission,'interpretation_claims.json'))
            if not isinstance(c,dict) or set(c)!={'schema_version','claims','narrative'}:raise ValueError('expected schema_version, claims, narrative object')
            if type(c['schema_version']) is not int or c['schema_version']!=2:raise ValueError('schema_version must be integer 2')
            if not isinstance(c['narrative'],str) or not c['narrative'].strip():raise ValueError('narrative must be nonempty')
            declarations=docs['CLAIMS.json']['claims']
            if not isinstance(c['claims'],dict) or set(c['claims'])!={s['id'] for s in declarations}:raise ValueError('claims exact key set mismatch')
            for s in declarations:
                name=s['id'];v=c['claims'][name];typ=s['type']
                if typ=='number':
                    if type(v) not in (int,float) or not math.isfinite(v):errors.append('claim '+name+': expected finite number');continue
                    if 'binding' in s:
                        try:
                            n=binding_value(s['binding'],loaded)
                            if not math.isclose(v,n,rel_tol=s.get('rel_tol',0),abs_tol=s.get('abs_tol',0)):errors.append('claim '+name+': table binding mismatch')
                        except (ValueError,KeyError,TypeError):errors.append('claim '+name+': invalid table binding')
                elif typ in ('derived','choice'):
                    if not isinstance(v,str) or v not in s.get('options',[]):errors.append('claim '+name+': not a declared option')
                    if typ=='derived' and 'rule' in s:
                        rule=s['rule'];ops={'lt':operator.lt,'le':operator.le,'gt':operator.gt,'ge':operator.ge,'eq':operator.eq,'ne':operator.ne}
                        try:
                            flag=ops[rule['op']](binding_value(rule['binding'],loaded),rule['threshold'])
                            if v!=rule['outcomes'][str(flag).lower()]:errors.append('claim '+name+': public derived rule mismatch')
                        except (ValueError,KeyError,TypeError):errors.append('claim '+name+': unsupported or invalid public rule')
                else:errors.append('claim '+name+': unsupported type')
        except (OSError,ValueError,KeyError,TypeError) as e:errors.append('interpretation_claims.json: '+str(e))
    result['ok']=not errors
    return result


def compare_deliveries(public,a,b,docs=None,rtol=0,atol=0,use_contract_tolerance=False):
    docs=contracts(public) if docs is None else docs
    specs,_=table_specs(docs);differences=[]
    for name,spec in specs.items():
        _,ra,ia=load_table(safe_path(a,name),spec);_,rb,ib=load_table(safe_path(b,name),spec)
        if ia or ib or set(ra)!=set(rb):differences.append({'file':name,'issue':'structure/key difference'});continue
        for key in sorted(ra):
            for col in spec['columns']:
                tolerance=spec.get('tolerance',{}).get(col,[rtol,atol]) if use_contract_tolerance else [rtol,atol]
                if not equal(ra[key][col],rb[key][col],col not in spec['key'] and spec.get('types',{}).get(col) in NUMERIC,*tolerance):
                    if len(differences)<50:differences.append({'file':name,'key':key,'column':col,'A':ra[key][col],'B':rb[key][col]})
    names={'interpretation_claims.json'} if 'CLAIMS.json' in docs else set()
    names.update(n for n in docs.get('PUBLIC_OUTPUT_NAMING_AND_TYPES.json',{}).get('delivery',{}) if n.endswith('.json'))
    for name in sorted(names):
        try:
            ja,jb=read_json(safe_path(a,name)),read_json(safe_path(b,name))
            # Explanatory prose is not an analytical result. Structured answers and diagnostics are compared.
            if isinstance(ja,dict) and isinstance(jb,dict):
                ja={k:v for k,v in ja.items() if k not in ('narrative','reasoning')};jb={k:v for k,v in jb.items() if k not in ('narrative','reasoning')}
            if name=='interpretation_claims.json' and use_contract_tolerance and isinstance(ja,dict) and isinstance(jb,dict):
                for s in docs['CLAIMS.json']['claims']:
                    if s.get('type')=='number':
                        ca=ja.get('claims',{});cb=jb.get('claims',{});k=s['id']
                        if k in ca and k in cb and equal(ca[k],cb[k],True,s.get('rel_tol',0),s.get('abs_tol',0)):cb[k]=ca[k]
            if ja!=jb:differences.append({'file':name,'issue':'JSON content difference','A':ja,'B':jb})
        except (OSError,ValueError):differences.append({'file':name,'issue':'missing/invalid JSON'})
    return {'agree':not differences,'differences':differences,'numeric_policy':{'rtol':rtol,'atol':atol,'public_contract_tolerance':use_contract_tolerance}}


def replay(public,submission,docs,seconds=120,temp_root=None):
    start=time.monotonic();root=Path(tempfile.mkdtemp(prefix='v13_delivery_',dir=temp_root))
    # Retain evidence; no deletion of user files or prior replay artifacts.
    inp=root/'inputs';out=root/'out';out.mkdir();cwd=root/'cwd';cwd.mkdir()
    result={'ok':False,'root':str(root),'seconds':None}
    try:
        source=safe_path(submission,'analysis.py')
        if not source.is_file():raise ValueError('analysis.py missing')
        shutil.copy2(source,root/'submitted.py')
        source_inputs=Path(public)/'inputs'
        if any(p.is_symlink() for p in source_inputs.rglob('*')):raise ValueError('input symlink unsupported')
        shutil.copytree(source_inputs,inp)
        bootstrap=root/'replay_bootstrap.py'
        bootstrap.write_text('''import sys, runpy, importlib.abc
class AllowedImports(importlib.abc.MetaPathFinder):
 def find_spec(self, fullname, path=None, target=None):
  top=fullname.split('.')[0]
  if not top.startswith('_sysconfigdata_') and top not in sys.stdlib_module_names and top not in {'numpy','scipy','pandas','dateutil','pytz','tzdata','six'}:
   raise ImportError('Replay dependency outside numpy/scipy/pandas: '+top)
sys.meta_path.insert(0,AllowedImports())
script=sys.argv.pop(1)
runpy.run_path(script,run_name='__main__')
''')
        env={k:v for k,v in os.environ.items() if k in ('PATH','SYSTEMROOT','WINDIR','LANG','LC_ALL')}
        env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1',PYTHONDONTWRITEBYTECODE='1',HOME=str(root))
        def limits():
            import resource
            resource.setrlimit(resource.RLIMIT_CPU,(max(1,int(seconds)),max(2,int(seconds)+1)))
            resource.setrlimit(resource.RLIMIT_AS,(1024**3,1024**3))
            resource.setrlimit(resource.RLIMIT_FSIZE,(8*1024**2,8*1024**2))
        cmd=[sys.executable,'-I','-B',str(bootstrap),str(root/'submitted.py'),'--inputs',str(inp),'--out',str(out)]
        with (root/'stdout.log').open('wb') as so,(root/'stderr.log').open('wb') as se:
            p=subprocess.Popen(cmd,cwd=cwd,env=env,stdout=so,stderr=se,start_new_session=(os.name=='posix'),preexec_fn=limits if os.name=='posix' else None)
            try:p.wait(timeout=seconds)
            except subprocess.TimeoutExpired:
                if os.name=='posix':os.killpg(p.pid,signal.SIGKILL)
                else:p.kill()
                p.wait();raise ValueError('replay wall-clock timeout')
        result['returncode']=p.returncode
        if p.returncode:raise ValueError('replay exit '+str(p.returncode)+': '+(root/'stderr.log').read_text(errors='replace')[-2000:])
        structure=validate(public,out,docs);result['validation']=structure
        comparison=compare_deliveries(public,submission,out,docs,use_contract_tolerance=True);result['comparison']=comparison
        if not (out/'analysis.py').is_file():structure['errors'].append('replay did not deliver analysis.py');structure['ok']=False
        result['ok']=structure['ok'] and comparison['agree']
    except (OSError,ValueError) as e:result['error']=str(e)
    result['seconds']=round(time.monotonic()-start,3)
    return result


def run_reconcile_checks(submission, replay_result, seconds=120):
    """v17: the reconciliation stage's own executable checks, run on the clean replay outputs.

    The script recomputes declared quantities from original inputs and compares them with delivered cells;
    claims in reconciliation.json are not trusted unless a check printed PASS for them."""
    result = {'ok': False, 'checks': 0, 'failed': []}
    script = safe_path(submission, 'reconcile_checks.py')
    if not script.is_file():
        result['error'] = 'submission/reconcile_checks.py missing'; return result
    root = Path(replay_result['root'])
    cmd = [sys.executable, '-I', '-B', str(script), '--inputs', str(root / 'inputs'), '--outputs', str(root / 'out')]
    env = {k: v for k, v in os.environ.items() if k in ('PATH', 'SYSTEMROOT', 'WINDIR', 'LANG', 'LC_ALL')}
    env.update(PYTHONDONTWRITEBYTECODE='1', HOME=str(root), PYTHONIOENCODING='utf-8')
    try:
        p = subprocess.run(cmd, cwd=str(root / 'cwd'), env=env, capture_output=True, timeout=seconds)
    except subprocess.TimeoutExpired:
        result['error'] = 'reconcile_checks.py timeout'; return result
    out = p.stdout.decode('utf-8', 'replace')
    lines = [l for l in out.splitlines() if l.startswith('CHECK ')]
    result['checks'] = len(lines)
    result['failed'] = [l for l in lines if ' FAIL ' in l][:20]
    result['returncode'] = p.returncode
    result['stdout_tail'] = out[-3000:]
    result['stderr_tail'] = p.stderr.decode('utf-8', 'replace')[-2000:]
    result['ok'] = p.returncode == 0 and len(lines) > 0 and not result['failed']
    if not lines: result['error'] = 'no CHECK lines printed'
    return result


def main():
    # Node writes UTF-8 JSON to the pipe. Windows' GBK stdin would silently
    # change Chinese contract text and create a false input-change alarm.
    sys.stdin.reconfigure(encoding='utf-8')
    sys.stdout.reconfigure(encoding='utf-8')
    ap=argparse.ArgumentParser();ap.add_argument('--public',required=True);ap.add_argument('--submission');ap.add_argument('--snapshot-stdin',action='store_true');ap.add_argument('--no-replay',action='store_true');ap.add_argument('--seconds',type=int,default=120);ap.add_argument('--temp-root');ap.add_argument('--out');ap.add_argument('--reconcile-checks',action='store_true');a=ap.parse_args()
    try:
        docs=contracts(a.public);semantic=None
        if a.snapshot_stdin:
            snapshot=json.load(sys.stdin)
            if snapshot.get('__biodsh_snapshot_version')==14:
                semantic=snapshot['semantic'];snapshot=snapshot['contracts']
            if docs!=snapshot:raise ValueError('public contract changed after session start')
            docs=snapshot
        submission=a.submission or str(Path(a.public)/'submission')
        r=validate(a.public,submission,docs)
        if semantic is not None:
            r['semantic']=check_semantics(a.public,submission,semantic,table_specs(docs)[0])
            r['ok']=r['ok'] and r['semantic']['ok']
            r['errors'].extend('semantic: '+e for e in r['semantic']['errors'])
        if r['triggered'] and r['ok'] and not a.no_replay:
            r['replay']=replay(a.public,submission,docs,a.seconds,a.temp_root)
            r['ok']=r['ok'] and r['replay']['ok']
            if not r['replay']['ok']:r['errors'].append('replay failed: '+json.dumps(r['replay'],ensure_ascii=False))
            elif a.reconcile_checks:
                r['reconcile_checks']=run_reconcile_checks(submission,r['replay'],a.seconds)
                r['ok']=r['ok'] and r['reconcile_checks']['ok']
                if not r['reconcile_checks']['ok']:r['errors'].append('reconcile_checks failed: '+json.dumps(r['reconcile_checks'],ensure_ascii=False))
    except Exception as e:r={'triggered':True,'ok':False,'errors':[type(e).__name__+': '+str(e)]}
    text=json.dumps(r,ensure_ascii=False,indent=2)
    if a.out:Path(a.out).write_text(text+'\n',encoding='utf-8')
    print(text)
    return 0 if r['ok'] else 1
if __name__=='__main__':sys.exit(main())
