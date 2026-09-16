#!/usr/bin/env python3
"""Build desktop/site/{index.html,en/index.html,ds.css} from the DeepSeek Harness template
(tmp/dsref/body-{zh,en}.html + ds.css). Only text, links, logo and images change.

    python3 desktop/site/build_from_dsref.py
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REF = os.path.normpath(os.path.join(HERE, '..', '..', 'tmp', 'dsref'))

REPO = 'https://github.com/sagirimo/BioDSH'
README = REPO + '#readme'
EXE = 'BioDSH_0.2.0_x64-setup.exe'
DMG = 'BioDSH_0.2.0_aarch64.dmg'
DL = REPO + '/releases/latest/download/'

MARK_PATH = '<path d="M14 12c0 10 16 10 16 20M30 12c0 10-16 10-16 20" stroke="#fff" stroke-width="4" stroke-linecap="round" fill="none"/>'
MARK_SVG = ''  # 换成用户提供的字标图
FAVICON = 'img/favicon-256.png'
LOGO = ('<span class="bio-logo inline-flex items-center"><img src="img/logo-wordmark.png" alt="BioDSH" class="bio-wordmark-img" height="26"/></span>')

ICON_DOWNLOAD = ('<svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden="true">'
                 '<path d="M8 2.25V10.25M4.9 7.3L8 10.4L11.1 7.3" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"></path>'
                 '<path d="M2.75 11.5V13.25H13.25V11.5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"></path></svg>')

GOOGLE_FONTS = ('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700'
                '&family=Fragment+Mono&family=Host+Grotesk:ital,wght@0,300..800;1,300..800'
                '&family=Montserrat:wght@400;500;600&family=Noto+Sans+SC:wght@400;500'
                '&family=Silkscreen&display=swap')

# ----------------------------------------------------------------------------- content
T = {
    'zh': dict(
        html_lang='zh-CN',
        title='BioDSH — DeepSeek Harness 生信插件生态',
        description='BioDSH：全网首个面向生信的 DeepSeek Harness 插件生态。给医生和湿实验科学家的生信智能体桌面版——放数据、说需求、看结论；2,183 个技能插件，本地运行，可纯离线。',
        nav=[('GitHub', REPO), ('用户手册', README), ('技能商店', '#plugins'), ('下载', '#download')],
        hero_label='BioDSH 技术预览版 · 全网首个面向生信的 DeepSeek Harness 插件生态',
        h1='一切皆插件，分析只需一句话',
        hero_p1='BioDSH 是给医生和湿实验科学家的生信智能体桌面版：基于 DeepSeek Harness，把单细胞、转录组、临床统计、公共数据库、文献、Zotero、Excel——甚至你的鼠标键盘——全部做成 DeepSeek 智能体的插件。',
        hero_p2='不用会编程：放数据、说需求、看结论。本地运行，原始数据永不改动，医院内网可纯离线。',
        hero_btns=[('下载 Windows 版', REPO + '/releases/latest'), ('下载 macOS 版', REPO + '/releases/latest'), ('技能商店 · 2,183 个插件', '#plugins'), ('GitHub', REPO)],
        tabs=('Windows', 'macOS'),
        copied='已复制',
        pill='AGENT = DEEPSEEK + HARNESS + BIODSH',
        harness_word='BioDSH',
        harness_line='让生信分析在真实的实验室里跑起来',
        soul='模型是智能体的灵魂。',
        soul2='Harness 给它手脚，BioDSH 给它生信的本事：技能、数据库、文献、电脑操作。',
        cards=[('DeepSeek Harness 内核', 'DSH CORE', '内核只负责插件加载与只追加的会话日志，BioDSH 不改一行内核代码。'),
               ('生信能力皆插件', 'CAPABILITIES AS PLUGINS', '单细胞、文献、数据库、Zotero、Excel、电脑控制——2,183 个技能插件即装即用，官方技能开箱即装。'),
               ('开箱即用', 'READY OUT OF THE BOX', '自带 Python 分析环境、9 个评测过的官方技能和 4 个真实示范项目，不用会编程。')],
        design_tag='产品思路',
        design_h2='一切皆插件，每一步可复现',
        features=[('一切皆插件', 'BioDSH 站在 DeepSeek Harness 的插件系统之上：开源社区里最好的 2,174 个生信技能已收编、翻译、按 10 个领域 × 40 个小类整理，加上 9 个离线可复现的官方技能。想要的能力，在商店里点一下就装上。'),
                  ('每一次分析都有迹可循', '模型看到的一切都写进只追加的会话日志：系统提示、思考、工具调用与结果。对话里中间过程折成一行「BioDSH 完成了 N 步」，点开逐级展开；对话可导出给导师和审稿人，项目一键版本快照。'),
                  ('四个真实示范项目', '装好就在项目列表里，每个都是真实跑出来的对话：单细胞分析与作图、文献调研、公共数据库抓取、电脑控制与 Zotero。照着问就行。')],
        img_alt=['BioDSH 技能商店：官方技能与 2,174 个社区技能按领域分类', 'BioDSH 对话：中间步骤折叠成一行，可逐级展开'],
        mock_project='BioDSH',
        mock_mode='电脑控制与 Zotero',
        mock_placeholder='描述你想要分析的内容',
        mock_aria='新对话界面展开示范项目选择器，列出单细胞分析与作图、文献调研、公共数据库抓取、电脑控制与 Zotero 四个项目',
        modes=[('单细胞分析与作图', 'PBMC 3k 原始计数 → 质控 → 聚类 → 注释 → UMAP，再复核 CD8 T 和 NK 有没有分错。'),
               ('文献调研', 'PubMed / Europe PMC 接口检索，整理成带 DOI 的表和综述提纲，挑出最值得精读的。'),
               ('公共数据库抓取', 'NCBI / UniProt 注释表、Hallmark 富集、GTEx 表达热图，本地参考包可离线。'),
               ('电脑控制与 Zotero', '按 DOI 把文献加进 Zotero，打开 Excel 贴表保存——屏幕上有「BioDSH 正在控制电脑」提示。')],
        custom_h2='定制你的 BioDSH',
        custom=[('纯离线模式', 'OFFLINE MODE', '医院内网接本地/内网模型或课题组 Linux 服务器。'),
                ('MCP 接入', 'MCP SERVERS', '把 Zotero、PubMed、课题组自建服务接给智能体。'),
                ('一键迁移', 'MIGRATE SKILLS', '从 Claude Code / Codex / OpenCode / Cursor 迁入已有技能。')],
        start_tag='开始使用',
        start_h2='三分钟上手',
        start=[('下载安装', '双击安装包，不需要管理员权限，之后自动更新。', EXE),
               ('填 Key、装环境', '在 DeepSeek 开放平台申请一个 Key 粘贴进去；软件自带 Python 工具链，一键装好分析包。', '更多 → 模型 API Key → 分析环境 → 一键安装')],
        join_h2='加入 BioDSH 插件生态',
        join_p='BioDSH 仍是技术预览版，官方技能和桌面端会持续迭代。我们期待与医生、湿实验科学家和生信开发者一起，在 DeepSeek Harness 开放、可复用、可组合的基础设施之上，把生信分析做成人人可用的插件。',
        join_btns=[('GitHub', REPO), ('下载', '#download'), ('技能商店', '#plugins')],
        footer='开源 · 技术预览 · © 2026 BioDSH · 北京大学',
        footer_nav=[('用户手册', README), ('GitHub', REPO)],
        footer_aria='站点链接',
        menu_aria=('打开菜单', '关闭菜单'),
    ),
    'en': dict(
        html_lang='en',
        title='BioDSH — the bioinformatics plugin ecosystem for DeepSeek Harness',
        description='BioDSH: the first bioinformatics plugin ecosystem for DeepSeek Harness. A bioinformatics agent desktop for clinicians and wet-lab scientists — drop in data, say what you need, read the conclusion. 2,183 skill plugins, runs locally, fully offline optional.',
        nav=[('GitHub', REPO), ('User guide', README), ('Skill store', '#plugins'), ('Download', '#download')],
        hero_label='BioDSH tech preview · the first bioinformatics plugin ecosystem for DeepSeek Harness',
        h1='Everything is a plugin. Every analysis is a sentence.',
        hero_p1='BioDSH is the bioinformatics agent desktop for clinicians and wet-lab scientists: built on DeepSeek Harness, it turns single-cell, bulk RNA-seq, clinical statistics, public databases, literature, Zotero, Excel — even your mouse and keyboard — into plugins of a DeepSeek agent.',
        hero_p2='No coding: drop in data, say what you need, read the conclusion. Runs locally, never modifies your originals, fully offline inside hospital intranets.',
        hero_btns=[('Download for Windows', REPO + '/releases/latest'), ('Download for macOS', REPO + '/releases/latest'), ('Skill store · 2,183 plugins', '#plugins'), ('GitHub', REPO)],
        tabs=('Windows', 'macOS'),
        copied='Copied',
        pill='AGENT = DEEPSEEK + HARNESS + BIODSH',
        harness_word='BioDSH',
        harness_line='keeps bioinformatics running in real labs',
        soul='The model is the soul of an agent.',
        soul2='Harness gives it hands; BioDSH gives it bioinformatics: skills, databases, literature, desktop control.',
        cards=[('DeepSeek Harness core', 'DSH CORE', 'The core only loads plugins and keeps an append-only session log. BioDSH does not change a single line of it.'),
               ('Bio capabilities as plugins', 'CAPABILITIES AS PLUGINS', 'Single-cell, literature, databases, Zotero, Excel, desktop control — 2,183 skill plugins install in one click, official skills included out of the box.'),
               ('Ready out of the box', 'READY OUT OF THE BOX', 'Ships with a Python analysis environment, 9 evaluated official skills and 4 real example projects. No coding required.')],
        design_tag='Product approach',
        design_h2='Everything is a plugin.\nEvery step is reproducible.',
        features=[('Everything is a plugin', 'BioDSH stands on the DeepSeek Harness plugin system: the best 2,174 open-source bio skills have been collected, translated and organised into 10 domains × 40 topics, plus 9 offline-reproducible official skills. Whatever you need, one click in the store installs it.'),
                  ('Every analysis is traceable', 'Everything the model sees goes into an append-only session log: system prompts, reasoning, tool calls and results. In the chat, the intermediate steps fold into one line — “BioDSH finished N steps” — and expand level by level. Conversations export for your advisor or reviewers; projects snapshot in one click.'),
                  ('Four real example projects', 'They are in your project list the moment you install, each a real recorded conversation: single-cell analysis and plotting, literature review, public database retrieval, desktop control with Zotero. Just ask the same way.')],
        img_alt=['BioDSH skill store: official skills and 2,174 community skills organised by domain', 'BioDSH chat: intermediate steps folded into one line, expandable level by level'],
        mock_project='BioDSH',
        mock_mode='Desktop control & Zotero',
        mock_placeholder='Describe what you want to analyze',
        mock_aria='The new-chat example-project picker listing single-cell analysis, literature review, public database retrieval and desktop control with Zotero',
        modes=[('Single-cell analysis & plots', 'PBMC 3k raw counts → QC → clustering → annotation → UMAP, then double-check whether CD8 T and NK cells were confused.'),
               ('Literature review', 'Search the PubMed / Europe PMC APIs, build a DOI-annotated table and a review outline, and pick what deserves a close read.'),
               ('Public database retrieval', 'NCBI / UniProt annotation tables, Hallmark enrichment, GTEx expression heatmaps; local reference packs work offline.'),
               ('Desktop control & Zotero', 'Add papers to Zotero by DOI, open Excel, paste a table and save — with a “BioDSH is controlling the computer” banner on screen.')],
        custom_h2='Customize your BioDSH',
        custom=[('Fully offline', 'OFFLINE MODE', 'Inside a hospital intranet, connect a local or intranet model, or your lab’s Linux server.'),
                ('MCP integration', 'MCP SERVERS', 'Plug Zotero, PubMed and your lab’s own services into the agent.'),
                ('One-click migration', 'MIGRATE SKILLS', 'Bring existing skills over from Claude Code, Codex, OpenCode or Cursor.')],
        start_tag='Get started',
        start_h2='Up and running in three minutes',
        start=[('Download and install', 'Double-click the installer — no admin rights needed, it updates itself afterwards.', EXE),
               ('Add a key, install the environment', 'Get an API key from the DeepSeek open platform and paste it in; the app ships its own Python toolchain and installs the analysis packages in one click.', 'More → Model API key → Analysis environment → Install')],
        join_h2='Join the BioDSH plugin ecosystem',
        join_p='BioDSH is still a technical preview; the official skills and the desktop app will keep evolving. We look forward to working with clinicians, wet-lab scientists and bioinformatics developers to turn bioinformatics analysis into plugins anyone can use, on top of DeepSeek Harness’s open, reusable, composable infrastructure.',
        join_btns=[('GitHub', REPO), ('Download', '#download'), ('Skill store', '#plugins')],
        footer='Open source · Tech preview · © 2026 BioDSH · Peking University',
        footer_nav=[('User guide', README), ('GitHub', REPO)],
        footer_aria='Site links',
        menu_aria=('Open menu', 'Close menu'),
    ),
}

# Original strings that differ per language (used as anchors for replacement).
ORIG = {
    'zh': dict(
        nav=['GitHub', '开发者文档', '社区插件', 'Cordis 论文'],
        hero_label='DeepSeek Harness 开发者预览版', h1='一切皆插件',
        hero_p1='DeepSeek Harness 开发者预览版面向全球 Harness 开发者开放测试，并同步开放源代码。',
        hero_p2='模型、工具、技能、会话、沙箱、存储、循环、调度、UI 等所有 Agent 能力均由插件组合而成，可以自由替换和灵活重组。',
        tabs=('一键使用', '源码安装'), pill='Agent = Model + Harness',
        harness_line='让 Agent 在真实场景中持续工作', soul='模型是 Agent 的灵魂。',
        soul2='Harness 给予 Agent 理解环境、使用工具，并在真实场景中持续工作的能力。',
        card_titles=['Cordis 内核', '插件提供能力', '配置层自由组合'],
        card_labels=['CORDIS KERNEL', 'CAPABILITIES AS PLUGINS', 'COMPOSE IN CONFIGURATION'],
        card_texts=['Cordis 内核只负责插件的加载、卸载和依赖关系，不承载 Agent 的具体能力。',
                    '模型、工具、技能、会话、沙箱、存储、循环、调度、UI 等所有 Agent 能力均由插件提供，并通过 Cordis 服务与事件彼此协作。',
                    '开发者无需改动源码，即可在配置层选择、替换或扩展任一能力。'],
        design_tag='设计思路', design_h2='一切皆插件，运行有迹可循',
        feat_titles=['一切皆插件', '每一次运行都有迹可循', '多种运行模式'],
        feat_texts=[None,
                    '模型看到的一切都会写入仅追加设计的会话日志，包括系统提示词、思维链、工具调用与结果、子 Agent 调度，以及每一次上下文注入。在 Trajectory 视图中，你可以按来源查看这些信息。恢复、分叉、检索与回放也共享同一份事件流。',
                    '标准模式提供完整的工具组合；PTC 模式通过模型生成的一段代码组合多轮工具调用；极简模式仅保留一个 shell 工具与一个文件编辑工具，用于最小化环境下的模型基准测试；创造模式可以检查当前运行时、在内存中试验 Cordis 插件，并据此组合和创作新的模式。'],
        img_alt=['DeepSeek Harness 设置页展示已安装插件及启用状态', '从同一份会话日志还原完整运行过程'],
        mock_mode='创造模式', mock_placeholder='描述你想要构建的内容',
        mock_aria='新会话界面展开模式选择器，列出标准、PTC、极简与创造四种模式',
        modes=[('标准模式', '功能完整的编码 Agent，支持文件编辑、Shell、文件与网页检索、Skills、计划、目标、子代理和工作流。'),
               ('PTC 模式', '具备标准模式的全部能力，并通过 Code Mode SDK 呈现工具，让模型用一个 TypeScript 程序组合多步操作。'),
               ('极简模式', '仅提供持久 bash 与 str_replace_editor 的双工具编码 Agent。'),
               ('创造模式', '用于创建自定义 Agent preset：具备标准模式的全部能力，并提供运行时检查、插件实验和 preset 创作指导。')],
        custom_h2='自定义你的 DeepSeek Harness',
        start_tag='开始使用', start_h2='快速体验或从源码安装',
        start=[('快速体验', '安装 Node.js 后，可通过 npx 启动 Web UI。'), ('源码安装', '获取完整项目源码，并按照仓库说明完成安装。')],
        join_h2='加入 DSH 插件生态',
        join_p='DeepSeek Harness 开发者预览版仍处于面向 Harness 开发者的测试阶段，核心插件和基础 API 将持续迭代。我们期待与全球开发者一起，在开源、开放、可复用、可组合的基础设施之上，共同探索智能上限。',
        footer='开源 · MIT<!-- --> · <!-- -->© 2026 杭州深度求索人工智能基础技术研究有限公司 版权所有',
        footer_aria='政策与说明',
    ),
    'en': dict(
        nav=['GitHub', 'Developer docs', 'Community plugins', 'Cordis paper'],
        hero_label='DeepSeek Harness developer preview', h1='Everything is a plugin',
        hero_p1='DeepSeek Harness is now in developer preview for agent harness developers worldwide — source code included.',
        hero_p2='Every capability is a plugin that can be swapped or recomposed: models, tools, skills, sessions, sandboxes, storage, loops, scheduling, and the UI.',
        tabs=('Quick start', 'Install from source'), pill='Agent = Model + Harness',
        harness_line='keeps agents working in real-world environments', soul='The model is the soul of an agent.',
        soul2='A harness lets an agent understand its environment, use tools, and keep working in real-world settings.',
        card_titles=['Cordis kernel', 'Capabilities as plugins', 'Compose with configuration'],
        card_labels=[],
        card_texts=['The Cordis kernel manages plugin mounting, unmounting, and dependencies. Agent capabilities live in the plugins.',
                    'Plugins provide every agent capability, including models, tools, skills, sessions, sandboxes, storage, loops, scheduling, and the UI. Cordis services and events let the plugins work together.',
                    'Developers can select, swap, or extend any capability in configuration without changing the DeepSeek Harness source code.'],
        design_tag='Design approach', design_h2='Everything is a plugin.\nEvery run is traceable.',
        feat_titles=['Everything is a plugin', 'Every run is traceable', 'Multiple runtime modes'],
        feat_texts=[None,
                    'Everything the model sees is recorded in an append-only session log: system prompts, reasoning, tool calls and results, subagent scheduling, and every context injection. In the Trajectory view, you can inspect these records by source. Resume, fork, search, and replay all operate on the same event stream.',
                    'Standard mode includes the full toolset. Code mode uses model-generated code to orchestrate multiple rounds of tool calls. Minimal mode keeps only a shell tool and a file editor for benchmarking models in a minimal environment. Creator mode lets you inspect the current runtime, test Cordis plugins in memory, and combine them into new modes.'],
        img_alt=['DeepSeek Harness settings showing installed plugins and their status', 'Reconstruct a complete run from a single session log'],
        mock_mode='Creator mode', mock_placeholder='Describe what you want to build',
        mock_aria='The new-session mode picker listing Standard, Code, Minimal, and Creator modes',
        modes=[('Standard mode', 'Full coding agent with file editing, shell, file and web search, skills, planning, goals, subagents, and workflows.'),
               ('Code mode', 'All Standard mode capabilities, with tools exposed through the Code Mode SDK so the model can combine multi-step operations in one TypeScript program.'),
               ('Minimal mode', 'Two-tool coding agent with persistent bash and str_replace_editor.'),
               ('Creator mode', 'Built for creating custom agent presets, with all Standard mode capabilities plus runtime inspection, plugin experiments, and preset-authoring guidance.')],
        custom_h2='Customize your DeepSeek Harness',
        start_tag='Get started', start_h2='Try it now or install from source',
        start=[('Quick start', 'Install Node.js, then launch the Web UI with npx.'), ('Install from source', 'Clone the full source and follow the setup instructions in the repository.')],
        join_h2='Join the DSH plugin ecosystem',
        join_p='DeepSeek Harness remains in developer preview and is still being tested by developers building agent harnesses. Its core plugins and APIs will continue to evolve. We look forward to exploring the limits of intelligence with developers worldwide using open-source infrastructure that is reusable and composable.',
        footer='Open source · MIT<!-- --> · <!-- -->© 2026 DeepSeek. All rights reserved.',
        footer_aria='Policies and statements',
    ),
}


# ----------------------------------------------------------------------------- helpers
class BuildError(Exception):
    pass


def sub(s, pattern, repl, count=1, flags=re.S, exact=True):
    """Regex substitute that fails loudly when the pattern is missing."""
    n = len(re.findall(pattern, s, flags))
    if n == 0 or (exact and count and n != count):
        raise BuildError('pattern matched %d times (expected %s): %s' % (n, count or 'any', pattern[:120]))
    return re.sub(pattern, repl, s, count=count or 0, flags=flags)


def text(s, old, new, count=None):
    """Replace a text node ('>old<') everywhere (mobile + desktop variants)."""
    key = '>' + old + '<'
    n = s.count(key)
    if n == 0 or (count and n != count):
        raise BuildError('text node found %d times (expected %s): %s' % (n, count or 'any', old[:80]))
    return s.replace(key, '>' + new + '<')


def esc(s):
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')


def rx(s):
    return re.escape(s)


def card(icon, title, label, body):
    return ('<div class="rounded-[12px] h-full" style="position:relative">'
            '<div class="bg-ds-surface-3 border border-ds-border-default rounded-ds-media p-ds-6 flex flex-col items-center text-center h-full">'
            '<div class="text-ds-primary opacity-70 mb-ds-4">%s</div>'
            '<h3 class="ds-text-title text-ds-primary mb-ds-2">%s</h3>'
            '<span class="font-mono text-[11px] text-ds-description tracking-wider block mb-ds-3">%s</span>'
            '<p class="ds-text-caption text-ds-description leading-[1.65]">%s</p></div></div>') % (icon, esc(title), esc(label), esc(body))


# --- four example-project cards for the "Four real example projects" panel ---
_PROJ_ICONS = [
    '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="7" cy="8" r="2.2" stroke="currentColor" stroke-width="1.4"/><circle cx="15.5" cy="6" r="1.5" stroke="currentColor" stroke-width="1.4"/><circle cx="17" cy="14.5" r="2.4" stroke="currentColor" stroke-width="1.4"/><circle cx="9" cy="16" r="1.7" stroke="currentColor" stroke-width="1.4"/></svg>',
    '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M12 6.5C10.5 5.2 8.2 4.8 5 5v13c3.2-.2 5.5.2 7 1.5 1.5-1.3 3.8-1.7 7-1.5V5c-3.2-.2-5.5.2-7 1.5Z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/><path d="M12 6.5v13" stroke="currentColor" stroke-width="1.4"/></svg>',
    '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true"><ellipse cx="12" cy="6" rx="7" ry="2.6" stroke="currentColor" stroke-width="1.4"/><path d="M5 6v12c0 1.44 3.13 2.6 7 2.6s7-1.16 7-2.6V6" stroke="currentColor" stroke-width="1.4"/><path d="M5 12c0 1.44 3.13 2.6 7 2.6s7-1.16 7-2.6" stroke="currentColor" stroke-width="1.4"/></svg>',
    '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M5.5 4l5.5 14 2.1-5.7 5.7-2.1L5.5 4Z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/><path d="M13.5 13.5 18 18" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>',
]

def _proj_card(icon, name, desc):
    return ('<div class="bg-ds-surface-3 border border-ds-border-default rounded-ds-media flex flex-col gap-ds-2" style="padding:16px">'
            '<div class="text-ds-primary" style="opacity:.8">%s</div>'
            '<h4 class="ds-text-subtitle text-ds-primary" style="line-height:1.25">%s</h4>'
            '<p class="ds-text-caption text-ds-description" style="line-height:1.55">%s</p></div>') % (icon, esc(name), esc(desc))

def replace_mock(s, projects, aria):
    """Swap the dsh-style project-picker mock (a possibly-nested role="img" div) for a real 2x2 project grid."""
    cards = ''.join(_proj_card(_PROJ_ICONS[i], projects[i][0], projects[i][1]) for i in range(4))
    grid = ('<div role="img" aria-label="%s" style="container-type:inline-size">'
            '<div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px">%s</div></div>') % (esc(aria), cards)
    key = '<div role="img"'; out = []; i = 0; n = 0
    while True:
        j = s.find(key, i)
        if j < 0:
            out.append(s[i:]); break
        out.append(s[i:j])
        k = s.find('>', j) + 1; depth = 1; q = k
        while depth > 0:
            nd = s.find('<div', q); nc = s.find('</div>', q)
            if nc < 0:
                raise BuildError('unbalanced mock div')
            if nd != -1 and nd < nc:
                depth += 1; q = nd + 4
            else:
                depth -= 1; q = nc + 6
        out.append(grid); i = q; n += 1
    return ''.join(out), n


# ----------------------------------------------------------------------------- build one page
def build(lang):
    t, o = T[lang], ORIG[lang]
    src = open(os.path.join(REF, 'body-%s.html' % lang), encoding='utf-8').read()
    s = src
    if s.startswith('<body>'):
        s = s[len('<body>'):]
    s = re.sub(r'</body>\s*(</html>)?\s*$', '', s)

    svgs = re.findall(r'<svg\b.*?</svg>', s, re.S)
    ICON_GITHUB, ICON_CUBE = svgs[4], svgs[6]
    ICON_FEAT = [svgs[16], svgs[17], svgs[18]]

    root = (lang == 'en')            # English lives at site root, Chinese at /zh/
    home = './'
    img = 'img/' if root else '../img/'
    active_zh = ' is-active' if lang == 'zh' else ''
    active_en = ' is-active' if lang == 'en' else ''
    href_zh = 'zh/' if root else './'
    href_en = './' if root else '../'
    logo = ('<span class="bio-logo inline-flex items-center">'
            '<img src="%slogo-wordmark.png" alt="BioDSH" class="bio-wordmark-img bio-wm-normal" height="26"/>'
            '<img src="%slogo-wordmark-white.png" alt="" aria-hidden="true" class="bio-wordmark-img bio-wm-white" height="26"/></span>') % (img, img)

    # --- header: logo + pill + locale toggle + menu buttons
    s = sub(s, r'<a class="flex items-center gap-\[8px\] min-w-0 text-\[var\(--ds-color-brand-medium-reverse\)\]" href="/harness/(?:en/)?">\s*<span class="shrink-0 inline-flex"><svg width="143".*?</svg></span>',
            '<a class="flex items-center gap-[8px] min-w-0 text-[var(--ds-color-brand-medium-reverse)]" href="%s">%s' % (home, logo))
    s = sub(s, r'>Harness</span></span></span></span></a>', '>for DeepSeek Harness</span></span></span></span></a>')
    toggle = ('<div class="ds-locale-toggle">'
              '<a class="ds-locale-toggle-item%s" href="%s" data-lang="zh" hreflang="zh-CN">中文</a>'
              '<a class="ds-locale-toggle-item%s" href="%s" data-lang="en" hreflang="en">EN</a></div>') % (active_zh, href_zh, active_en, href_en)
    s = sub(s, r'<div class="ds-locale-toggle">\s*<button type="button" class="ds-locale-toggle-item[^"]*">中文</button>\s*<button type="button" class="ds-locale-toggle-item[^"]*">EN</button></div>',
            toggle, count=2)
    s = sub(s, r'<button class="md:hidden flex items-center justify-center w-10 h-10 text-ds-primary">',
            '<button type="button" class="md:hidden flex items-center justify-center w-10 h-10 text-ds-primary" data-menu-open aria-label="%s">' % esc(t['menu_aria'][0]))
    # mobile menu header logo + close button
    s = sub(s, r'<a class="flex items-center text-\[var\(--ds-color-brand-medium-reverse\)\]" href="/harness/(?:en/)?"><svg width="143".*?</svg></a>\s*<button class="flex items-center justify-center w-10 h-10 text-ds-primary">',
            '<a class="flex items-center text-[var(--ds-color-brand-medium-reverse)]" href="%s">%s</a><button type="button" class="flex items-center justify-center w-10 h-10 text-ds-primary" data-menu-close aria-label="%s">' % (home, logo, esc(t['menu_aria'][1])))
    # mobile nav links
    for (old, (new, href)) in zip(o['nav'], t['nav']):
        ext = ' target="_blank" rel="noopener noreferrer"' if href.startswith('http') else ''
        s = sub(s, r'<a href="[^"]*" target="_blank" rel="noopener noreferrer" class="ds-mobile-menu-item">%s</a>' % rx(old),
                '<a href="%s"%s class="ds-mobile-menu-item">%s</a>' % (href, ext, esc(new)))

    # --- hero background: drop the two shader canvases and the client-only 3D block
    s = sub(s, r'<div class="absolute inset-0 z-0 overflow-hidden" style="mask:[^"]*"><canvas[^>]*></canvas></div>\s*'
               r'<div class="absolute inset-0 z-\[5\] hidden md:block" style="mask:[^"]*"><canvas[^>]*></canvas></div>\s*'
               r'<div class="absolute inset-0 z-\[2\] hidden md:flex[^"]*" style="mix-blend-mode:screen">\s*<div class="w-\[800px\] h-\[800px\] ml-\[100px\] shrink-0"><!--\$!--><!--/\$--></div></div>',
            '<div class="absolute inset-0 z-0 overflow-hidden bio-hero-bg" aria-hidden="true" style="mask:linear-gradient(#000000fc 0%, #000000e8 8.98%, transparent 100%);-webkit-mask:linear-gradient(#000000fc 0%, #000000e8 8.98%, transparent 100%)"></div>')

    # --- hero text
    s = sub(s, r'(<p data-hero-preview-label="true" class=")whitespace-nowrap ', r'\1')
    s = text(s, o['hero_label'], esc(t['hero_label']), 1)
    s = sub(s, r'(<h1 class="ds-text-hero[^"]*"[^>]*>)%s</h1>' % rx(o['h1']), r'\1%s</h1>' % esc(t['h1']))
    s = text(s, o['hero_p1'], esc(t['hero_p1']), 1)
    s = text(s, o['hero_p2'], esc(t['hero_p2']), 1)

    # --- all ds-btn-m anchors: 4 hero (desktop) + 4 hero (mobile) + 3 join, in document order
    def btn(cls, label, href, icon):
        ext = ' target="_blank" rel="noopener noreferrer"' if href.startswith('http') else ''
        return '<a class="%s ds-btn-m" href="%s"%s>%s%s</a>' % (cls, href, ext, icon, esc(label))
    hero_icons = [ICON_DOWNLOAD, ICON_DOWNLOAD, ICON_CUBE, ICON_GITHUB]
    join_icons = [ICON_GITHUB, ICON_DOWNLOAD, ICON_CUBE]
    plan = []
    for i, (label, href) in enumerate(t['hero_btns']):
        plan.append(btn('ds-btn-primary' if i == 0 else 'ds-btn-secondary', label, href, hero_icons[i]))
    plan = plan + plan
    for i, (label, href) in enumerate(t['join_btns']):
        plan.append(btn('ds-btn-primary' if i == 0 else 'ds-btn-secondary', label, href, join_icons[i]))
    anchors = list(re.finditer(r'<a class="ds-btn-(?:primary|secondary) ds-btn-m" href="[^"]*"[^>]*>.*?</a>', s, re.S))
    if len(anchors) != len(plan):
        raise BuildError('expected %d ds-btn-m anchors, found %d' % (len(plan), len(anchors)))
    out, pos = [], 0
    for m, new in zip(anchors, plan):
        out.append(s[pos:m.start()]); out.append(new); pos = m.end()
    out.append(s[pos:]); s = ''.join(out)

    # --- hero code block: tabs + panels + copy
    s = sub(s, r'<div class="ds-hero-enter flex flex-col gap-ds-3 order-2 "', '<div class="ds-hero-enter flex flex-col gap-ds-3 order-2 " data-tabs')
    s = sub(s, r'(<button class="px-ds-4 py-ds-2 [^"]*border-white/\[0\.08\]")>%s</button>' % rx(o['tabs'][0]),
            r'\1 type="button" data-tab aria-selected="true">%s</button>' % t['tabs'][0])
    s = sub(s, r'(<button class="px-ds-4 py-ds-2 [^"]*border-transparent")>%s</button>' % rx(o['tabs'][1]),
            r'\1 type="button" data-tab aria-selected="false">%s</button>' % t['tabs'][1])
    s = sub(s, r'<button class="flex items-center gap-ds-2 text-ds-description text-\[12px\] cursor-pointer hover:text-ds-primary transition-colors">(<svg.*?</svg>)([^<]+)</button>',
            r'<button type="button" class="flex items-center gap-ds-2 text-ds-description text-[12px] cursor-pointer hover:text-ds-primary transition-colors" data-copy data-copied="%s">\1<span data-copy-label>\2</span></button>' % t['copied'])
    s = sub(s, r'(<pre class="col-start-1 row-start-1 font-mono[^"]*")>(\s*<span class="select-none text-ds-brand">\$ </span>)npx @deepseek-ai/dsh web</pre>',
            r'\1 data-panel data-copy-text="%s">\2%s</pre>' % (EXE, EXE))
    s = sub(s, r'(<pre class="col-start-1 row-start-1 font-mono[^"]*invisible")>(\s*<span class="select-none text-ds-brand">\$ </span>)git clone https://github.com/deepseek-ai/deepseek-harness</pre>',
            r'\1 data-panel data-copy-text="%s">\2%s</pre>' % (DMG, DMG))

    # --- "Agent = Model + Harness" section
    s = text(s, o['pill'], t['pill'], 1)
    s = sub(s, r'(<span class="ds-font-harness[^"]*">)Harness</span>( <!-- -->|<br/>)%s</h2>' % rx(o['harness_line']),
            r'\1%s</span>\2%s</h2>' % (t['harness_word'], esc(t['harness_line'])))
    s = text(s, o['soul'], esc(t['soul']), 1)
    s = text(s, o['soul2'], esc(t['soul2']), 1)
    # card 1 title is a link to cordis → plain text
    s = sub(s, r'<a href="https://github.com/cordiverse/cordis"[^>]*class="underline [^"]*">%s</a>' % rx(o['card_titles'][0]), esc(t['cards'][0][0]))
    for i in (1, 2):
        s = text(s, o['card_titles'][i], esc(t['cards'][i][0]), 1)
    for i in range(3):
        if o['card_labels']:
            s = text(s, o['card_labels'][i], esc(t['cards'][i][1]), 1)
        s = text(s, o['card_texts'][i], esc(t['cards'][i][2]), 1)
    if not o['card_labels']:  # the English template has no mono label line; add it for parity with zh
        for i in range(3):
            s = sub(s, r'(<h3 class="ds-text-title text-ds-primary mb-ds-2">%s</h3>)' % rx(esc(t['cards'][i][0])),
                    r'\1<span class="font-mono text-[11px] text-ds-description tracking-wider block mb-ds-3">%s</span>' % esc(t['cards'][i][1]))

    # --- design section
    s = text(s, o['design_tag'], esc(t['design_tag']), 2)
    s = text(s, o['design_h2'], esc(t['design_h2']), 2)
    s = sub(s, r'<section class="ds-container py-ds-10">(\s*<div class="hidden md:block">)', r'<section id="plugins" class="ds-container py-ds-10 scroll-mt-[100px]">\1')
    # feature 1 paragraph contains a Cordis link → rebuild whole paragraph (desktop + mobile)
    s = sub(s, r'<p class="ds-text-body text-ds-description leading-\[1\.7\]">DeepSeek Harness (?:基于|is built on) \s*<a href="https://github.com/cordiverse/cordis".*?</a>[^<]*</p>',
            '<p class="ds-text-body text-ds-description leading-[1.7]">%s</p>' % esc(t['features'][0][1]), count=2)
    for i in range(3):
        s = text(s, o['feat_titles'][i], esc(t['features'][i][0]), 2)
        if o['feat_texts'][i]:
            s = text(s, o['feat_texts'][i], esc(t['features'][i][1]), 2)
    # images
    s = sub(s, r'<img src="/harness/images/harness/feat-plugin(?:\.en)?\.png" alt="[^"]*"', '<img src="%sshot-store.png" alt="%s" loading="lazy"' % (img, esc(t['img_alt'][0])), count=2)
    s = sub(s, r'<img src="/harness/images/harness/trajectory-real-view\.(?:zh|en)\.png" alt="[^"]*"', '<img src="%sshot-data.png" alt="%s" loading="lazy"' % (img, esc(t['img_alt'][1])), count=2)
    # scroll-spy hooks (desktop variant only)
    n = [0]
    def feat_block(m):
        n[0] += 1
        return m.group(0).replace('cursor-pointer"', 'cursor-pointer" data-feature="%d"' % (n[0] - 1), 1)
    s = re.sub(r'<div class="flex flex-col justify-center gap-ds-4 min-h-\[35vh\] py-\[11vh\] transition-opacity duration-500 cursor-pointer"', feat_block, s)
    if n[0] != 3:
        raise BuildError('feature blocks: %d' % n[0])
    s = sub(s, r'<div class="transition-colors duration-500 (text-ds-primary|text-ds-description)">', r'<div class="transition-colors duration-500 \1" data-feature-icon>', count=3)
    n = [0]
    def feat_panel(m):
        n[0] += 1
        return m.group(0).replace('duration-500"', 'duration-500" data-feature-panel="%d"' % (n[0] - 1), 1)
    s = re.sub(r'<div class="col-start-1 row-start-1 min-w-0 transition-opacity duration-500" style="opacity:[01];pointer-events:(?:auto|none)">', feat_panel, s)
    if n[0] != 3:
        raise BuildError('feature panels: %d' % n[0])
    # example-projects panel: replace the dsh-style project-picker mock with a real 2x2 project grid
    s, _nm = replace_mock(s, t['modes'], t['mock_aria'])
    if _nm < 1:
        raise BuildError('mock grid: %d replaced' % _nm)

    # --- "Customize" section: the NEXT_DYNAMIC video frame → static three-item block
    custom_cards = ''.join(card(ICON_FEAT[i], *t['custom'][i]) for i in range(3))
    s = sub(s, r'<h2 class="ds-text-heading1 text-ds-primary max-w-\[820px\]">%s</h2></div>\s*<div class="mt-ds-9 rounded-2xl[^"]*demo-video-frame" style="[^"]*"><!--\$!-->.*?<!--/\$--></div>' % rx(o['custom_h2']),
            '<h2 class="ds-text-heading1 text-ds-primary max-w-[820px]">%s</h2></div>'
            '<div class="mt-ds-9 bio-reveal"><div class="grid grid-cols-1 md:grid-cols-3 gap-ds-5">%s</div></div>' % (esc(t['custom_h2']), custom_cards))

    # --- get started
    s = sub(s, r'<section class="ds-container py-ds-10">(\s*<div style="opacity:0;transform:translateY\(20px\)">\s*<span class="inline-flex items-center rounded-\[8px\] p-\[1px\] "[^>]*>\s*<span[^>]*>%s</span>)' % rx(o['start_tag']),
            r'<section id="download" class="ds-container py-ds-10 scroll-mt-[100px]">\1')
    s = text(s, o['start_tag'], esc(t['start_tag']), 1)
    s = text(s, o['start_h2'], esc(t['start_h2']), 1)
    for (ot, od), (nt, nd, code) in zip(o['start'], t['start']):
        s = sub(s, r'<h3 class="ds-text-subtitle text-ds-primary">%s</h3>' % rx(ot), '<h3 class="ds-text-subtitle text-ds-primary">%s</h3>' % esc(nt))
        s = text(s, od, esc(nd), 1)
    codes = [t['start'][0][2], t['start'][1][2]]
    for old, new in zip(['npx @deepseek-ai/dsh web', 'git clone https://github.com/deepseek-ai/deepseek-harness'], codes):
        s = sub(s, r'(<code class="min-w-0 whitespace-pre-wrap break-all">\s*<span class="select-none text-ds-brand">\$ </span>)%s</code>\s*<button type="button" class="shrink-0 font-sans text-\[12px\] text-ds-description hover:text-ds-primary transition-colors">' % rx(old),
                r'\1%s</code><button type="button" class="shrink-0 font-sans text-[12px] text-ds-description hover:text-ds-primary transition-colors" data-copy data-copy-text="%s" data-copied="%s">' % (esc(new), esc(new), t['copied']))

    # --- join section: drop the 3D block + canvas, keep the blurred glows
    s = sub(s, r'<div class="absolute -inset-\[30%\] z-0 pointer-events-none hidden md:block" style="[^"]*"><!--\$!--><!--/\$--></div>\s*', '')
    s = sub(s, r'<div class="absolute top-\[80px\] left-0 w-full h-\[500px\] pointer-events-none z-0" style="opacity:0;transform:scale\(0\.85\)">\s*<div class="absolute inset-0" style="mask:[^"]*"><canvas[^>]*></canvas></div>',
            '<div class="absolute top-[80px] left-0 w-full h-[500px] pointer-events-none z-0" aria-hidden="true">')
    s = sub(s, r'<section id="products" class="([^"]*)" style="min-height:min\(60vh, 720px\);opacity:0;filter:blur\(10px\);transform:translateY\(40px\)">',
            r'<section id="join" class="\1 bio-reveal" style="min-height:min(60vh, 720px)">')
    s = text(s, o['join_h2'], esc(t['join_h2']), 1)
    s = text(s, o['join_p'], esc(t['join_p']), 1)

    # --- footer: WeChat QR → small mark; company text → ours; policy links → user guide / GitHub
    s = sub(s, r'<div class="ds-qr-trigger  relative ">.*?</div></div></div>(\s*</div>\s*<p class="ds-text-caption text-ds-description text-center">)',
            r'<span class="flex items-center gap-ds-2 text-ds-secondary"><span class="w-5 h-5 flex items-center justify-center">%s</span><span class="ds-text-caption whitespace-nowrap">BioDSH</span></span>\1'
            % MARK_SVG.replace('width="28" height="28"', 'width="20" height="20"'))
    s = sub(s, r'>%s</p>' % rx(o['footer']), '>%s</p>' % esc(t['footer']))
    fnav = ('<nav aria-label="%s" class="flex flex-wrap items-center justify-center gap-x-ds-3 gap-y-ds-2 xl:justify-self-end">'
            '<a class="ds-text-caption text-ds-primary transition-opacity hover:opacity-70 whitespace-nowrap" href="%s" target="_blank" rel="noopener noreferrer">%s</a>'
            '<span aria-hidden="true" class="ds-text-caption text-ds-description">·</span>'
            '<a class="ds-text-caption text-ds-primary transition-opacity hover:opacity-70 whitespace-nowrap" href="%s" target="_blank" rel="noopener noreferrer">%s</a></nav>'
            ) % (esc(t['footer_aria']), t['footer_nav'][0][1], esc(t['footer_nav'][0][0]), t['footer_nav'][1][1], esc(t['footer_nav'][1][0]))
    s = sub(s, r'<nav aria-label="%s" class="[^"]*">.*?</nav>' % rx(o['footer_aria']), fnav)

    # --- scroll-reveal inline styles (driven by their JS) → progressive .bio-reveal class
    def reveal(m):
        return m.group(1) + ' bio-reveal"' if m.group(1) else 'class="bio-reveal"'
    s = re.sub(r'(class="[^"]*)" style="opacity:0;transform:translateY\(\d+px\)"', lambda m: m.group(1) + ' bio-reveal"', s)
    s = re.sub(r'<div style="opacity:0;transform:translateY\(\d+px\)">', '<div class="bio-reveal">', s)
    if 'opacity:0;transform:translateY' in s:
        raise BuildError('leftover reveal styles')

    # --- sanity: nothing of theirs left
    for bad in ('/harness/', '_next', 'deepseek-ai/', 'cordiverse', 'arxiv.org', 'qr-wechat', '<canvas', '<!--$!-->', 'deepseek-harness.github.io', '深度求索', 'DeepSeek. All rights'):
        if bad in s:
            i = s.find(bad)
            raise BuildError('leftover %r near: %s' % (bad, s[max(0, i - 120):i + 80]))

    css = 'ds.css' if root else '../ds.css'
    js = 'site.js' if root else '../site.js'
    favicon = img + 'favicon-256.png'
    redirect = ''  # English is the default landing page; language is switched only via the toggle
    head = ('<!DOCTYPE html><html lang="%s" data-theme="dark"><head><meta charset="utf-8"/>'
            '<meta name="viewport" content="width=device-width, initial-scale=1"/>'
            '<title>%s</title><meta name="description" content="%s"/>'
            '<meta property="og:title" content="%s"/><meta property="og:description" content="%s"/>'
            '<link rel="alternate" hreflang="en" href="/"/><link rel="alternate" hreflang="zh-CN" href="/zh/"/><link rel="alternate" hreflang="x-default" href="/"/>'
            '<link rel="icon" href="%s" type="image/png"/>'
            '<link rel="preconnect" href="https://fonts.googleapis.com"/><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin/>'
            '<link rel="stylesheet" href="%s"/>'
            '<meta name="google" content="notranslate"/>%s</head><body>'
            ) % (t['html_lang'], esc(t['title']), esc(t['description']), esc(t['title']), esc(t['description']), favicon, css, redirect)
    page = head + s.strip() + '<script src="%s" defer></script></body></html>\n' % js
    return page


# ----------------------------------------------------------------------------- stylesheet
BIO_CSS = r'''
/* ---- BioDSH additions (everything above is the template's compiled stylesheet) ---- */
html,body{background:#0a0a0a}
.ds-font-harness{font-family:"Silkscreen","Edit Undo",monospace;-webkit-text-stroke:0;font-weight:400}
.bio-logo{color:var(--ds-color-text-primary)}
.bio-mark{display:block;border-radius:8px;flex-shrink:0}
.bio-wordmark{font-family:var(--ds-font-display);font-weight:600;font-size:21px;letter-spacing:-.01em;line-height:1;white-space:nowrap}
.ds-locale-toggle-item{text-decoration:none;cursor:pointer}
/* hero background: static stand-in for the two shader canvases (dark navy, faint grid, blue glow top-right) */
.bio-hero-bg{background:
  radial-gradient(55% 60% at 74% 28%,rgba(70,118,205,.30) 0%,rgba(45,88,165,.14) 38%,transparent 72%),
  radial-gradient(40% 45% at 22% 78%,rgba(30,58,120,.16) 0%,transparent 70%),
  linear-gradient(180deg,#0c1322 0%,#0a0f1a 55%,#0a0a0a 100%)}
.bio-hero-bg:before{content:"";position:absolute;inset:0;
  background-image:linear-gradient(90deg,hsla(0,0%,100%,.045) 1px,transparent 0),linear-gradient(180deg,hsla(0,0%,100%,.045) 1px,transparent 0);
  background-size:90px 90px;background-position:-12px -12px;
  -webkit-mask-image:linear-gradient(180deg,#000 0,#000 35%,transparent 100%);mask-image:linear-gradient(180deg,#000 0,#000 35%,transparent 100%)}
.bio-hero-bg:after{content:"";position:absolute;width:58%;height:64%;right:-2%;top:-4%;border-radius:50%;
  background:radial-gradient(ellipse at center,rgba(96,148,232,.42) 0%,rgba(58,100,180,.22) 35%,transparent 70%);filter:blur(70px)}
/* scroll reveal: visible without JS; animated in when JS is present */
.bio-js .bio-reveal{opacity:0;transform:translateY(20px);transition:opacity .7s ease,transform .7s ease}
.bio-js .bio-reveal.is-in{opacity:1;transform:none}
@media (prefers-reduced-motion:reduce){.bio-js .bio-reveal{opacity:1;transform:none;transition:none}}

/* --- header shrink on scroll (DeepSeek-style) --- */
.ds-header-wrapper{transition:width .32s cubic-bezier(.4,0,.2,1),padding .32s ease}
.ds-header-bar{transition:padding .32s ease,background .32s ease,box-shadow .32s ease,border-color .32s ease}
.bio-wordmark-img{height:26px;width:auto;transition:height .32s ease}
.ds-header-wrapper.is-scrolled{width:min(100% - 48px,980px);padding-top:6px}
.ds-header-bar.is-scrolled{padding:3px 16px;background:rgba(11,12,16,.72);backdrop-filter:blur(20px) saturate(1.25);-webkit-backdrop-filter:blur(20px) saturate(1.25);box-shadow:0 8px 28px rgba(0,0,0,.30);border:1px solid rgba(255,255,255,.09)}
/* the bar carries an inline padding-left/right:0 (higher specificity than a class); force inner room so the logo never crosses the pill border when shrunk */
.ds-header-bar.is-scrolled{padding-left:22px!important;padding-right:18px!important}
.ds-header-bar.is-scrolled .bio-wordmark-img{height:22px}
/* logo: blue-on-dark normally; all-white once the dark glass pill appears (avoids the muddy blue+white contrast) */
.bio-wm-white{display:none}
.ds-header-bar.is-scrolled .bio-wm-normal{display:none}
.ds-header-bar.is-scrolled .bio-wm-white{display:inline-block}
/* hero download panel */
.bio-dl-btn{display:flex;align-items:center;gap:12px;width:100%;padding:16px 18px;border-radius:12px;background:#fff;color:#0a0a0a;font-weight:600;font-size:15px;transition:transform .05s,background .15s;text-align:left}
.bio-dl-btn:hover{background:#eef0f5}.bio-dl-btn:active{transform:scale(.99)}
.bio-dl-btn .bio-dl-sub{font-weight:400;font-size:12px;opacity:.62}
.bio-dl-note{font-size:12.5px;color:var(--ds-color-text-description,#9a9ca6);line-height:1.6}
.bio-dl-alt{font-size:13px;color:var(--ds-color-text-description,#9a9ca6)}
.bio-dl-alt a{color:#7c9cff}
/* real in-app screenshots (feature blocks + example-project window) */
.bio-shot img{display:block;width:100%;height:auto}
'''


def build_css():
    css = open(os.path.join(REF, 'ds.css'), encoding='utf-8').read()
    n = len(re.findall(r'@font-face\{[^}]*\}', css))
    css = re.sub(r'@font-face\{[^}]*\}', '', css)
    # their stylesheet already imports Noto Sans SC from Google Fonts; fold everything into one import
    css = re.sub(r'@import url\("https://fonts\.googleapis\.com/[^"]*"\);?', '', css)
    css = css.replace('font-family:Edit Undo,monospace', 'font-family:"Silkscreen","Edit Undo",monospace')
    css = ('@charset "UTF-8";\n@import url("%s");\n' % GOOGLE_FONTS) + css.replace('@charset "UTF-8";', '') + BIO_CSS
    if '/harness/' in css:
        raise BuildError('leftover /harness/ url in css')
    return css, n


def main():
    out_css, n = build_css()
    with open(os.path.join(HERE, 'ds.css'), 'w', encoding='utf-8') as f:
        f.write(out_css)
    print('ds.css: %d @font-face blocks replaced by Google Fonts import' % n)
    for lang, path in (('en', 'index.html'), ('zh', os.path.join('zh', 'index.html'))):
        page = build(lang)
        full = os.path.join(HERE, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, 'w', encoding='utf-8') as f:
            f.write(page)
        print('%s: %d bytes' % (path, len(page.encode('utf-8'))))


if __name__ == '__main__':
    try:
        main()
    except BuildError as e:
        print('BUILD ERROR:', e, file=sys.stderr)
        sys.exit(1)
