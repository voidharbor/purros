/* The PurrOS cat: a 16 x 16 sprite drawn from code every frame, in the three tones of the current theme.
   Ported from the approved mockup (mockup 2). window.PurrCat.draw(ctx, mood, seconds, {fg, hi, dim}). */
(function () {
  const G = 16;
  const KEY = { '#': 'fg', '+': 'hi', '.': 'dim' };
  const MOODS = ['idle', 'listening', 'thinking', 'working', 'searching', 'drawing', 'playing', 'done', 'oops', 'sleeping'];
  let C = { fg: '#8ef0a6', hi: '#d4ffdf', dim: '#55a06a' };

  function painter(ctx) {
    ctx.clearRect(0, 0, G, G);
    const p = {
      px(x, y, k = 'fg', a = 1) { x = Math.round(x); y = Math.round(y); if (x < 0 || y < 0 || x >= G || y >= G || a <= 0) return; ctx.globalAlpha = Math.min(1, a); ctx.fillStyle = C[k]; ctx.fillRect(x, y, 1, 1); ctx.globalAlpha = 1; },
      cut(x, y) { ctx.clearRect(Math.round(x), Math.round(y), 1, 1); },
      map(rows, ox, oy, a = 1) { rows.forEach((r, y) => { for (let x = 0; x < r.length; x++) { const k = KEY[r[x]]; if (k) p.px(ox + x, oy + y, k, a); } }); },
      pts(list, ox, oy, k = 'fg', a = 1) { list.forEach(([x, y]) => p.px(ox + x, oy + y, k, a)); }
    };
    return p;
  }

  /* two 2 x 2 eyes cut out of the body; cols are the left edges of each eye */
  function eyes2(p, X, Y, cols, row, mode, ex = 0, ey = 0) {
    cols.forEach((c, i) => {
      const x = X + c + ex, y = Y + row + ey, left = i === 0;
      if (mode === 'open') { p.cut(x, y); p.cut(x + 1, y); p.cut(x, y + 1); p.cut(x + 1, y + 1); }
      else if (mode === 'closed') { p.cut(x, y + 1); p.cut(x + 1, y + 1); }
      else if (mode === 'happy') { const a = left ? x - 1 : x; p.cut(a, y + 1); p.cut(a + 1, y); p.cut(a + 2, y + 1); }
      else if (mode === 'small') p.cut(left ? x + 1 : x, y + 1);
    });
  }

  const PROPS = {
    bang(p, x, y) { p.px(x, y, 'hi'); p.px(x, y + 1, 'hi'); p.px(x, y + 3, 'hi'); },
    question(p, x, y) { p.pts([[0, 0], [1, 0], [2, 0], [2, 1], [1, 2], [1, 4]], x, y, 'hi'); },
    zee(p, x, y, a) { p.pts([[0, 0], [1, 0], [2, 0], [3, 0], [4, 0], [3, 1], [2, 2], [1, 3], [0, 4], [1, 4], [2, 4], [3, 4], [4, 4]], x, y, 'dim', a); },
    note(p, x, y, a) { p.pts([[1, 0], [2, 0], [1, 1], [1, 2], [0, 3], [1, 3]], x, y, 'hi', a); },
    spark(p, x, y) { p.px(x, y, 'hi'); p.pts([[1, 0], [-1, 0], [0, 1], [0, -1]], x, y, 'fg', .7); },
    dots(p, x, y, t) { const n = Math.floor(t * 3) % 4; for (let i = 0; i < n; i++) p.px(x + i * 2, y - i); },
    keys(p, y, t) { for (let x = 2; x <= 13; x++) p.px(x, y, 'dim', .7); p.px(2 + Math.floor(t * 9) % 12, y, 'hi'); p.px(2 + Math.floor(t * 7 + 5) % 12, y, 'hi'); },
    easel(p, x, y, t) {
      for (let i = 0; i < 5; i++) { p.px(x + i, y, 'dim'); p.px(x + i, y + 5, 'dim'); }
      for (let j = 1; j < 5; j++) { p.px(x, y + j, 'dim'); p.px(x + 4, y + j, 'dim'); }
      const PIC = ['hi', 'dim', 'dim', 'dim', 'dim', 'fg', 'fg', 'dim', 'fg', 'fg', 'fg', 'fg'];
      const n = Math.floor(t * 4) % 18;
      for (let i = 0; i < Math.min(n, 12); i++) p.px(x + 1 + i % 3, y + 1 + Math.floor(i / 3), PIC[i], PIC[i] === 'dim' ? .55 : 1);
    }
  };

  function stateProps(p, s, t) {
    if (s === 'listening') PROPS.bang(p, 14, 0);
    else if (s === 'thinking') PROPS.dots(p, 11, 2, t);
    else if (s === 'working') PROPS.keys(p, 15, t);
    else if (s === 'playing') for (let i = 0; i < 2; i++) { const k = (t * .7 + i * .5) % 1; PROPS.note(p, i ? 13 : 0, 5 - Math.round(k * 5), 1 - k * .8); }
    else if (s === 'done') { const S = [[1, 1], [14, 2], [14, 9], [1, 10], [8, 0]], n = Math.floor(t * 3); PROPS.spark(p, ...S[n % 5]); PROPS.spark(p, ...S[(n + 2) % 5]); }
    else if (s === 'oops') PROPS.question(p, 12, 0);
    else if (s === 'sleeping') { const k = (t * .6) % 1; PROPS.zee(p, 10 + Math.round(k), 3 - Math.round(k * 3), 1 - k * .7); }
  }

  const CAT = ['#      #', '##    ##', '########', '########', '########', '###..###', ' ###### ', '########', '########', '##.##.##'];
  const CAT_TAILS = [[[8, 9], [9, 9], [10, 8], [10, 7], [10, 6]], [[8, 9], [9, 9], [10, 9], [11, 8], [11, 7]], [[8, 9], [9, 8], [9, 7], [9, 6], [10, 5]]];

  function cat(p, s, t) {
    let X = 3, Y = 4, mode = 'open', ex = 0, ey = 0, tail = CAT_TAILS[[0, 1, 0, 2][Math.floor(t * 1.5) % 4]], mirror = false, ears = 'normal', paws = '';
    if (s === 'idle') { if ((t % 3.7) < .14) mode = 'closed'; if ((t % 5) < .25) ears = 'twitch'; }
    else if (s === 'listening') { ears = 'up'; tail = CAT_TAILS[2]; }
    else if (s === 'thinking') { ey = -1; ex = Math.floor(t * 1.3) % 2 ? 1 : -1; tail = CAT_TAILS[Math.floor(t * .8) % 2]; paws = 'chin'; }
    else if (s === 'working') paws = 'type';
    else if (s === 'searching') { const k = t % 2.4; ex = 1; tail = CAT_TAILS[1]; if (k < 1.9) { Y += 1; X += Math.floor(t * 12) % 2; } else { Y -= 2; X += 2; } }
    else if (s === 'drawing') { mirror = true; ex = 1; paws = 'reach'; }
    else if (s === 'playing') { Y += Math.floor(t * 2.5) % 2; tail = CAT_TAILS[Math.floor(t * 2.5) % 2]; }
    else if (s === 'done') { mode = 'happy'; tail = CAT_TAILS[2]; }
    else if (s === 'oops') { X = 2; mode = 'small'; mirror = true; paws = 'push'; }
    else if (s === 'sleeping') { Y += 2; mode = 'closed'; tail = [[8, 9], [9, 9], [10, 9], [11, 9]]; }
    if (s === 'drawing') PROPS.easel(p, 11, 5, t);
    p.pts(mirror ? tail.map(([x, y]) => [7 - x, y]) : tail, X, Y);
    const rows = CAT.slice(); if (ears === 'twitch') rows[0] = '       #';
    p.map(rows, X, Y);
    if (ears === 'up') { p.px(X, Y - 1); p.px(X + 7, Y - 1); }
    p.px(X - 1, Y + 5, 'dim'); p.px(X + 8, Y + 5, 'dim');
    eyes2(p, X, Y, [1, 5], 3, mode, ex, ey);
    if (paws === 'type') { const a = Math.floor(t * 8) % 2; p.px(a ? X + 1 : X + 6, Y + 10); p.px(a ? X + 2 : X + 5, Y + 10, 'dim'); }
    else if (paws === 'chin') p.px(X, Y + 6, 'hi');
    else if (paws === 'reach') { p.px(X + 8, Y + 6); p.px(X + 9, Y + 5, 'hi'); }
    else if (paws === 'push') {
      const k = (t % 2.6) / 2.6;
      for (let x = 12; x <= 15; x++) p.px(x, 10, 'dim');
      if (k < .35) { p.px(X + 8, Y + 6); p.px(X + 9, Y + 6); const cx = 12 + (k > .22 ? 1 : 0); p.pts([[0, 0], [1, 0], [0, 1], [1, 1]], cx, 8, 'hi'); }
      else if (k < .7) p.pts([[0, 0], [1, 0], [0, 1], [1, 1]], 14, 8 + Math.round((k - .35) / .35 * 8), 'hi');
    }
    stateProps(p, s, t);
  }

  window.PurrCat = {
    MOODS,
    draw(ctx, mood, t, colors) {
      if (colors) C = colors;
      cat(painter(ctx), MOODS.includes(mood) ? mood : 'idle', t);
    }
  };
})();
