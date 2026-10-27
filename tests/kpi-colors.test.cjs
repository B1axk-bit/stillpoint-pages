const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');

const html = fs.readFileSync(path.join(__dirname, '../index.html'), 'utf8');
const helper = html.match(/  function kpiDirection\(k\)\{[\s\S]*?\n  \}\n/)[0];
const direction = vm.runInNewContext(helper + '\nkpiDirection;');

for (const [name, data, expected] of [
  ['legacy down flag gets the existing green class', {value:'17.57',dir:'down'}, 'dn'],
  ['dn alias remains compatible', {value:'17.57',dir:'dn'}, 'dn'],
  ['up flag remains compatible', {value:'17.57',dir:'up'}, 'up'],
  ['real negative change overrides an old up flag', {value:'109.28',chg:'−1.32%',dir:'up'}, 'dn'],
  ['real positive change overrides an old down flag', {value:'19.28',chg:'+1.32%',dir:'down'}, 'up'],
  ['zero change is neutral despite an old down flag', {value:'19.28',chg:'0.00%',dir:'down'}, ''],
  ['signed positive return is red', {value:'+1.30'}, 'up'],
  ['unicode negative return is green', {value:'−1.30'}, 'dn'],
  ['signed zero return is neutral', {value:'+0.00'}, ''],
  ['unsigned probability is not a price increase', {value:'82.3'}, ''],
  ['missing probability stays neutral', {value:'—'}, ''],
  ['positive net buying is red without a written plus', {value:'5,826',colorBy:'netFlow'}, 'up'],
  ['negative net flow is green', {value:'−6,827',colorBy:'netFlow'}, 'dn'],
  ['zero net flow is neutral', {value:'0',colorBy:'netFlow'}, ''],
  ['missing net flow is neutral', {value:'—',colorBy:'netFlow'}, ''],
]) {
  test(name, () => assert.equal(direction(data), expected));
}

test('the main cards and overview menu share the same direction helper', () => {
  assert.match(html, /var direction = kpiDirection\(k\), kd/);
  assert.match(html, /m: true, d: kpiDirection\(k\), s: k\.read/);
});
