/* Static presentation only. No analytics, API calls or application state. */
(()=>{
 const root=document.documentElement,button=document.getElementById('theme-toggle'),image=document.getElementById('workspace-image');
 let screen='skills',theme='light';
 try{theme=localStorage.getItem('biodsh-site-theme')|| (matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light')}catch{theme=matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'}
 if(theme!=='dark')theme='light';
 function render(){
  root.dataset.theme=theme;button.setAttribute('aria-pressed',String(theme==='dark'));
  image.src=`${image.dataset.base}showcase-${screen}-${theme}-${image.dataset.lang}.png`;
  image.alt=image.dataset.lang==='zh'?`BioDSH ${screen==='skills'?'技能中心':'工作流'}设计预览，示例内容`:`BioDSH ${screen==='skills'?'skill hub':'workflow'} design preview, illustrative content`;
  document.querySelectorAll('[data-screen]').forEach(b=>{b.classList.toggle('selected',b.dataset.screen===screen);b.setAttribute('aria-pressed',String(b.dataset.screen===screen))});
 }
 button.addEventListener('click',()=>{theme=theme==='light'?'dark':'light';try{localStorage.setItem('biodsh-site-theme',theme)}catch{}render()});
 document.querySelectorAll('[data-screen]').forEach(b=>b.addEventListener('click',()=>{screen=b.dataset.screen;render()}));render();
})();
