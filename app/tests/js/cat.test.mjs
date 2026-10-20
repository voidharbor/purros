// The cat: every mood draws a real sprite, the moods look different, nothing throws.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const window = {};
vm.runInNewContext(readFileSync(new URL('../../static/cat.js', import.meta.url), 'utf8'), { window, Math });
const MOODS = ['idle', 'listening', 'thinking', 'working', 'searching', 'drawing', 'playing', 'done', 'oops', 'sleeping'];
const COLORS = { fg: '#8ef0a6', hi: '#d4ffdf', dim: '#55a06a' };

function fakeCtx() {
  const px = new Map();
  return {
    px, globalAlpha: 1, fillStyle: '',
    clearRect(x, y, w, h) { for (let i = x; i < x + w; i++) for (let j = y; j < y + h; j++) px.delete(i + ',' + j); },
    fillRect(x, y) { px.set(x + ',' + y, this.fillStyle); },
  };
}

test('exports the moods', () => {
  assert.deepEqual([...window.PurrCat.MOODS], MOODS);  // spread: the array comes from another realm
});

test('every mood draws a cat at several moments', () => {
  for (const m of MOODS) for (const t of [0, 0.5, 1.3, 2.7, 9.1]) {
    const c = fakeCtx();
    window.PurrCat.draw(c, m, t, COLORS);
    assert.ok(c.px.size > 40, `${m} at ${t} drew ${c.px.size} pixels`);
    for (const k of c.px.keys()) { const [x, y] = k.split(',').map(Number); assert.ok(x >= 0 && x < 16 && y >= 0 && y < 16, k); }
  }
});

test('moods look different from each other', () => {
  const sigs = new Set(MOODS.map(m => { const c = fakeCtx(); window.PurrCat.draw(c, m, 1.3, COLORS); return [...c.px.entries()].sort().join(';'); }));
  assert.equal(sigs.size, MOODS.length);
});

test('uses the colors it is given', () => {
  const c = fakeCtx();
  window.PurrCat.draw(c, 'done', 0.4, { fg: '#ffb547', hi: '#ffe4b8', dim: '#ad7a2e' });
  assert.ok([...c.px.values()].includes('#ffb547'));
});
