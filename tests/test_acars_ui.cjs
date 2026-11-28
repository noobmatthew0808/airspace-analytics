'use strict';
const fs=require('node:fs'),assert=require('node:assert/strict');
const app=fs.readFileSync('frontend/app.js','utf8');
const alerts=fs.readFileSync('frontend/alerts-ui.js','utf8');
const acars=fs.readFileSync('frontend/acars-ui.js','utf8');
assert.match(app,/mountSettingsProviders/);
assert.match(app,/mountAcarsSettings/);
assert.match(app,/#tracker/); // ACARS UI replaced; original engine/settings still retained
assert.match(app,/hash==='acars'\?'tracker'/);
assert.match(acars,/\/api\/acars\/search/);
assert.match(acars,/\/api\/acars\/track/);
assert.match(acars,/opts\(\[1,3,6,12,24\]/);
assert.match(acars,/opts\(\[1,2,3,6,12,24\]/);
assert.match(acars,/esc\(m.text\)/);
assert.match(acars,/setTimeout\(poll,5000\)/);
assert.match(alerts,/export function mountSettingsProviders/);
console.log('ACARS UI and Settings integration checks passed');

assert.match(acars,/cfg\.filter/);
assert.match(acars,/Use feeder IP only/);
assert.match(acars,/retry_seconds/);
assert.match(acars,/Waiting for the first provider searches/);
