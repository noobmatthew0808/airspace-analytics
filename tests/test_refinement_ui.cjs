'use strict';
const fs=require('node:fs');
const assert=require('node:assert/strict');
const src=fs.readFileSync('frontend/alerts-ui.js','utf8');
const end=src.indexOf('function renderAlertPageContents(){');
const {providers,otherSources,providerCard,otherProviderCard}=new Function(src.slice(0,end)+';return {providers,otherSources,providerCard,otherProviderCard}')();
const avio=providers.find(p=>p.id==='avioadsb');
const fi=providers.find(p=>p.id==='adsbfi');
const render=(data={})=>providerCard(avio,data);
assert.match(render(),/alert-api-icon missing/);
assert.match(render({avioadsb:{key_set:true}}),/alert-api-icon saved/);
assert.match(render({avioadsb:{key_set:true},provider_tests:{avioadsb:{ok:true,message:'Connection successful',at:1800000000}}}),/alert-api-icon verified/);
assert.match(render({avioadsb:{key_set:true},provider_tests:{avioadsb:{ok:false,message:'HTTP 403',at:1800000000}}}),/alert-api-icon missing/);
assert.match(render({avioadsb:{key_set:true},provider_tests:{avioadsb:{ok:false,message:'HTTP 403',at:1800000000}}}),/provider-result-avioadsb[^]*HTTP 403/);
assert.match(providerCard(fi,{}),/alert-api-icon keyless/);
assert.doesNotMatch(providerCard(fi,{}),/name="key"/);
assert.equal(providers.length+otherSources.length,15);
assert(otherSources.every(p=>otherProviderCard(p).includes('Not integrated')));
const app=fs.readFileSync('frontend/app.js','utf8');
assert.match(app,/\/api\/preferences/);
assert.match(app,/\$\$\('\[data-include-day\]'\)\.forEach/);
assert.match(app,/\$\$\('\[data-remove\]'\)\.forEach/);
assert.match(app,/\$\$\('\[data-suggest-exclude\]',target\)\.forEach/);
assert.match(app,/https:\/\/airplanes\.live\/myfeed\//);
assert(app.includes("https://avioadsb.org/station?id=743cc25e-05b7-472d-a6a7-f7f48d164a64"));
assert(app.includes("https://adsbiq.com/feeder/51a27442-b77e-45a3"));
assert(app.includes("https://www.adsbhub.org/statistic.php"));
assert(app.includes("https://opensky-network.org/my-opensky/account"));
const flights=fs.readFileSync('frontend/flights-ui.js','utf8');
assert.match(flights,/result\.refreshing/);
assert.match(flights,/loadFlights\(true,true\)/);
const css=fs.readFileSync('frontend/flights.css','utf8');
assert.match(css,/\.flights-table \.flights-highlight\{background:transparent!important\}/);
assert.match(css,/\.flights-table \.flights-reg-line \.flights-live-chip\.flights-lgw\{color:var\(--green,#36bc76\)!important;background:transparent!important;border:0!important/);
console.log('API cards, shared settings, cache UI and Gatwick text checks passed');

assert(providers.some(p=>p.id==='opensky'&&p.oauth));
assert.match(providerCard(providers.find(p=>p.id==='opensky'),{}),/name="client_id"/);
assert.match(providerCard(providers.find(p=>p.id==='opensky'),{}),/written permission/);
assert(providers.some(p=>p.id==='airplaneslive'&&p.keyless));
assert(providers.some(p=>p.id==='adsbhub'&&p.keyless));

// Credential type and connection status are independent, including keyless APIs.
const summary=html=>html.split('</summary>')[0];
for(const p of providers){
 const base=p.keyless?{}:{[p.id]:{key_set:true}};
 const tested=ok=>({...base,provider_tests:{[p.id]:{ok,message:'test',at:1800000000}}});
 const key=p.keyless?'keyless':'key';
 for(const [data,state] of [[base,p.keyless?'pending':'saved'],[tested(true),'verified'],[tested(false),'missing']]){
  const html=summary(providerCard(p,data));
  assert.match(html,new RegExp('alert-api-icon '+key+'"'));
  assert.match(html,new RegExp('alert-api-icon '+state+'"'));
  assert.equal((html.match(/<svg /g)||[]).length,2);
 }
}
assert.match(summary(providerCard(fi,{adsbfi:{connected:true}})),/alert-api-icon verified/);
assert.match(summary(providerCard(fi,{adsbfi:{connected:true},provider_tests:{adsbfi:{ok:false}}})),/alert-api-icon missing/);
assert.match(summary(providerCard(avio,{})),/alert-api-icon key"[^]*alert-api-icon missing/);
for(const p of otherSources)assert.equal((summary(otherProviderCard(p)).match(/<svg /g)||[]).length,2);
