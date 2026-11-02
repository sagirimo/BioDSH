"""Source-derived checks for selected output columns, not a scientific answer oracle.

The model supplies an explicit public-spec interpretation. This module executes a
small declarative language directly on unchanged public CSV/TSV inputs; it never
imports submitted code, evaluates Python expressions, or reads private answers.
An incorrect interpretation can still pass. Coverage and this limitation are explicit.
"""
import csv, hashlib, json
from decimal import Decimal, InvalidOperation
from pathlib import Path

def sha(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def within(root,name):
    root=Path(root).resolve();p=(root/name).resolve()
    if not p.is_relative_to(root):raise ValueError('path outside supplied root')
    return p

def number(value):
    try:n=Decimal(str(value))
    except InvalidOperation:raise ValueError('not numeric: '+repr(value))
    if not n.is_finite():raise ValueError('nonfinite number')
    return n

def predicate(row, spec, missing):
    if spec is None:return True
    if not isinstance(spec,dict):raise ValueError('predicate must be an object')
    if set(spec)=={'all'}:return all(predicate(row,s,missing) for s in spec['all'])
    if set(spec)=={'any'}:return any(predicate(row,s,missing) for s in spec['any'])
    if set(spec)=={'not'}:return not predicate(row,spec['not'],missing)
    if set(spec)-{'column','op','value'}:raise ValueError('unknown predicate member')
    value=row[spec['column']];op=spec['op']
    if op=='is_missing':return value in missing
    if op=='is_present':return value not in missing
    other=spec['value']
    if op=='eq':return value==str(other)
    if op=='ne':return value!=str(other)
    if op=='in':
        if not isinstance(other,list):raise ValueError('in requires a list')
        return value in [str(x) for x in other]
    if op in ('lt','le','gt','ge'):
        if value in missing:return False
        a,b=number(value),number(other)
        return {'lt':a<b,'le':a<=b,'gt':a>b,'ge':a>=b}[op]
    raise ValueError('unsupported predicate operation: '+str(op))

def aggregate(rows, spec, missing):
    if not isinstance(spec,dict):raise ValueError('aggregate must be an object')
    if set(spec)-{'kind','column','where','numerator','denominator','skip_missing'}:raise ValueError('unknown aggregate member')
    rows=[r for r in rows if predicate(r,spec.get('where'),missing)]
    kind=spec['kind']
    if kind=='count_rows':return Decimal(len(rows))
    if kind=='ratio':
        a=aggregate(rows,spec['numerator'],missing);b=aggregate(rows,spec['denominator'],missing)
        if b==0:raise ValueError('zero denominator; no inferred missing-value convention')
        return a/b
    values=[r[spec['column']] for r in rows]
    if spec.get('skip_missing') is True:values=[v for v in values if v not in missing]
    if kind=='count_distinct':return Decimal(len(set(values)))
    if kind not in ('sum','mean'):raise ValueError('unsupported aggregate: '+str(kind))
    nums=[number(v) for v in values]
    if kind=='sum':return sum(nums,Decimal(0))
    if not nums:raise ValueError('mean of empty cohort')
    return sum(nums,Decimal(0))/len(nums)

def check(public,submission,snapshot,declared_tables,max_rows=1000000):
    result={'ok':False,'scope':'selected public-source consistency checks','scientific_correctness_verified':False,
            'independent_reimplementation':False,'errors':[],'rules':[],'checked_cells':0,'checked_columns':[],
            'unverified_columns':[],'interpretation_limit':'A valid public quotation does not prove the model interpreted it correctly.'}
    errors=result['errors'];cache={};verified=set();plan=snapshot.get('plan');manifest=snapshot.get('public_files',{})
    def source(name):
        if name not in manifest:raise ValueError('source was not in initial public snapshot: '+str(name))
        p=within(public,name)
        if name not in verified:
            if sha(p)!=manifest[name]:raise ValueError('public input changed: '+name)
            verified.add(name)
        return p
    def table(p):
        key=str(p)
        if key not in cache:
            with p.open(encoding='utf-8-sig',newline='') as f:
                reader=csv.DictReader(f,delimiter='\t' if p.suffix.lower()=='.tsv' else ',')
                names=reader.fieldnames
                if not names or len(names)!=len(set(names)):raise ValueError('missing or duplicate CSV header')
                rows=[]
                for r in reader:
                    if None in r or any(v is None for v in r.values()):raise ValueError('malformed CSV row')
                    rows.append(r)
                    if len(rows)>max_rows:raise ValueError('semantic checker row limit exceeded; no silent sampling')
            cache[key]=(names,rows)
        return cache[key]
    try:
        if not isinstance(plan,dict) or plan.get('version')!=1:raise ValueError('semantic plan version 1 required')
        if set(plan)-{'version','rules','unverified'}:raise ValueError('unknown semantic plan member')
        rules=plan.get('rules')
        if not isinstance(rules,list) or not rules:raise ValueError('at least one executable source check required')
        if len(rules)>300:raise ValueError('semantic rule limit exceeded')
        if any(not isinstance(r,dict) for r in rules):raise ValueError('rules must be objects')
        ids=[r.get('id') for r in rules]
        if any(not isinstance(x,str) or not x for x in ids) or len(set(ids))!=len(ids):raise ValueError('unique nonempty rule IDs required')
        checked=set()
        for rule in rules:
            record={'id':rule['id'],'checked_cells':0,'mismatches':[],'mismatch_count':0}
            result['rules'].append(record)
            try:
                allowed={'id','operation','source','target','target_column','keys','citation','missing_tokens','where','aggregate','source_column','predicate'}
                if set(rule)-allowed:raise ValueError('unknown rule members (literal expected answers are unsupported)')
                cite=rule['citation'];quote=cite['quote']
                if not isinstance(quote,str) or len(quote.strip())<8:raise ValueError('specific verbatim public definition required')
                if quote not in source(cite['path']).read_text(encoding='utf-8-sig'):raise ValueError('citation not found in unchanged public material')
                src=source(rule['source'])
                if src.suffix.lower() not in ('.csv','.tsv'):raise ValueError('only original public CSV/TSV sources supported')
                target=rule['target'];column=rule['target_column']
                if target not in declared_tables or column not in declared_tables[target]['columns']:raise ValueError('target column not in public output contract')
                source_columns,rows=table(src);target_columns,outputs=table(within(submission,target))
                if column not in target_columns:raise ValueError('target column missing')
                keys=rule.get('keys',[])
                if not isinstance(keys,list) or any(not isinstance(k,list) or len(k)!=2 for k in keys):raise ValueError('keys must be [target_column, source_column] pairs')
                if len({k[0] for k in keys})!=len(keys):raise ValueError('duplicate key mapping')
                if any(a not in target_columns or b not in source_columns for a,b in keys):raise ValueError('unknown key column')
                missing=rule.get('missing_tokens',[''])
                if not isinstance(missing,list) or any(not isinstance(x,str) for x in missing):raise ValueError('missing tokens must be explicit strings')
                # Index original input by declared identity. Do not borrow an agent-generated intermediate cohort.
                groups={}
                for r in rows:
                    if predicate(r,rule.get('where'),missing):groups.setdefault(tuple(r[b] for a,b in keys),[]).append(r)
                seen=set();operation=rule['operation']
                for out in outputs:
                    key=tuple(out[a] for a,b in keys)
                    if key in seen:raise ValueError('target identity is not unique for this rule; extend key mapping')
                    seen.add(key);matches=groups.get(key,[])
                    if operation=='aggregate':expected=aggregate(matches,rule['aggregate'],missing)
                    elif operation in ('preserve','predicate'):
                        if len(matches)!=1:raise ValueError('source identity must match exactly one row')
                        expected=matches[0][rule['source_column']] if operation=='preserve' else str(int(predicate(matches[0],rule['predicate'],missing)))
                    else:raise ValueError('unsupported rule operation')
                    actual=out[column]
                    if isinstance(expected,Decimal):
                        observed=number(actual)
                        # Discrete quantities are exact. No model-selected tolerance or grader expected value.
                        exact=rule['aggregate']['kind'] in ('count_rows','count_distinct')
                        equal=observed==expected if exact else abs(observed-expected)<=max(Decimal('1e-12'),Decimal('1e-9')*max(abs(observed),abs(expected)))
                    else:equal=actual==expected
                    record['checked_cells']+=1
                    if not equal:
                        record['mismatch_count']+=1
                        if len(record['mismatches'])<20:record['mismatches'].append({'key':list(key),'actual':actual,'source_derived':str(expected)})
                if not outputs:raise ValueError('no output cells checked')
                record['ok']=not record['mismatches'];checked.add((target,column))
                result['checked_cells']+=record['checked_cells']
                if not record['ok']:errors.append(rule['id']+': source-derived value mismatch')
            except (OSError,KeyError,TypeError,ValueError,InvalidOperation) as e:
                record['ok']=False;record['error']=str(e);errors.append(rule['id']+': '+str(e))
        result['checked_columns']=[{'table':t,'column':c} for t,c in sorted(checked)]
        result['unverified_columns']=[{'table':t,'column':c} for t,s in declared_tables.items() for c in s['columns'] if (t,c) not in checked]
        result['model_declared_unverified']=plan.get('unverified',[])
        result['ok']=not errors and result['checked_cells']>0
    except (OSError,KeyError,TypeError,ValueError) as e:errors.append(str(e))
    return result
