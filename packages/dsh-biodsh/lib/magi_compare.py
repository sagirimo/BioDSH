"""BioDSH-MAGI: literal cell differences between the two frozen candidates (same as the v18 evaluation runner).
Usage: magi_compare.py TABLE_CONTRACT.json PRIMARY_DIR BLIND_DIR OUT.json. Not scientific grading."""
import csv, json, sys
from pathlib import Path


def main(contract, left, right, out):
    spec_all = json.loads(Path(contract).read_text(encoding='utf-8-sig'))
    result = {}
    for name, spec in spec_all['tables'].items():
        keys = spec['key']; keys = [keys] if isinstance(keys, str) else keys
        data = []
        for parent in (Path(left), Path(right)):
            p = parent / name
            if not p.exists(): data.append(None); continue
            with p.open(encoding='utf-8-sig', newline='') as f: rows = list(csv.DictReader(f))
            data.append({tuple(r.get(k) for k in keys): r for r in rows})
        if None in data: result[name] = {'missing_in': ['primary', 'blind'][data.index(None)]}; continue
        a, b = data; common = a.keys() & b.keys(); cols = {}
        for col in spec['columns']:
            diff = [k for k in sorted(common, key=str) if a[k].get(col) != b[k].get(col)]
            if diff: cols[col] = {'different_cells': len(diff), 'examples': [{'key': k, 'primary': a[k].get(col), 'blind': b[k].get(col)} for k in diff[:3]]}
        result[name] = {'primary_rows': len(a), 'blind_rows': len(b), 'only_primary_keys': len(a.keys() - b.keys()), 'only_blind_keys': len(b.keys() - a.keys()), 'literal_differences': cols}
    Path(out).write_text(json.dumps({'basis': 'Literal cell comparison only; differences may be formatting or below public tolerance. Not scientific grading.', 'tables': result}, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main(*sys.argv[1:5])
