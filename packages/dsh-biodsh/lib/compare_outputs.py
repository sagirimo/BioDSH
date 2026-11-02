#!/usr/bin/env python3
"""Public-only, contract-key-aligned candidate comparator; no grading imports.
Numeric non-key fields: symmetric rtol=1e-4, atol=1e-8 by default.
Exact text keys/types; row/column order ignored. AST summaries are heuristics.
"""
import argparse, ast, collections, csv, difflib, itertools, json, math
from pathlib import Path


def read_json(p, default=None):
    return json.loads(p.read_text(encoding='utf-8-sig')) if p.is_file() else default


def expand(x, definitions):
    if isinstance(x, list):
        return [(str(v),) for v in x]
    if 'set_ref' in x:
        return expand(definitions[x['set_ref']], definitions)
    if 'integer_range' in x:
        a,b=x['integer_range']
        return [(x.get('prefix','')+str(i).zfill(x.get('zero_pad',0))+x.get('suffix',''),) for i in range(a,b+1)]
    if 'cartesian' in x:
        return [sum(z,()) for z in itertools.product(*(expand(v,definitions) for v in x['cartesian']))]
    if 'branches' in x:
        return [head+tail for b in x['branches'] for head in expand(b['values'],definitions) for tail in expand(b['then'],definitions)]
    raise ValueError('Unsupported public key expression')


def expected_keys(spec, rowsets):
    r=spec.get('row_set') or {}
    if 'domains' in r:
        return set(itertools.product(*(map(str,r['domains'][k]) for k in spec['key'])))
    if 'key_tuples' in r:
        return {tuple(map(str,v)) for v in r['key_tuples']}
    if 'key_set' in r:
        defs=rowsets.get('definitions',rowsets.get('sets',rowsets.get('row_set_definitions',{})))
        keys=expand(r['key_set'],defs)
        if 'composite_key' in r:
            keys=[(r['composite_key'].get('join','|').join(k),) for k in keys]
        return set(keys)
    return None


def load_table(p, spec):
    if not p.is_file():
        return [],{},['missing_file']
    issues=[]; rows={}
    with p.open(encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f,delimiter='\t' if p.suffix=='.tsv' else ',')
        header=reader.fieldnames or []
        if len(header)!=len(set(header)): issues.append('duplicate_columns')
        if set(header)!=set(spec['columns']): issues.append('column_set_mismatch')
        if not set(spec['key'])<=set(header): return header,{},issues+['missing_key_columns']
        for row in reader:
            if None in row or None in row.values(): issues.append('malformed_row')
            key=tuple(row.get(k) for k in spec['key'])
            if key in rows: issues.append('duplicate_key:'+repr(key))
            rows[key]=row
    return header,rows,issues


def equal(a,b,numeric,rtol,atol):
    if a is None or b is None: return a is b
    if not numeric: return a==b
    try:
        x,y=float(a),float(b)
        return math.isclose(x,y,rel_tol=rtol,abs_tol=atol) or (math.isnan(x) and math.isnan(y))
    except (ValueError,TypeError): return a==b


def code_steps(p):
    if not p.is_file(): return {'error':'analysis.py missing'}
    try: tree=ast.parse(p.read_text(encoding='utf-8-sig'))
    except (SyntaxError,UnicodeError) as e: return {'error':type(e).__name__}
    result={'filters':[], 'denominators':[], 'method_parameters':[]}
    for node in ast.walk(tree):
        category=None
        if isinstance(node,(ast.Compare,ast.If,ast.IfExp)): category='filters'
        elif isinstance(node,ast.BinOp) and isinstance(node.op,ast.Div): category='denominators'
        elif isinstance(node,ast.Call) and (node.keywords or any(isinstance(a,ast.Constant) for a in node.args)): category='method_parameters'
        if category:
            s=ast.unparse(node.test if isinstance(node,(ast.If,ast.IfExp)) else node)
            if s not in result[category]: result[category].append(s[:600])
    return result


