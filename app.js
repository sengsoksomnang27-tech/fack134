"use strict";
const canvas = document.getElementById('space');
const ctx = canvas.getContext('2d');
let stars = [], tick = 0;
function resize() {
  canvas.width = innerWidth; canvas.height = innerHeight;
  stars = Array.from({length: 155}, () => ({x:Math.random()*canvas.width,y:Math.random()*canvas.height,r:Math.random()*1.6+.3,s:Math.random()*.6+.15}));
}
addEventListener('resize', resize); resize();
function draw() {
  const w=canvas.width,h=canvas.height;
  ctx.fillStyle='#020613';ctx.fillRect(0,0,w,h);
  const g=ctx.createRadialGradient(w*.82,h*.42,10,w*.82,h*.42,w*.8);
  g.addColorStop(0,'#152b58');g.addColorStop(1,'#020613');ctx.fillStyle=g;ctx.fillRect(0,0,w,h);
  for(const s of stars){ctx.fillStyle='rgba(194,229,255,.8)';ctx.beginPath();ctx.arc(s.x,s.y,s.r,0,7);ctx.fill();s.y+=s.s;if(s.y>h)s.y=0;}
  const cx=w*.83,cy=h*.47;
  for(let i=0;i<5;i++){
    const r=95+i*70;ctx.strokeStyle='rgba(103,159,218,.19)';ctx.lineWidth=1;ctx.beginPath();ctx.ellipse(cx,cy,r,r*.48,-.2,0,7);ctx.stroke();
    const a=tick*(.012-i*.0016)+i*1.9,x=cx+Math.cos(a)*r,y=cy+Math.sin(a)*r*.48;
    ctx.fillStyle=['#adb4c7','#e4a45b','#55a6ff','#e17b60','#caa577'][i];ctx.beginPath();ctx.arc(x,y,[5,8,11,9,18][i],0,7);ctx.fill();
  }
  const sun=ctx.createRadialGradient(cx,cy,4,cx,cy,95);sun.addColorStop(0,'#fff0a5');sun.addColorStop(.3,'#ffb22b');sun.addColorStop(.52,'#c75a12');sun.addColorStop(1,'#c75a1200');ctx.fillStyle=sun;ctx.beginPath();ctx.arc(cx,cy,95,0,7);ctx.fill();tick++;requestAnimationFrame(draw);
}
draw();
const input=document.getElementById('url'), statusEl=document.getElementById('status'), bar=document.getElementById('bar'),percent=document.getElementById('percent'),logs=document.getElementById('logs');
const buttons=[...document.querySelectorAll('[data-platform]')];
let active=false, lastUrl='';
async function api(path, options={}) {
  let response;
  try {response=await fetch(path, {...options, cache:'no-store'});} catch(e){throw Error('Cannot connect to Python. Start app.py and open http://127.0.0.1:5055');}
  const raw=await response.text();let data;
  try {data=JSON.parse(raw);}catch(e){throw Error(`Server returned HTTP ${response.status}, not JSON. Make sure you opened http://127.0.0.1:5055 (NOT port 5000).`);}
  if(!response.ok)throw Error(data.error||`HTTP ${response.status}`);
  return data;
}
function setBusy(value){active=value;buttons.forEach(b=>b.disabled=value);}
document.getElementById('paste').onclick=async()=>{try{input.value=await navigator.clipboard.readText();}catch(e){input.focus();}};
buttons.forEach(button=>button.addEventListener('click',async()=>{
  if(active)return;
  const url=input.value.trim();if(!url){alert('Paste a media link first');input.focus();return;}
  try{
    await api('/api/download',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({platform:button.dataset.platform,url,mode:document.getElementById('mode').value})});
    lastUrl=url;setBusy(true);statusEl.textContent='Connecting...';logs.textContent='Starting download...';
  }catch(e){alert(e.message);}
}));
async function update(){
  try{
    const data=await api('/api/status');
    statusEl.textContent=data.status;percent.textContent=data.progress+'%';bar.style.width=data.progress+'%';
    logs.textContent=data.logs.length?data.logs.join('\n'):'Awaiting download mission...';
    if(active&&!data.busy){setBusy(false);if(data.success&&input.value.trim()===lastUrl)input.value='';}
  }catch(e){statusEl.textContent=e.message;}
}
setInterval(update,900);update();
