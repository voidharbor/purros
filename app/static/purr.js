/* PurrOS screen: the input line, the stream, the cat, and the WebSocket to purrd. */
(function () {
  const $ = s => document.querySelector(s);
  const screen = $('#screen'), term = $('#term'), out = $('#out'), input = $('#input');
  const before = $('#before'), cursor = $('#cursor'), after = $('#after');
  const statusEl = $('#status'), whereEl = $('#where');
  const catCtx = $('#cat').getContext('2d'), bootCtx = $('#bootCat').getContext('2d');
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;

  let ws = null, settings = null, connected = false, firstHello = true;
  let runSeq = 0, busy = 0, outBlock = null, progressEl = null, progressTimer = null;
  let pendingAsk = null, awaitingName = false;
  const history = [], panes = new Map();
  let histPos = -1, draft = '';
  let completeId = 0;

  /* ---------- the cat and the status word ---------- */
  let mood = 'sleeping', moodWord = 'waking up', bootMood = 'sleeping';
  let lastInput = performance.now(), holdUntil = 0, moodQ = [], moodTimer = null, backTimer = null, mediaPlaying = 0;
  let colors = { fg: '#8ef0a6', hi: '#d4ffdf', dim: '#55a06a' };

  function readColors() {
    const cs = getComputedStyle(screen);
    colors = { fg: cs.getPropertyValue('--s-fg').trim(), hi: cs.getPropertyValue('--s-hi').trim(), dim: cs.getPropertyValue('--s-dim').trim() };
  }
  function showMood(m, w) {
    mood = m; moodWord = w; statusEl.textContent = w;
    clearTimeout(backTimer);
    if (m === 'done' || m === 'oops') backTimer = setTimeout(() => queueMood('idle', 'ready'), 2600);
    if (m !== 'sleeping') lastInput = performance.now();
  }
  /* every mood but idle stays up at least a moment, so quick jobs still show what happened */
  function queueMood(m, w) { moodQ.push([m, w]); pumpMood(); }
  function pumpMood() {
    if (moodTimer) return;
    const now = performance.now();
    if (now < holdUntil) { moodTimer = setTimeout(() => { moodTimer = null; pumpMood(); }, holdUntil - now); return; }
    const next = moodQ.shift();
    if (!next) return;
    showMood(next[0], next[1]);
    holdUntil = now + (next[0] === 'idle' ? 0 : 650);
    if (moodQ.length) pumpMood();
  }
  function wake() {
    lastInput = performance.now();
    if (mood === 'sleeping' && connected) { moodQ = []; holdUntil = 0; queueMood('idle', 'ready'); }
  }

  let lastFrame = 0;
  function frame(now) {
    requestAnimationFrame(frame);
    if (now - lastFrame < 80) return;
    lastFrame = now;
    const napAfter = ((settings && settings.nap_seconds) || 45) * 1000;
    if (mood === 'idle' && !busy && !mediaPlaying && now - lastInput > napAfter) showMood('sleeping', 'napping');
    const t = now / 1000;
    PurrCat.draw(catCtx, mood, t, colors);
    if (!bootDone) PurrCat.draw(bootCtx, bootMood, t, colors);
  }

  /* ---------- clock and greeting ---------- */
  function tick() {
    const d = new Date(); let h = d.getHours(); const m = String(d.getMinutes()).padStart(2, '0');
    const ap = h < 12 ? 'am' : 'pm'; h = h % 12 || 12;
    $('#clock').textContent = h + ':' + m + ' ' + ap;
  }
  tick(); setInterval(tick, 15000);
  function greet(name) {
    const h = new Date().getHours(), n = name ? ', ' + name.toLowerCase() : '';
    if (h >= 5 && h < 12) return 'good morning' + n + '.';
    if (h >= 12 && h < 17) return 'good afternoon' + n + '.';
    if (h >= 17 && h < 23) return 'good evening' + n + '.';
    return 'still up' + n + '?';
  }

  /* ---------- the stream ---------- */
  const esc = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const ANSI = /\x1b\[[0-9;?]*[ -\/]*[@-~]|\x1b[()][A-Z0-9]|\x1b[=>]|\r(?!\n)/g;
  function nearBottom() { return term.scrollHeight - term.scrollTop - term.clientHeight < 80; }
  function scrollDown(force) { if (force || nearBottom()) term.scrollTop = term.scrollHeight; }
  function add(html, cls) {
    const stick = nearBottom();
    const d = document.createElement('div');
    d.className = cls || 'line';
    d.innerHTML = html;
    out.appendChild(d);
    scrollDown(stick);
    return d;
  }
  function addLine(text, cls) { return add(esc(text), 'line' + (cls ? ' ' + cls : '')); }
  function gap() { add('', 'gap'); }
  function openButton(path, label, cls) {
    return '<button class="link' + (cls ? ' ' + cls : '') + '" data-open="' + esc(path) + '" data-label="' + esc(label) + '">' + esc(label) + '</button>';
  }

  function fmt(s) { s = Math.max(0, Math.floor(s || 0)); return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0'); }
  function player(m) {
    const video = m.kind === 'video';
    const d = add('<div class="player">' + (video ? '<video playsinline preload="metadata"></video>' : '<audio preload="metadata"></audio>') +
      '<div class="ctl"><button class="pp" aria-label="pause">❚❚</button><span class="nm">' + esc(m.name) + '</span><span class="track"><i></i></span><span class="t">0:00</span></div></div>', 'line');
    const el = d.querySelector(video ? 'video' : 'audio'), pp = d.querySelector('.pp'), bar = d.querySelector('.track i'), tEl = d.querySelector('.t');
    el.src = m.url;
    let counted = false;
    const playing = on => {
      if (on && !counted) { counted = true; mediaPlaying++; queueMood('playing', 'playing'); }
      if (!on && counted) { counted = false; mediaPlaying = Math.max(0, mediaPlaying - 1); if (!mediaPlaying && mood === 'playing') queueMood('idle', 'ready'); }
      pp.textContent = on ? '❚❚' : '▶'; pp.setAttribute('aria-label', on ? 'pause' : 'play');
    };
    el.addEventListener('play', () => playing(true));
    el.addEventListener('pause', () => playing(false));
    el.addEventListener('ended', () => playing(false));
    el.addEventListener('timeupdate', () => { const dur = el.duration || 0; bar.style.width = (dur ? el.currentTime / dur * 100 : 0).toFixed(2) + '%'; tEl.textContent = fmt(el.currentTime) + ' / ' + fmt(dur); });
    el.addEventListener('loadedmetadata', () => { tEl.textContent = '0:00 / ' + fmt(el.duration); scrollDown(true); });
    el.addEventListener('error', () => { tEl.textContent = 'can\'t play this one'; playing(false); });
    const toggle = () => { if (el.paused) el.play().catch(() => {}); else el.pause(); };
    pp.addEventListener('click', toggle);
    if (video) el.addEventListener('click', toggle);
    d.querySelector('.track').addEventListener('click', e => { const r = e.currentTarget.getBoundingClientRect(); if (el.duration) el.currentTime = (e.clientX - r.left) / r.width * el.duration; });
    document.querySelectorAll('video, audio').forEach(o => { if (o !== el && !o.paused) o.pause(); });
    el.play().catch(() => playing(false));
  }

  function media(m) {
    if (m.kind === 'image') {
      const d = add('<div class="pic"><img alt="' + esc(m.name) + '"' + (m.reveal && !reduce ? ' class="reveal"' : '') + '><div class="cap">' + esc(m.name) + '</div></div>', 'line');
      const img = d.querySelector('img');
      img.onload = () => scrollDown(true);
      img.onerror = () => { d.querySelector('.cap').textContent = 'can\'t show ' + m.name; };
      img.src = m.url;
      img.addEventListener('click', () => { $('#viewerImg').src = m.url; $('#viewer').hidden = false; });
    } else if (m.kind === 'pdf') {
      const d = add('<iframe class="pdf" title="' + esc(m.name) + '"></iframe>', 'line');
      d.querySelector('iframe').src = m.url;
    } else player(m);
  }
  $('#viewer').addEventListener('click', () => { $('#viewer').hidden = true; });

  function textFile(m) {
    const d = add('<div class="textfile"><div class="head">' + esc(m.name) + '<button class="link" data-run="edit &quot;' + esc(m.path) + '&quot;" data-label="edit ' + esc(m.name) + '">edit it</button></div><pre></pre></div>', 'line');
    d.querySelector('pre').textContent = m.lines.join('\n') + (m.more ? '\n…' : '');
    if (!m.lines.length) d.querySelector('pre').textContent = '(empty)';
  }

  function ask(m) {
    const d = add('<div class="ask"><span>' + esc(m.question) + '</span><code>' + esc(m.cmd) + '</code><button data-yes="1">yes</button><button data-yes="0">no</button></div>', 'line');
    const box = d.querySelector('.ask');
    pendingAsk = { id: m.id, box };
    box.addEventListener('click', e => { const b = e.target.closest('button'); if (b) answer(b.dataset.yes === '1'); });
    queueMood('listening', 'asking');
  }
  function answer(yes) {
    if (!pendingAsk) return;
    send({ t: 'confirm', id: pendingAsk.id, yes });
    pendingAsk.box.classList.add('answered');
    pendingAsk.box.insertAdjacentHTML('beforeend', '<span class="dim">' + (yes ? 'yes' : 'no') + '</span>');
    pendingAsk = null;
  }

  function progress(text) {
    clearInterval(progressTimer);
    if (progressEl) { progressEl.remove(); progressEl = null; }
    if (!text) return;
    progressEl = addLine(text, 'dim');
    let n = 0;
    progressTimer = setInterval(() => { n = (n + 1) % 4; progressEl.textContent = text + ' ' + '.'.repeat(n); }, 420);
  }

  /* terminal panes: xterm.js in the stream, focus moves in and back out */
  const HINTS = { nano: 'ctrl+x exits', vim: ':q exits', vi: ':q exits', htop: 'q quits', top: 'q quits', python3: 'exit() leaves', python: 'exit() leaves', less: 'q quits', man: 'q quits' };
  function xtermTheme() {
    const t = { background: 'rgba(0,0,0,0)', foreground: colors.fg, cursor: colors.fg, cursorAccent: colors.dim, selectionBackground: colors.dim };
    ['black', 'brightBlack'].forEach(k => t[k] = colors.dim);
    ['red', 'green', 'yellow', 'blue', 'magenta', 'cyan', 'white'].forEach(k => { t[k] = colors.fg; t['bright' + k[0].toUpperCase() + k.slice(1)] = colors.hi; });
    return t;
  }
  function termOpen(m) {
    const first = m.title.split(' ')[0].split('/').pop();
    const d = add('<div class="pane"><div class="ptitle"><span>' + esc(m.title) + '</span><span class="hint">' + esc(HINTS[first] || 'ctrl+d or exit closes') + '</span></div><div class="xt"></div></div>', 'line');
    const pane = d.querySelector('.pane');
    const cs = getComputedStyle(screen);
    const xt = new Terminal({
      /* Plex Mono in panes either way: VT323's glyph widths throw off xterm's grid (nano showed "f ix") */
      fontFamily: '"IBM Plex Mono", monospace', fontSize: 15, lineHeight: 1.1, rows: 24, cols: 100,
      theme: xtermTheme(), allowTransparency: true, cursorBlink: true, scrollback: 2000,
    });
    const fit = new FitAddon.FitAddon();
    xt.loadAddon(fit);
    xt.open(pane.querySelector('.xt'));
    const refit = () => { try { fit.fit(); send({ t: 'term_resize', sid: m.sid, cols: xt.cols, rows: xt.rows }); } catch (e) { /* hidden */ } };
    requestAnimationFrame(refit);
    xt.onData(data => send({ t: 'term_in', sid: m.sid, data }));
    xt.textarea.addEventListener('focus', () => screen.classList.add('paneFocus'));
    xt.textarea.addEventListener('blur', () => screen.classList.remove('paneFocus'));
    panes.set(m.sid, { xt, pane, refit });
    pane.addEventListener('mousedown', e => { e.stopPropagation(); xt.focus(); });
    scrollDown(true);
    setTimeout(() => xt.focus(), 30);
  }
  function termExit(m) {
    const p = panes.get(m.sid);
    if (!p) return;
    panes.delete(m.sid);
    p.pane.classList.add('done');
    p.xt.options.cursorBlink = false;
    p.xt.blur();
    screen.classList.remove('paneFocus');
    focusInput();
  }
  window.addEventListener('resize', () => panes.forEach(p => p.refit()));

  /* settings panel */
  function seg(key, values, current) {
    return '<div class="row"><span class="lbl">' + key + '</span><span class="seg" data-key="' + key + '">' +
      values.map(v => '<button aria-pressed="' + (v === current) + '" data-v="' + v + '">' + v + '</button>').join('') + '</span></div>';
  }
  function field(label, name, value, type) {
    return '<label class="row"><span class="lbl">' + label + '</span><input name="' + name + '" type="' + (type || 'text') + '" value="' + esc(value || '') + '"></label>';
  }
  function select(label, name, opts, value) {
    return '<label class="row"><span class="lbl">' + label + '</span><select name="' + name + '">' + opts.map(o => '<option' + (o === value ? ' selected' : '') + '>' + o + '</option>').join('') + '</select></label>';
  }
  function panel(s) {
    const d = add('<form class="panel">' +
      seg('theme', ['phosphor', 'amber', 'ice', 'paper'], s.theme) +
      seg('glow', ['off', 'light', 'more'], s.glow) +
      seg('font', ['pixel', 'clean'], s.font) +
      field('name', 'name', s.name) +
      select('brain', 'brain.kind', ['ollama', 'openai'], s.brain.kind) +
      field('address', 'brain.url', s.brain.url) + field('model', 'brain.model', s.brain.model) + field('key', 'brain.key', s.brain.key, 'password') +
      select('pictures', 'pictures.kind', ['purr-host', 'openai'], s.pictures.kind) +
      field('address', 'pictures.url', s.pictures.url) +
      seg('quality', ['careful', 'quick'], s.pictures.quality) +
      '<button class="save" type="submit">save</button></form>', 'line');
    const form = d.querySelector('form');
    form.addEventListener('click', e => {
      const b = e.target.closest('.seg button'); if (!b) return;
      e.preventDefault();
      const key = b.parentElement.dataset.key;
      b.parentElement.querySelectorAll('button').forEach(x => x.setAttribute('aria-pressed', String(x === b)));
      send({ t: 'settings', patch: key === 'quality' ? { pictures: { quality: b.dataset.v } } : { [key]: b.dataset.v } });
    });
    form.addEventListener('submit', e => {
      e.preventDefault();
      const patch = { name: form.elements.name.value.trim(), brain: {}, pictures: {} };
      ['brain.kind', 'brain.url', 'brain.model', 'brain.key', 'pictures.kind', 'pictures.url'].forEach(n => { const [a, b] = n.split('.'); patch[a][b] = form.elements[n].value.trim(); });
      send({ t: 'settings', patch });
      addLine('saved.', 'dim');
      focusInput();
    });
    form.addEventListener('keydown', e => e.stopPropagation());
  }

  function applySettings(s) {
    settings = s;
    screen.dataset.look = s.theme; screen.dataset.glow = s.glow; screen.dataset.font = s.font;
    readColors();
    panes.forEach(p => { p.xt.options.theme = xtermTheme(); });
  }

  /* ---------- messages from purrd ---------- */
  function onMessage(m) {
    switch (m.t) {
      case 'hello':
        applySettings(m.settings);
        whereEl.textContent = m.cwd;
        connected = true;
        if (firstHello) { firstHello = false; finishBoot(m); }
        else { addLine('(reconnected)', 'dim'); queueMood('idle', 'ready'); }
        break;
      case 'mood': queueMood(m.mood, m.word); break;
      case 'line': {
        const el = addLine(m.text, m.cls);
        const s = m.text.match(/There's a (.+?) in .+\. Want that one\?$/);
        if (s) el.innerHTML = esc(m.text).replace(esc(s[1]), '<button class="link hi" data-run="yes" data-label="yes">' + esc(s[1]) + '</button>');
        break;
      }
      case 'list':
        add(m.items.map(i => openButton(i.path, i.name + (i.dir ? '/' : ''), i.dir ? 'dir' : '')).join(''), 'ls');
        if (m.summary) addLine(m.summary, 'dim');
        break;
      case 'out': {
        if (!outBlock) { outBlock = add('<pre class="out"></pre>', 'line').querySelector('pre'); }
        const stick = nearBottom();
        outBlock.textContent += m.text.replace(ANSI, '');
        if (outBlock.textContent.length > 300000) outBlock.textContent = '…' + outBlock.textContent.slice(-250000);
        scrollDown(stick);
        break;
      }
      case 'media': media(m); break;
      case 'text': textFile(m); break;
      case 'ask': ask(m); break;
      case 'progress': progress(m.text); break;
      case 'term_open': termOpen(m); break;
      case 'term_out': { const p = panes.get(m.sid); if (p) p.xt.write(m.data); break; }
      case 'term_exit': termExit(m); break;
      case 'cwd': whereEl.textContent = m.cwd; break;
      case 'settings': applySettings(m.settings); break;
      case 'panel': panel(m.settings); break;
      case 'clear': out.innerHTML = ''; outBlock = null; break;
      case 'tips': add(m.items.map(t => '<button class="link" data-run="' + esc(t) + '" data-label="' + esc(t) + '">' + esc(t) + '</button>').join(''), 'tips'); break;
      case 'completions': completions(m); break;
      case 'end':
        busy = Math.max(0, busy - 1);
        outBlock = null;
        if (pendingAsk) { pendingAsk.box.classList.add('answered'); pendingAsk = null; }
        gap();
        break;
    }
  }

  /* ---------- talking to purrd ---------- */
  function send(m) { if (ws && ws.readyState === 1) ws.send(JSON.stringify(m)); }
  function connect() {
    ws = new WebSocket((location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws');
    ws.onmessage = e => { try { onMessage(JSON.parse(e.data)); } catch (err) { console.error(err); } };
    ws.onclose = () => {
      if (connected) { connected = false; queueMood('oops', 'reconnecting'); }
      busy = 0;
      setTimeout(connect, 1000);
    };
  }

  function run(text, label) {
    const shown = label || text;
    add('<span class="hi">› ' + esc(shown) + '</span>', 'line');
    if (pendingAsk && /^(y|yes|n|no)$/i.test(text.trim())) { answer(/^y/i.test(text.trim())); return; }
    if (awaitingName) {
      awaitingName = false;
      if (/^[a-z][a-z'-]{0,23}$/i.test(text.trim())) text = 'call me ' + text.trim();
    }
    busy++;
    send({ t: 'run', id: 'r' + (++runSeq), text });
  }

  function completions(m) {
    if (m.id !== 'c' + completeId) return;
    const items = m.items;
    if (!items.length) return;
    const v = input.value, cut = v.lastIndexOf(' ') + 1, last = v.slice(cut);
    let common = items[0];
    for (const it of items) { let i = 0; while (i < common.length && i < it.length && common[i].toLowerCase() === it[i].toLowerCase()) i++; common = common.slice(0, i); }
    if (items.length === 1) common = items[0];
    if (common.length > last.length) { input.value = v.slice(0, cut) + common; input.setSelectionRange(input.value.length, input.value.length); }
    else addLine(items.join('   '), 'dim');
    drawInput();
  }

  /* ---------- the input line ---------- */
  function drawInput() {
    const v = input.value, c = input.selectionStart ?? v.length;
    before.textContent = v.slice(0, c);
    cursor.textContent = v[c] || ' ';
    after.textContent = v.slice(c + 1);
  }
  function focusInput() { if (document.activeElement !== input) input.focus({ preventScroll: true }); }
  let typingTimer = null;
  input.addEventListener('input', () => {
    drawInput(); wake();
    screen.classList.add('typing');
    if (input.value && mood !== 'listening' && !busy) queueMood('listening', 'listening');
    clearTimeout(typingTimer);
    typingTimer = setTimeout(() => { screen.classList.remove('typing'); if (mood === 'listening' && !busy && !pendingAsk) queueMood('idle', 'ready'); }, 1500);
    scrollDown(true);
  });
  input.addEventListener('keyup', drawInput);
  input.addEventListener('click', drawInput);
  input.addEventListener('keydown', e => {
    wake();
    if (e.key === 'Enter') {
      e.preventDefault();
      const text = input.value;
      input.value = ''; drawInput();
      if (!text.trim()) { add('<span class="hi">›</span>', 'line'); return; }
      if (history[history.length - 1] !== text) history.push(text);
      histPos = -1;
      run(text);
    } else if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
      e.preventDefault();
      if (!history.length) return;
      if (histPos === -1) { draft = input.value; histPos = history.length; }
      histPos += e.key === 'ArrowUp' ? -1 : 1;
      histPos = Math.max(0, Math.min(history.length, histPos));
      input.value = histPos === history.length ? draft : history[histPos];
      if (histPos === history.length) histPos = -1;
      input.setSelectionRange(input.value.length, input.value.length);
      drawInput();
    } else if (e.key === 'Tab') {
      e.preventDefault();
      send({ t: 'complete', id: 'c' + (++completeId), text: input.value });
    } else if (e.ctrlKey && (e.key === 'c' || e.key === 'C')) {
      if (window.getSelection().toString()) return;
      e.preventDefault();
      add('<span class="hi">› ' + esc(input.value) + '</span><span class="dim">^C</span>', 'line');
      input.value = ''; drawInput();
      send({ t: 'stop' });
    } else if (e.ctrlKey && (e.key === 'l' || e.key === 'L')) {
      e.preventDefault();
      out.innerHTML = ''; outBlock = null;
    } else if (e.key === 'Escape') {
      $('#viewer').hidden = true;
    } else if (e.key === 'PageUp' || e.key === 'PageDown') {
      e.preventDefault();
      term.scrollBy(0, (e.key === 'PageUp' ? -1 : 1) * term.clientHeight * .85);
    }
    requestAnimationFrame(drawInput);
  });

  /* taps on anything live in the stream */
  term.addEventListener('click', e => {
    wake();
    const b = e.target.closest('[data-open],[data-run]');
    if (b) {
      e.preventDefault();
      if (b.dataset.open) run('open "' + b.dataset.open + '"', 'open ' + b.dataset.label);
      else run(b.dataset.run, b.dataset.label);
      focusInput();
      return;
    }
    if (!e.target.closest('.pane,.panel,video,audio,.track,.ctl,iframe') && !window.getSelection().toString()) focusInput();
  });
  document.addEventListener('keydown', e => {
    if (document.activeElement === input || e.target.closest('.pane,.panel')) return;
    if (e.key === 'Escape') { $('#viewer').hidden = true; return; }
    if (!e.ctrlKey && !e.metaKey && !e.altKey) focusInput();
  }, true);
  document.addEventListener('mousemove', wake, { passive: true });

  /* ---------- boot ---------- */
  let bootDone = false;
  const bootStart = performance.now();
  function finishBoot(hello) {
    const wait = Math.max(0, 1500 - (performance.now() - bootStart));
    setTimeout(() => { bootMood = 'listening'; $('#bootWord').textContent = 'hi'; }, Math.max(0, wait - 600));
    setTimeout(() => {
      $('#boot').classList.add('gone');
      setTimeout(() => { bootDone = true; $('#boot').remove(); }, 600);
      add('<span class="hi">PurrOS</span> <span class="dim">' + esc(hello.version) + '</span>', 'line');
      const name = hello.settings.name;
      if (name) addLine(greet(name) + ' type anything, plain words are fine.', 'dim');
      else { addLine('hi. what should I call you?', 'dim'); awaitingName = true; }
      gap();
      showMood('idle', 'ready');
      focusInput(); drawInput();
    }, wait);
  }
  let dots = 0;
  const bootDots = setInterval(() => { if (bootDone || bootMood !== 'sleeping') return clearInterval(bootDots); dots = (dots + 1) % 4; $('#bootWord').textContent = 'waking up' + ' .'.repeat(dots); }, 400);

  readColors();
  statusEl.textContent = moodWord;
  requestAnimationFrame(frame);
  connect();
  focusInput();
  window.PurrOS = { run, onMessage, get mood() { return mood; } };
})();
