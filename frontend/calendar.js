/* Compact UK calendar for aircraft-traffic analytics. */
(function(){
 const months=['January','February','March','April','May','June','July','August','September','October','November','December'],days=['M','T','W','T','F','S','S'];
 const p=n=>String(n).padStart(2,'0'),esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 function monthGrid(y,m,records,max,mode){
  const mini=mode==='year',offset=(new Date(Date.UTC(y,m-1,1)).getUTCDay()+6)%7,numDays=new Date(Date.UTC(y,m,0)).getUTCDate();
  const head=mini?`<button class="calendar-month-link" type="button" data-heat-month="${y}-${p(m)}" aria-label="Open ${months[m-1]} ${y}">${months[m-1]} <span>›</span></button>`:`<h4 class="calendar-month-title">${months[m-1]} ${y}</h4>`;
  let cells=Array(offset).fill('<span class="calendar-blank" aria-hidden="true"></span>');
  for(let d=1;d<=numDays;d++){
   const k=`${y}-${p(m)}-${p(d)}`,row=records.get(k),has=row&&row.value!=null,value=has?Number(row.value):0;
   const f=has?Math.max(.12,Math.sqrt(Math.max(0,value)/Math.max(1,max))):0;
   const bg=has?`background-color:hsl(172 74% ${Math.round(22+36*f)}%);color:${f>.5?'#072c2a':'#e7fbf7'}`:'';
   const label=`${d} ${months[m-1]} ${y}: ${has?value.toLocaleString('en-GB')+' recorded':'no recorded data'}`;
   cells.push(`<span class="calendar-date ${has?'has-data':'missing'}" title="${esc(label)}" aria-label="${esc(label)}" style="${bg}">${d}</span>`);
  }
  return `<section class="calendar-month ${mini?'calendar-mini':'calendar-large'}">${head}<div class="calendar-grid">${days.map(d=>`<span class="calendar-weekday" aria-hidden="true">${d}</span>`).join('')}${cells.join('')}</div></section>`;
 }
 function render(series,{level='year',year,month,metric='flights'}={}){
  const y=Number(year),m=Number(month||1);if(!Number.isInteger(y)||y<1970||y>2100||!Number.isInteger(m)||m<1||m>12)throw Error('Invalid calendar period');
  const records=new Map((series||[]).filter(i=>/^\d{4}-\d{2}-\d{2}$/.test(i.key||'')).map(i=>[i.key,i]));
  const max=Math.max(1,...[...records.values()].map(x=>Number(x.value)||0));
  const selected=level==='month'?[m]:Array.from({length:12},(_,i)=>i+1);
  const heading=level==='month'?months[m-1]+' '+y:String(y),unit={flights:'estimated visits',aircraft:'unique aircraft',observations:'observations'}[metric]||metric;
  return `<div class="calendar-heatmap" aria-label="${esc(heading)} traffic calendar"><div class="calendar-headline"><strong>${esc(heading)}</strong><span>Daily ${esc(unit)}</span></div><div class="calendar-months ${level==='month'?'single-month':'year-months'}">${selected.map(n=>monthGrid(y,n,records,max,level)).join('')}</div><div class="calendar-legend"><span>Less</span>${[.15,.3,.5,.7,1].map(f=>`<i style="background-color:hsl(172 74% ${Math.round(22+36*f)}%)"></i>`).join('')}<span>More</span><span class="calendar-no-data">No data</span></div></div>`;
 }
 window.AirspaceCalendar={render};
})();
