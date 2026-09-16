#!/usr/bin/env python3
# 在 build_from_dsref.py 之后运行：把 hero 右侧终端框换成 Windows/macOS 下载面板、
# hero 左侧只留 技能商店 + GitHub、开始使用改成安装包步骤。zh 与 en 各处理一次。
import re, sys
EXE='https://github.com/sagirimo/BioDSH/releases/latest'
DMG='https://github.com/sagirimo/BioDSH/releases/latest'
REL='https://github.com/sagirimo/BioDSH/releases/latest'
GH='https://github.com/sagirimo/BioDSH'
DLICON='<svg width="18" height="18" viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M8 2V10M4.6 6.9L8 10.3L11.4 6.9" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"></path><path d="M2.75 11.5V13.25H13.25V11.5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"></path></svg>'
T={
 'zh': dict(win='Windows', mac='macOS', dlwin='下载 Windows 版', dlmac='下载 macOS 版',
   subwin='x64 安装包 · 双击即装', submac='Apple 芯片 · dmg', winnote='Windows 10/11，首次运行点「更多信息 → 仍要运行」。装好后自动检查更新。',
   macnote='macOS 12+。若提示「已损坏」，打开「终端」运行 sudo xattr -cr /Applications/BioDSH.app 后再打开（未签名应用的正常拦截，App 没问题）。', intel='用 Intel 芯片的 Mac？', more='更多平台（Intel Mac / Linux）',
   gs1h='下载安装', gs1p='双击安装包，不需要管理员权限；之后有新版本会自动提示更新。',
   gs2h='填 Key、装环境', gs2p='在 DeepSeek 开放平台申请一个 Key 粘贴进「更多」；软件自带 Python 工具链，点一下一键装好 scanpy 等分析包。',
   gs2chip='更多 → 模型 API Key → 分析环境 → 一键安装', getkey='去申请 DeepSeek Key'),
 'en': dict(win='Windows', mac='macOS', dlwin='Download for Windows', dlmac='Download for macOS',
   subwin='x64 installer · double-click', submac='Apple silicon · dmg', winnote='Windows 10/11. On first run click "More info → Run anyway". Updates itself afterwards.',
   macnote='macOS 12+. If it says the app is “damaged”, open Terminal and run  sudo xattr -cr /Applications/BioDSH.app  then reopen (normal Gatekeeper block for unsigned apps).', intel='On an Intel Mac?', more='Other platforms (Intel Mac / Linux)',
   gs1h='Download & install', gs1p='Double-click the installer; no admin rights needed. New versions prompt to update.',
   gs2h='Add a key, set up the environment', gs2p='Get a DeepSeek key and paste it into "More"; the bundled Python toolchain installs scanpy and friends with one click.',
   gs2chip='More → API key → Environment → one-click install', getkey='Get a DeepSeek key'),
}
TABBTN='px-ds-4 py-ds-2 text-[13px] font-medium transition-all cursor-pointer rounded-t-[8px] border border-b-0'

def hero_panel(x):
    return ('<div class="ds-hero-enter flex flex-col gap-ds-3 order-2" data-tabs style="--enter-y:20px;animation-duration:0.9s;animation-delay:0.4s">'
      '<div class="flex gap-ds-1 px-ds-1 ml-[6px]">'
      f'<button class="{TABBTN} text-ds-primary bg-black/20 backdrop-blur-xl border-white/[0.08]" type="button" data-tab aria-selected="true">{x["win"]}</button>'
      f'<button class="{TABBTN} text-ds-description hover:text-ds-primary bg-transparent border-transparent" type="button" data-tab aria-selected="false">{x["mac"]}</button>'
      '</div>'
      '<div class="rounded-ds-media border border-white/[0.08] bg-black/20 backdrop-blur-xl overflow-hidden -mt-[13px] p-ds-6 grid">'
      f'<div data-panel class="col-start-1 row-start-1 self-start flex flex-col gap-ds-4"><a class="bio-dl-btn" href="{EXE}">{DLICON}<span>{x["dlwin"]}<span class="bio-dl-sub"> · {x["subwin"]}</span></span></a><p class="bio-dl-note">{x["winnote"]}</p></div>'
      f'<div data-panel class="col-start-1 row-start-1 self-start invisible flex flex-col gap-ds-4"><a class="bio-dl-btn" href="{DMG}">{DLICON}<span>{x["dlmac"]}<span class="bio-dl-sub"> · {x["submac"]}</span></span></a><p class="bio-dl-note">{x["macnote"]}</p><p class="bio-dl-alt">{x["intel"]} <a href="{REL}">{x["more"]}</a></p></div>'
      '</div></div>')

def process(path, lang):
    x=T[lang]; s=open(path,encoding='utf-8').read()
    # 1) hero right terminal -> download panel (match order-2 data-tabs block up to first </section>)
    n=re.subn(r'<div class="ds-hero-enter flex flex-col gap-ds-3 order-2 " data-tabs.*?</section>',
              hero_panel(x)+'</div></div></section>', s, count=1, flags=re.S)
    s, c1 = n
    # 2) hero-left: remove the two download anchors (keep skill store + github)
    s, c2 = re.subn(r'<a class="ds-btn-(?:primary|secondary) ds-btn-m" href="'+re.escape(EXE)+r'".*?</a>', '', s, count=1, flags=re.S)
    s, c3 = re.subn(r'<a class="ds-btn-(?:primary|secondary) ds-btn-m" href="'+re.escape(DMG)+r'".*?</a>', '', s, count=1, flags=re.S)
    # make the first remaining hero-left button primary (skill store), leave github secondary
    s = s.replace('<a class="ds-btn-secondary ds-btn-m" href="#plugins"', '<a class="ds-btn-primary ds-btn-m" href="#plugins"', 1)
    # 3) get-started: replace the two fake "$ ..." code rows with real controls
    coderow=r'<div class="mt-ds-2 flex items-center justify-between gap-ds-3 rounded-\[10px\] border border-ds-border-default bg-ds-surface-1 px-ds-4 py-\[14px\] font-mono text-\[14px\] text-ds-primary">.*?</div>'
    rows=re.findall(coderow, s, re.S)
    if len(rows)>=2:
        dl_pair=(f'<div class="mt-ds-2 flex flex-wrap gap-ds-2"><a class="ds-btn-primary ds-btn-s" href="{EXE}">{DLICON}{x["dlwin"]}</a>'
                 f'<a class="ds-btn-secondary ds-btn-s" href="{DMG}">{DLICON}{x["dlmac"]}</a></div>')
        s=s.replace(rows[0], dl_pair, 1)
        chip=(f'<div class="mt-ds-2 flex flex-wrap items-center gap-ds-2"><span class="px-ds-3 py-[10px] rounded-[10px] border border-ds-border-default bg-ds-surface-1 font-mono text-[13px] text-ds-primary">{x["gs2chip"]}</span>'
              f'<a class="ds-btn-secondary ds-btn-s" href="https://platform.deepseek.com/api_keys" target="_blank" rel="noopener">{x["getkey"]}</a></div>')
        s=s.replace(rows[1], chip, 1)
        c4=2
    else: c4=0
    open(path,'w',encoding='utf-8').write(s)
    print(f'{path}: hero_panel={c1} rm_exe={c2} rm_dmg={c3} getstarted_rows={c4}')

process('index.html','en')
process('zh/index.html','zh')
