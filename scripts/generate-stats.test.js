const test = require('node:test');
const assert = require('node:assert/strict');

const {
  buildSvg,
  computeStreaks,
  flattenDays,
  previousDate,
} = require('./generate-stats');

test('flattenDays sorts contribution days across weeks', () => {
  const days = flattenDays([
    { contributionDays: [{ date: '2026-06-30', contributionCount: 1 }] },
    { contributionDays: [{ date: '2026-06-28', contributionCount: 2 }] },
  ]);

  assert.deepEqual(days.map((day) => day.date), ['2026-06-28', '2026-06-30']);
});

test('current streak includes today when today is active', () => {
  const result = computeStreaks([
    { date: '2026-06-27', contributionCount: 0 },
    { date: '2026-06-28', contributionCount: 1 },
    { date: '2026-06-29', contributionCount: 2 },
    { date: '2026-06-30', contributionCount: 1 },
  ], '2026-06-30');

  assert.deepEqual(result, { current: 3, longest: 3, activeDays: 3 });
});

test('current streak can continue through yesterday before today is active', () => {
  const result = computeStreaks([
    { date: '2026-06-27', contributionCount: 1 },
    { date: '2026-06-28', contributionCount: 1 },
    { date: '2026-06-29', contributionCount: 1 },
    { date: '2026-06-30', contributionCount: 0 },
  ], '2026-06-30');

  assert.deepEqual(result, { current: 3, longest: 3, activeDays: 3 });
});

test('future calendar cells do not affect streak totals', () => {
  const result = computeStreaks([
    { date: '2026-06-29', contributionCount: 1 },
    { date: '2026-06-30', contributionCount: 1 },
    { date: '2026-07-01', contributionCount: 1 },
  ], '2026-06-30');

  assert.deepEqual(result, { current: 2, longest: 2, activeDays: 2 });
});

test('template values and date helpers are deterministic', () => {
  assert.equal(previousDate('2026-03-01'), '2026-02-28');
  assert.equal(buildSvg('{{A}} + {{A}} = {{B}}', { A: 2, B: 4 }), '2 + 2 = 4');
});
