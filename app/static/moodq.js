/* The line of moods waiting for the cat. Listening and idle are passing states: they never queue behind
   themselves, and a real job (drawing, searching...) clears them out, so the cat never lags behind the work.
   window.PurrMoodQueue.push(queue, mood, word, showing) returns the new queue. */
(function () {
  const PASSING = new Set(['idle', 'listening']);
  const MAX = 4;
  function push(queue, mood, word, showing) {
    const last = queue.length ? queue[queue.length - 1][0] : showing;
    if (mood === last) return queue;
    let q = PASSING.has(mood) ? queue.slice() : queue.filter(([m]) => !PASSING.has(m));
    q.push([mood, word]);
    return q.length > MAX ? q.slice(-MAX) : q;
  }
  window.PurrMoodQueue = { push };
})();