def compare(public,a,b,n=5,rtol=1e-4,atol=1e-8,code=True,contract_tolerance=False):
    public,a,b=map(Path,(public,a,b))
    contract=read_json(public/'TABLE_CONTRACT.json'); rowsets=read_json(public/'ROW_SETS.json',{})
    naming=read_json(public/'PUBLIC_OUTPUT_NAMING_AND_TYPES.json',{})
    result={'schema_version':1,'numeric_policy':{'rtol':rtol,'atol':atol,'contract_tolerance':contract_tolerance,'keys':'exact text','nonfinite':'paired NaN agrees but may violate validity'},'agree':True,'files':{},'contract_issues':{},'sources':['TABLE_CONTRACT.json']+[f for f in ['ROW_SETS.json','PUBLIC_OUTPUT_NAMING_AND_TYPES.json'] if (public/f).is_file()]}
    required=set(contract['tables'])
    result['uncontracted_tables']={label:sorted(p.name for p in folder.iterdir() if p.suffix in ('.csv','.tsv') and p.name not in required) if folder.is_dir() else [] for label,folder in [('A',a),('B',b)]}
    result['naming_required_files_not_in_contract']=sorted(set(naming.get('delivery',{}).get('required_csv_files',[]))-required)
    for name,original in contract['tables'].items():
        spec=dict(original)
        if 'row_set' not in spec: spec['row_set']=rowsets.get('tables',{}).get(name,{})
        ha,ra,ia=load_table(a/name,spec); hb,rb,ib=load_table(b/name,spec)
        sa,sb=set(ra),set(rb); ka,kb=sorted(sa-sb),sorted(sb-sa)
        changed=collections.Counter(); examples=[]; affected=set()
        for key in sorted(sa&sb):
            for col in spec['columns']:
                if col in spec['key']:continue
                tol=spec.get('tolerance',{}).get(col,[rtol,atol]) if contract_tolerance else [rtol,atol]
                numeric=spec.get('types',{}).get(col) in ('float','int','number','integer')
                if not equal(ra[key].get(col),rb[key].get(col),numeric,*tol):
                    changed[col]+=1;affected.add(key)
                    if len(examples)<n:examples.append({'key':key,'column':col,'A':ra[key].get(col),'B':rb[key].get(col)})
        invalid={}
        try: ek=expected_keys(spec,rowsets)
        except (KeyError,ValueError,TypeError) as e:
            ek=None;invalid['public_key_expansion']=str(e)
        for label,keys,issues in [('A',sa,ia),('B',sb,ib)]:
            if ek is not None and keys!=ek:
                invalid[label]={'missing_key_count':len(ek-keys),'extra_key_count':len(keys-ek),'missing_examples':sorted(ek-keys)[:n],'extra_examples':sorted(keys-ek)[:n]}
            if issues:invalid.setdefault(label,{})['structural_issues']=issues[:n]
        if invalid:result['contract_issues'][name]=invalid
        # Both-identical scientific errors can agree; absent/ambiguous tables cannot.
        same=not(ka or kb or changed or ia or ib) and set(ha)==set(hb)
        if not same:
            result['agree']=False
            result['files'][name]={'keys':spec['key'],'A_rows':len(ra),'B_rows':len(rb),'A_only_columns':sorted(set(ha)-set(hb)),'B_only_columns':sorted(set(hb)-set(ha)),'A_only_key_count':len(ka),'B_only_key_count':len(kb),'A_only_keys':ka[:n],'B_only_keys':kb[:n],'changed_columns':dict(changed),'changed_row_count':len(affected),'cell_examples':examples,'A_issues':ia[:n],'B_issues':ib[:n]}
    if code:
        ca,cb=code_steps(a/'analysis.py'),code_steps(b/'analysis.py')
        result['analysis_steps']={'note':'AST 静态启发式，非语义等价证明；仅列出两边独有的过滤、除法与带常量/关键字参数调用。'}
        for category in ('filters','denominators','method_parameters'):
            aa,bb=ca.get(category,[]),cb.get(category,[])
            result['analysis_steps'][category]={'A_only':[v for v in aa if v not in bb][:n],'B_only':[v for v in bb if v not in aa][:n]}
        result['analysis_steps']['parse_errors']={k:v['error'] for k,v in [('A',ca),('B',cb)] if 'error' in v}
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('public');p.add_argument('candidate_A');p.add_argument('candidate_B');p.add_argument('--examples',type=int,default=5);p.add_argument('--out');p.add_argument('--contract-tolerance',action='store_true')
    a=p.parse_args(); r=compare(a.public,a.candidate_A,a.candidate_B,n=a.examples,contract_tolerance=a.contract_tolerance)
    s=json.dumps(r,ensure_ascii=False,indent=2)+'\n'
    if a.out:Path(a.out).write_text(s,encoding='utf-8')
    else:print(s)
if __name__=='__main__':main()
