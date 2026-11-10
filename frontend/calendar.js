/* Compact calendar heatmap for Airspace Analytics.
   Dates are UK-local calendar days supplied by the analytics API. */
(function () {
  'use strict';
  const MONTHS=['January','February','March','April','May','June','July','August','September','October','November','December'];
  const WEEKDAYS=['M','T','W','T','F','S','S'];
  const pad=n=>String(n).padStart(2,'0');
  const escapeHtml=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const dateKey=(y,m,d)=>`${y}-${pad(m)}-${pad(d)}`;

  function monthGrid(year,month,points,max,mode){
    const isYear=mode==='year';
    const start=new Date(Date.UTC(year,month-1,1));
    const blanks=(start.getUTCDay()+6)%7;
    const totalDays=new Date(Date.UTC(year,month,0)).getUTCDate();
    const head=isYear?`<button class="calendar-month-link" data-heat-month="${year}-${pad(month)}" type="button" aria-label="Open ${MONTHS[month-1]} ${year} calendar">${MONTHS[month-1]} <span aria-hidden="true">›</span></button>`:
      `<h4 class="calendar-month-title">${MONTHS[month-1]} ${year}</h4>`;
    const days=[];
    for(let i=0;i<blanks;i++)days.push('<span class="calendar-blank" aria-hidden="true"></span>');
    for(let d=1;d<=totalDays;d++){
      const key=dateKey(year,month,d);
      const row=points.get(key);
      const observed=row&&row.value!==null&&row.value!==undefined;
      const value=observed?Number(row.value):null;
      // Missing calendar days stay dark, instead of being mistaken for 0 traffic.
      const strength=observed?Math.max(0.12,Math.sqrt(Math.max(0,value)/Math.max(1,max))):0;
      const noun=mode==='year'?'daily traffic':'daily traffic';
      const label=`${d} ${MONTHS[month-1]} ${year}: ${observed?`${Math.round(value*100)/100} ${noun}`:'No recorded traffic data'}`;
      const base=observed?`background-color:hsl(172 74% ${Math.round(22+36*strength)}%);color:${strength>.5?'#072c2a':'#e7fbf7'}`:'';
      days.push(`<span class="calendar-date ${observed?'has-data':'missing'}" title="${escapeHtml(label)}" aria-label="${escapeHtml(label)}" style="${base}">${d}</span>`);
    }
    return `<section class="calendar-month ${isYear?'calendar-mini':'calendar-large'}">${head}<div class="calendar-grid">${WEEKDAYS.map(w=>`<span class="calendar-weekday" aria-hidden="true">${w}</span>`).join('')}${days.join('')}</div></section>`;
  }
  function render(series,{level='year',year,month,metric='flights'}={}){
    const y=Number(year),m=Number(month||1);
    if(!Number.isInteger(y)||y<1970||y>2100||!Number.isInteger(m)||m<1||m>12)throw Error('Invalid calendar period');
    const points=new Map();
    for(const item of series||[]){
      if(/^\d{4}-\d{2}-\d{2}$/.test(item.key||''))points.set(item.key,item);
    }
    const max=Math.max(1,...[...points.values()].map(v=>Number(v.value)||0));
    const months=level==='month'?[m]:Array.from({length:12},(_,i)=>i+1);
    const heading=level==='month'?MONTHS[m-1]+' '+y:String(y);
    const keys={flights:'estimated visits',aircraft:'unique aircraft',observations:'observations'};
    return `<div class="calendar-heatmap" role="group" aria-label="${escapeHtml(heading)} traffic calendar">
      <div class="calendar-headline"><strong>${escapeHtml(heading)}</strong><span>Daily ${escapeHtml(keys[metric]||metric)}</span></div>
      <div class="calendar-months ${level==='month'?'single-month':'year-months'}">${months.map(mon=>monthGrid(y,mon,points,max,level)).join('')}</div>
      <div class="calendar-legend"><span>Less</span>${[0.15,.3,.5,.7,1].map(v=>`<i style="background-color:hsl(172 74% ${Math.round(22+36*v)}%)"></i>`).join('')}<span>More</span><span class="calendar-no-data">No data</span></div>
    </div>`;
  }
  window.AirspaceCalendar={render};
})();
