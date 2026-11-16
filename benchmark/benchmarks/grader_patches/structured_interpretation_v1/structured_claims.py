"""Deterministic structured-interpretation grading shared by task revisions.

Replaces free-text semantic review with explicit scientific claims:
  choice  - one public option; correct option kept in an evaluator-private key
  number  - finite value that must agree with a verified result-table cell
  derived - choice whose correct option is computed from a verified table cell
            (e.g. significance from the submission's own verified p value)
Free narrative is required non-empty but never scored; no LLM review is used.
The public spec lists options only. The private key never leaves the evaluator.
"""
import csv
import json
import math
from pathlib import Path

SCHEMA_VERSION = 2
OPERATORS = {'lt': lambda v, t: v < t, 'le': lambda v, t: v <= t,
             'gt': lambda v, t: v > t, 'ge': lambda v, t: v >= t}


def read_json(path):
    def pairs(items):
        out = {}
        for k, v in items:
            if k in out:
                raise ValueError('Duplicate JSON key')
            out[k] = v
        return out
    return json.loads(Path(path).read_text('utf-8-sig'), object_pairs_hook=pairs,
                      parse_constant=lambda s: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))


def _finite(v):
    return type(v) in (int, float) and math.isfinite(v)


def validate_spec(spec, key):
    """Static consistency of public spec and private key; raises on any defect."""
    ids = [c['id'] for c in spec['claims']]
    if len(ids) != len(set(ids)) or not ids:
        raise ValueError('Claim ids must be unique and non-empty')
    for c in spec['claims']:
        if not isinstance(c.get('question'), str) or not c['question'].strip():
            raise ValueError('Claim question required: ' + c['id'])
        kind = c.get('type')
        if kind in ('choice', 'derived'):
            opts = c.get('options')
            if not isinstance(opts, list) or len(opts) < 2 or len(set(opts)) != len(opts):
                raise ValueError('At least two distinct options required: ' + c['id'])
        if kind == 'choice':
            if key['choices'].get(c['id']) not in c['options']:
                raise ValueError('Private key missing or not an option: ' + c['id'])
        elif kind == 'number':
            b = c.get('binding', {})
            if not all(isinstance(b.get(k), str) for k in ('table', 'column')):
                raise ValueError('Numeric binding incomplete: ' + c['id'])
            if not (_finite(c.get('rel_tol')) and _finite(c.get('abs_tol'))):
                raise ValueError('Numeric tolerances required: ' + c['id'])
        elif kind == 'derived':
            rule = c.get('rule', {})
            if rule.get('op') not in OPERATORS or not _finite(rule.get('threshold')):
                raise ValueError('Derived rule invalid: ' + c['id'])
            if set(rule.get('outcomes', {})) != {'true', 'false'} or not set(rule['outcomes'].values()) <= set(c['options']):
                raise ValueError('Derived outcomes must map to options: ' + c['id'])
        else:
            raise ValueError('Unknown claim type: ' + str(kind))
        if kind != 'choice' and c['id'] in key['choices']:
            raise ValueError('Private key must not shadow table-bound claim: ' + c['id'])
    if set(key['choices']) - set(ids):
        raise ValueError('Private key has unknown claims')
    return ids


def table_cell(out, binding):
    with (Path(out) / binding['table']).open(encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))
    if 'key_column' in binding:
        rows = [r for r in rows if r.get(binding['key_column']) == binding['key']]
    for col, val in binding.get('keys', {}).items():
        rows = [r for r in rows if r.get(col) == val]
    if len(rows) != 1:
        raise ValueError('Bound table row is not unique: ' + binding['table'])
    value = float(rows[0][binding['column']])
    if not math.isfinite(value):
        raise ValueError('Bound table value is not finite')
    return value


def grade(out, spec, key, filename='interpretation.json'):
    """Return per-claim results; all claims must hold for semantic_verified."""
    ids = validate_spec(spec, key)
    obj = read_json(Path(out) / filename)
    if not isinstance(obj, dict) or set(obj) != {'schema_version', 'claims', 'narrative'}:
        raise ValueError(filename + ' must contain exactly schema_version, claims, narrative')
    if type(obj['schema_version']) is not int or obj['schema_version'] != SCHEMA_VERSION:
        raise ValueError('Unknown interpretation schema')
    if not isinstance(obj['narrative'], str) or not obj['narrative'].strip():
        raise ValueError('Narrative must be non-empty (it is not scored)')
    claims = obj['claims']
    if not isinstance(claims, dict) or set(claims) != set(ids):
        raise ValueError('Claims must cover exactly the published claim ids')
    results = {}
    for c in spec['claims']:
        given = claims[c['id']]
        if c['type'] == 'choice':
            ok = isinstance(given, str) and given == key['choices'][c['id']]
            if isinstance(given, str) and given not in c['options']:
                raise ValueError('Not a published option: ' + c['id'])
        elif c['type'] == 'number':
            if not _finite(given):
                raise ValueError('Numeric claim must be finite: ' + c['id'])
            ok = math.isclose(given, table_cell(out, c['binding']), rel_tol=c['rel_tol'], abs_tol=c['abs_tol'])
        else:
            if not isinstance(given, str) or given not in c['options']:
                raise ValueError('Not a published option: ' + c['id'])
            rule = c['rule']
            truth = OPERATORS[rule['op']](table_cell(out, rule['binding']), rule['threshold'])
            ok = given == rule['outcomes']['true' if truth else 'false']
        results[c['id']] = 'pass' if ok else 'fail'
    return dict(semantic_verified=all(v == 'pass' for v in results.values()),
                claim_results=results, scored_claims=len(results), narrative_scored=False,
                method='structured_claims_v1_deterministic', llm_review=False)


def public_prompt_section(spec, filename='interpretation.json'):
    """Render the public claim list appended to a task prompt (no answers)."""
    lines = ['', f'结构化解释（{filename}，schema_version=2）：',
             '提交对象恰含 schema_version、claims、narrative 三个字段。claims 以下列 id 为键，'
             '选项题填所给选项字符串之一，数值题填有限数字。每个声明独立确定性判分，全部正确才算解释通过；'
             'narrative 为非空自由说明，不计分。数值声明须与你自己已验证的结果表一致。']
    for c in spec['claims']:
        if c['type'] == 'number':
            b = c['binding']
            sel = ([b['key_column'] + '=' + b['key']] if 'key_column' in b else []) + [k + '=' + v for k, v in b.get('keys', {}).items()]
            where = b['table'] + ('[' + ','.join(sel) + ']' if sel else '') + '.' + b['column']
            lines.append(f"- {c['id']}（数值，须与 {where} 一致）：{c['question']}")
        else:
            lines.append(f"- {c['id']}（选项：{' | '.join(c['options'])}）：{c['question']}")
    return '\n'.join(lines) + '\n'
