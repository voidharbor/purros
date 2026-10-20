// The mood line: what the cat is about to act out, oldest first.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const window = {};
vm.runInNewContext(readFileSync(new URL('../../static/moodq.js', import.meta.url), 'utf8'), { window });
const { push } = window.PurrMoodQueue;
const moods = q => q.map(([m]) => m);

test('typing many keys queues listening once', () => {
  let q = [];
  for (let i = 0; i < 38; i++) q = push(q, 'listening', 'listening', 'hello');
  assert.deepEqual(moods(q), ['listening']);
});

test('nothing queued when the cat already shows that mood', () => {
  assert.deepEqual(push([], 'listening', 'listening', 'listening'), []);
});

test('a real job drops waiting listening and idle moods', () => {
  let q = push([], 'listening', 'listening', 'hello');
  q = push(q, 'idle', 'ready', 'hello');
  q = push(q, 'drawing', 'drawing', 'hello');
  assert.deepEqual(moods(q), ['drawing']);
});

test('real jobs keep their order', () => {
  let q = push([], 'searching', 'looking', 'idle');
  q = push(q, 'idle', 'ready', 'idle');
  q = push(q, 'oops', 'hmm', 'idle');
  assert.deepEqual(moods(q), ['searching', 'oops']);
});

test('the line never grows past four', () => {
  let q = [];
  for (const m of ['searching', 'working', 'thinking', 'drawing', 'done', 'oops']) q = push(q, m, m, 'idle');
  assert.deepEqual(moods(q), ['thinking', 'drawing', 'done', 'oops']);
});
