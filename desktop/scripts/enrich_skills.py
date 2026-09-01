#!/usr/bin/env python3
"""用 DeepSeek API 给社区技能批量生成：中文标题、白话一句话简介、两级分类、中文标签。
输入 store/community-index.json，输出 store/community-zh.json（可断点续跑，缓存在 store/cache/enrich/）。
API key 读取顺序：环境变量 DEEPSEEK_API_KEY → ~/.dsh/.credentials.yaml。
"""
from __future__ import annotations
import json, os, re, sys, time, hashlib, concurrent.futures as cf, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
INDEX = HERE.parent / 'store' / 'community-index.json'
OUT = HERE.parent / 'store' / 'community-zh.json'
CACHE = HERE.parent / 'store' / 'cache' / 'enrich'
CACHE.mkdir(parents=True, exist_ok=True)
BATCH = 12
WORKERS = 6
MODEL = os.environ.get('DEEPSEEK_MODEL', 'deepseek-chat')

TAXONOMY = {
    '单细胞与空间': ['单细胞预处理与质控', '聚类与降维', '细胞类型注释', '轨迹与动态', '细胞通讯', '单细胞多组学', '空间转录组'],
    '转录组与表达': ['RNA-seq 上游处理', '差异表达', '可变剪接与异构体', '共表达与网络', '非编码 RNA'],
    '基因组与变异': ['测序质控与比对', '变异检测与注释', '结构变异与拷贝数', '基因组组装与注释', 'GWAS 与群体遗传', '基因编辑与 CRISPR', '比较与进化基因组'],
    '表观与调控': ['ATAC / 染色质可及性', 'ChIP-seq 与组蛋白', 'DNA 甲基化', '三维基因组', '基因调控网络与转录因子'],
    '蛋白与结构': ['蛋白质组与质谱', '结构预测与建模', '蛋白设计', '分子对接与动力学', '蛋白互作'],
    '药物与化学': ['化合物与分子性质', '药物发现与筛选', '药物基因组与药效', '临床试验'],
    '临床与医学': ['肿瘤与癌症基因组', '临床数据与电子病历', '生存与预后分析', '疾病与表型', '流行病学与公共卫生'],
    '微生物与免疫': ['宏基因组与微生物组', '病原与病毒', '免疫组库 TCR/BCR', '免疫与抗原表位'],
    '代谢与其他组学': ['代谢组与脂质组', '多组学整合', '影像与显微', '流式细胞'],
    '数据与工具': ['公共数据库查询', '文献检索与阅读', '数据格式与转换', '可视化与作图', '统计与机器学习', '流程与环境', '写作与报告', '实验设计与湿实验'],
}

def api_key() -> str:
    k = os.environ.get('DEEPSEEK_API_KEY')
    if k: return k
    f = Path(os.environ.get('DSH_HOME', Path.home() / '.dsh')) / '.credentials.yaml'
    m = re.search(r'^DEEPSEEK_API_KEY:\s*["\']?([^"\'\s]+)', f.read_text(), re.M) if f.exists() else None
    if not m: sys.exit('no DEEPSEEK_API_KEY')
    return m.group(1)

KEY = api_key()

def chat(messages: list[dict], retries: int = 5) -> str:
    body = json.dumps({'model': MODEL, 'messages': messages, 'temperature': 0.2, 'response_format': {'type': 'json_object'}}).encode()
    for i in range(retries):
        try:
            req = urllib.request.Request('https://api.deepseek.com/chat/completions', data=body, headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {KEY}'})
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.loads(r.read())['choices'][0]['message']['content']
        except Exception as e:
            wait = 2 ** i
            print(f'  retry {i+1}: {e} (sleep {wait}s)', file=sys.stderr); time.sleep(wait)
    raise RuntimeError('api failed')

SYSTEM = f"""你是生物信息学产品经理，为一个面向医生和湿实验科学家的"生信技能商店"整理条目。用户不懂生信术语，你要用最通俗的中文。
对输入的每个技能，输出：
- title_zh：中文标题，8-16 字，说清"做什么"，不要写工具名的音译；工具名可保留英文（如 "DESeq2 差异表达分析"）
- summary_zh：一句白话简介，30-60 字，说明"什么时候用它、能得到什么"，避免术语堆砌
- domain：只能从这个列表选一个：{json.dumps(list(TAXONOMY), ensure_ascii=False)}
- subcategory：必须是该 domain 下的一个：{json.dumps(TAXONOMY, ensure_ascii=False)}
- tags_zh：2-4 个中文短标签
- level：入门 / 进阶 / 专家（按使用门槛）
只输出 JSON 对象：{{"items": [{{"id": ..., "title_zh": ..., "summary_zh": ..., "domain": ..., "subcategory": ..., "tags_zh": [...], "level": ...}}]}}，顺序与输入一致，id 原样返回。"""

def enrich_batch(items: list[dict]) -> list[dict]:
    key = hashlib.sha1(json.dumps([i['id'] for i in items]).encode()).hexdigest()[:16]
    cf_ = CACHE / f'{key}.json'
    if cf_.exists():
        return json.loads(cf_.read_text(encoding='utf-8'))
    payload = [{'id': i['id'], 'name': i['name'], 'description': i['description'][:400], 'source': i['origin']['repo'], 'hint_category': i['category']} for i in items]
    txt = chat([{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}])
    out = json.loads(txt).get('items', [])
    good = []
    by_id = {o.get('id'): o for o in out if isinstance(o, dict)}
    for i in items:
        o = by_id.get(i['id'])
        if not o: continue
        if o.get('domain') not in TAXONOMY: o['domain'] = '数据与工具'
        if o.get('subcategory') not in TAXONOMY[o['domain']]: o['subcategory'] = TAXONOMY[o['domain']][0]
        good.append(o)
    cf_.write_text(json.dumps(good, ensure_ascii=False), encoding='utf-8')
    return good

def main():
    skills = json.loads(INDEX.read_text(encoding='utf-8'))['skills']
    batches = [skills[i:i + BATCH] for i in range(0, len(skills), BATCH)]
    print(f'{len(skills)} skills, {len(batches)} batches, model {MODEL}')
    results, done = {}, 0
    with cf.ThreadPoolExecutor(WORKERS) as ex:
        for res in ex.map(lambda b: (b, enrich_batch(b)), batches):
            b, out = res
            for o in out: results[o['id']] = o
            done += 1
            if done % 10 == 0: print(f'  {done}/{len(batches)} batches, {len(results)} enriched', flush=True)
    OUT.write_text(json.dumps({'meta': {'model': MODEL, 'count': len(results), 'taxonomy': TAXONOMY}, 'items': results}, ensure_ascii=False, indent=1), encoding='utf-8')
    from collections import Counter
    print('written', len(results)); print(Counter(v['domain'] for v in results.values()).most_common())

if __name__ == '__main__':
    main()
