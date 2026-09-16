/* BioDSH landing page — the small amount of behaviour the template needs without Next.js. */
(function () {
  'use strict';
  var d = document, root = d.documentElement;
  root.classList.add('bio-js');

  /* file:// convenience: any relative "…/" href (zh/, ../, ./) gets index.html appended. */
  if (location.protocol === 'file:') {
    Array.prototype.forEach.call(d.querySelectorAll('a[href$="/"]'), function (a) {
      var h = a.getAttribute('href');
      if (!/^[a-z]+:/i.test(h)) a.setAttribute('href', h + 'index.html');
    });
  }

  /* Locale toggle: remember the choice so the auto-redirect on / never fights the user. */
  Array.prototype.forEach.call(d.querySelectorAll('[data-lang]'), function (a) {
    a.addEventListener('click', function () {
      try { localStorage.setItem('biodsh.lang', a.getAttribute('data-lang')); } catch (e) {}
    });
  });

  /* Header glass background once scrolled. */
  var bar = d.querySelector('.ds-header-bar');
  var wrap = d.querySelector('.ds-header-wrapper');
  function onScroll() { var on = (window.scrollY || 0) > 8; if (bar) bar.classList.toggle('is-scrolled', on); if (wrap) wrap.classList.toggle('is-scrolled', on); }
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();

  /* Mobile menu. */
  var menu = d.querySelector('.ds-mobile-menu');
  function setMenu(open) {
    if (!menu) return;
    menu.classList.toggle('is-open', open);
    d.body.style.overflow = open ? 'hidden' : '';
  }
  Array.prototype.forEach.call(d.querySelectorAll('[data-menu-open]'), function (b) {
    b.addEventListener('click', function () { setMenu(true); });
  });
  Array.prototype.forEach.call(d.querySelectorAll('[data-menu-close]'), function (b) {
    b.addEventListener('click', function () { setMenu(false); });
  });
  if (menu) Array.prototype.forEach.call(menu.querySelectorAll('a'), function (a) {
    a.addEventListener('click', function () { setMenu(false); });
  });
  d.addEventListener('keydown', function (e) { if (e.key === 'Escape') setMenu(false); });

  /* Tabs (hero code block). Active/inactive class sets are the template's own. */
  var ACTIVE = ['text-ds-primary', 'bg-black/20', 'backdrop-blur-xl', 'border-white/[0.08]'];
  var INACTIVE = ['text-ds-description', 'hover:text-ds-primary', 'bg-transparent', 'border-transparent'];
  Array.prototype.forEach.call(d.querySelectorAll('[data-tabs]'), function (group) {
    var tabs = group.querySelectorAll('[data-tab]');
    var panels = group.querySelectorAll('[data-panel]');
    function select(i) {
      Array.prototype.forEach.call(tabs, function (t, j) {
        var on = j === i;
        ACTIVE.forEach(function (c) { t.classList.toggle(c, on); });
        INACTIVE.forEach(function (c) { t.classList.toggle(c, !on); });
        t.setAttribute('aria-selected', on ? 'true' : 'false');
      });
      Array.prototype.forEach.call(panels, function (p, j) { p.classList.toggle('invisible', j !== i); });
    }
    Array.prototype.forEach.call(tabs, function (t, i) {
      t.addEventListener('click', function () { select(i); });
    });
  });

  /* Copy buttons. */
  function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) return navigator.clipboard.writeText(text);
    return new Promise(function (res, rej) {
      var ta = d.createElement('textarea');
      ta.value = text; ta.setAttribute('readonly', ''); ta.style.position = 'fixed'; ta.style.opacity = '0';
      d.body.appendChild(ta); ta.select();
      try { d.execCommand('copy'); res(); } catch (e) { rej(e); }
      d.body.removeChild(ta);
    });
  }
  Array.prototype.forEach.call(d.querySelectorAll('[data-copy]'), function (btn) {
    btn.addEventListener('click', function () {
      var text = btn.getAttribute('data-copy-text');
      if (!text) {
        var scope = btn.closest('[data-tabs]');
        var panel = scope && scope.querySelector('[data-panel]:not(.invisible)');
        text = panel ? panel.getAttribute('data-copy-text') || panel.textContent.replace(/^\s*\$\s*/, '') : '';
      }
      if (!text) return;
      copyText(text.trim()).then(function () {
        var label = btn.querySelector('[data-copy-label]') || btn;
        var was = label.textContent;
        label.textContent = btn.getAttribute('data-copied') || 'Copied';
        setTimeout(function () { label.textContent = was; }, 1500);
      }, function () {});
    });
  });

  /* Feature blocks: scroll spy that swaps the sticky image (desktop layout). */
  var blocks = Array.prototype.slice.call(d.querySelectorAll('[data-feature]'));
  var panels = Array.prototype.slice.call(d.querySelectorAll('[data-feature-panel]'));
  var current = -1;
  function setFeature(i) {
    if (i === current) return;
    current = i;
    blocks.forEach(function (b, j) {
      var on = j === i;
      b.style.opacity = on ? '1' : '0.3';
      var ic = b.querySelector('[data-feature-icon]');
      if (ic) { ic.classList.toggle('text-ds-primary', on); ic.classList.toggle('text-ds-description', !on); }
    });
    panels.forEach(function (p, j) {
      var on = j === i;
      p.style.opacity = on ? '1' : '0';
      p.style.pointerEvents = on ? 'auto' : 'none';
    });
  }
  function spy() {
    if (!blocks.length) return;
    var mid = window.innerHeight * 0.5, best = 0, bestDist = Infinity;
    blocks.forEach(function (b, j) {
      var r = b.getBoundingClientRect();
      var dist = Math.abs((r.top + r.bottom) / 2 - mid);
      if (dist < bestDist) { bestDist = dist; best = j; }
    });
    setFeature(best);
  }
  if (blocks.length) {
    blocks.forEach(function (b, j) {
      b.addEventListener('click', function () {
        setFeature(j);
        b.scrollIntoView({ block: 'center', behavior: 'smooth' });
      });
    });
    window.addEventListener('scroll', spy, { passive: true });
    window.addEventListener('resize', spy);
    spy();
  }

  /* Scroll reveal (progressive: without JS everything is simply visible). */
  var reveals = d.querySelectorAll('.bio-reveal');
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (reveals.length && 'IntersectionObserver' in window && !reduce) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) { en.target.classList.add('is-in'); io.unobserve(en.target); }
      });
    }, { rootMargin: '0px 0px -8% 0px', threshold: 0.05 });
    Array.prototype.forEach.call(reveals, function (el) { io.observe(el); });
    /* Safety net: never leave content hidden. */
    setTimeout(function () {
      Array.prototype.forEach.call(reveals, function (el) {
        var r = el.getBoundingClientRect();
        if (r.top < window.innerHeight && r.bottom > 0) el.classList.add('is-in');
      });
    }, 1200);
  } else {
    Array.prototype.forEach.call(reveals, function (el) { el.classList.add('is-in'); });
  }
})();
