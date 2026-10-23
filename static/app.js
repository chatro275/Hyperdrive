const $ = s => document.querySelector(s);
let movies=[], page='Library', genre='All movies', query='', current=null, toastTimer;
function escapeHTML(s){return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function toast(text){$('#toast').textContent=text;$('#toast').classList.add('show');clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('#toast').classList.remove('show'),4500);}
async function api(path,body){const r=await fetch(path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const data=await r.json();if(!r.ok)throw Error(data.error||'Request failed');return data;}
async function load(){movies=await api('/api/movies');$('#total').textContent=movies.length;render();}
function navigate(name){page=name;genre='All movies';$('.search input').value='';query='';document.querySelectorAll('.nav').forEach(b=>b.classList.toggle('active',b.dataset.page===page));$('#page-name').textContent=page==='Manage'?'Settings':page==='Library'?'Movies':page;document.querySelector('main>header').hidden=page==='Manage';document.querySelector('.tv-panel').hidden=page==='Manage';document.querySelector('.search').hidden=page==='Manage';document.querySelector('.movie-nav').hidden=page==='Manage';$('#discover').hidden=page!=='Discover';$('#management').hidden=page!=='Manage';render();if(page==='Manage')settingsSection(activeSettings);else document.querySelector('.collection').hidden=false;}
function render(){let items=movies;if(page==='Watchlist')items=items.filter(m=>m.favorite);if(page==='Continue watching')items=items.filter(m=>m.progress>0&&m.progress<.97);items=items.filter(m=>(genre==='All movies'||m.genre===genre)&&m.title.toLowerCase().includes(query.toLowerCase()));$('#collection-title').textContent=page==='Discover'?'Something for every mood.':page==='Manage'?'Your collection':page==='Library'?'The movie library.':page+'.';$('#collection-subtitle').textContent=page==='Manage'?'Select a film to edit its title, year or genre.':'Your couch. Your collection. Your call.';$('#view-all').hidden=page!=='Discover';$('#movie-count').textContent=items.length+' films';$('#empty').hidden=!!items.length;$('#empty h3').textContent=query||genre!=='All movies'?'No films found.':page==='Watchlist'?'Save something for movie night.':page==='Continue watching'?'A fresh start for your next film.':'Your next movie night starts here.';$('#empty p').textContent=query?'Try another title or genre.':page==='Watchlist'?'Tap the heart on a movie to keep it here.':'Upload films from Manage library. They will appear on your TV.';document.querySelectorAll('.chip').forEach(b=>b.classList.toggle('selected',b.dataset.genre===genre));$('#movies').innerHTML=items.map((m,i)=>`<article class="movie"><button class="poster" data-open="${m.id}" aria-label="${page==='Manage'?'Edit':'Open'} ${escapeHTML(m.title)}" style="background:linear-gradient(145deg,hsl(${85+i*31} 20% 29%),#11180f)">${m.image?`<img src="https://images.unsplash.com/${m.image}?auto=format&fit=crop&w=500&q=80" alt="" loading="lazy">`:''}<span class="poster-tag">ON YOUR PI</span><span class="poster-title">${m.caption?`<small>${escapeHTML(m.caption)}</small>`:''}${escapeHTML(m.title)}</span>${m.progress?`<span class="progress" style="width:${m.progress*100}%"></span>`:''}</button><div class="movie-info"><h3>${escapeHTML(m.title)}</h3>${`<button class="favorite ${m.favorite?'saved':''}" data-favorite="${m.id}" aria-label="${m.favorite?'Remove from':'Add to'} watchlist" aria-pressed="${!!m.favorite}">${m.favorite?'♥':'♡'}</button>`}</div><p>${escapeHTML(m.year||'Local movie')}<span>·</span>${escapeHTML(m.genre)}</p></article>`).join('');}
function openMovie(id){
 const m=movies.find(m=>String(m.id)===id);if(!m)return;current=m;
 $('#detail-content').innerHTML=page==='Manage' ? `<h2>Edit movie details</h2><form id="edit-form"><label>Title<input name="title" required value="${escapeHTML(m.title)}"></label><label>Year<input name="year" maxlength="4" value="${escapeHTML(m.year)}"></label><label>Genre<input name="genre" list="genres" value="${escapeHTML(m.genre)}"></label><datalist id="genres"><option>Adventure</option><option>Sci-Fi</option><option>Drama</option><option>Animation</option><option>Thriller</option></datalist><button class="primary">Save changes</button></form>` : `<p class="eyebrow">TONIGHT, ON YOUR TV</p><h2>${escapeHTML(m.title)}</h2><p>Play on the Raspberry Pi connected to your TV. Use your TV remote to pause, seek, or return to the library.</p><button class="primary" id="play-tv">▶ ${m.progress>0&&m.progress<.97?'Resume':'Play'} on TV</button>`;
 $('#details').showModal();
 const play=$('#play-tv');if(play)play.onclick=async()=>{play.disabled=true;try{await api('/api/tv/play',{id:m.id});$('#details').close();toast('Play request sent to your TV.');}catch(e){toast(e.message);}finally{play.disabled=false;}};
}
$('#details').addEventListener('close',render);
document.addEventListener('click',async e=>{const nav=e.target.closest('[data-page]'),chip=e.target.closest('[data-genre]'),open=e.target.closest('[data-open]'),favorite=e.target.closest('[data-favorite]');if(nav)navigate(nav.dataset.page);if(chip){genre=chip.dataset.genre;render();}if(open)openMovie(open.dataset.open);if(favorite){const m=movies.find(m=>m.id===Number(favorite.dataset.favorite));try{await api('/api/movies/'+m.id,{favorite:!m.favorite});m.favorite=!m.favorite;render();}catch(e){toast(e.message);}}if(e.target.id==='dialog-manage'){$('#details').close();navigate('Manage');}});
$('#search').addEventListener('input',e=>{query=e.target.value;render();});document.addEventListener('keydown',e=>{if(e.key==='/'&&!['INPUT','TEXTAREA'].includes(document.activeElement.tagName)){e.preventDefault();$('#search').focus();}});
$('#view-all').onclick=$('#explore').onclick=()=>navigate('Library');$('#empty-manage').onclick=()=>navigate('Manage');$('#about-frame').onclick=()=>toast('Upload movies in Manage library, then choose them on your TV using its remote.');$('#close-dialog').onclick=()=>$('#details').close();
$('#scan').onclick=async()=>{const b=$('#scan');b.disabled=true;b.textContent='Scanning…';try{const result=await api('/api/scan',{});await load();toast(`Scan complete. Found ${result.count} video files.`);}catch(e){toast(e.message);}finally{b.disabled=false;b.textContent='↻  Scan media folder';}};
$('#details').addEventListener('submit',async e=>{e.preventDefault();try{await api('/api/movies/'+current.id,Object.fromEntries(new FormData(e.target)));await load();$('#details').close();toast('Movie details saved.');}catch(e){toast(e.message);}});


async function status(){
 try{const s=await api('/api/status');$('#media-path').textContent=s.media;$('#tv-state').textContent=s.tv.online?(s.tv.playing?'Playing on TV: '+s.tv.title:'TV connected · Ready for movie night'):'TV offline · Open Kodi with the Frame add-on';$('#tv-state').classList.toggle('connected',s.tv.online);$('#disk-space').textContent=(s.free/1024**3).toFixed(1)+' GB available';$('#tv-error').textContent=s.tv.error||'';document.querySelectorAll('[data-control]').forEach(b=>b.disabled=!s.tv.online||(['shutdown','reboot'].includes(b.dataset.control)&&!s.tv.power?.[b.dataset.control]));
const a=s.tv.audio||{};
const test=s.audio_test||{};$('#audio-verification').textContent=test.time?(test.heard&&test.output===a.output?'You confirmed sound on this output.':'Sound is not confirmed for this output. Run Test sound on TV.'):'Sound has not been tested. Run Test sound on TV.';$('#volume').disabled=!s.tv.online||a.volume===undefined||a.passthrough;
if(document.activeElement!==$('#volume')&&a.volume!==undefined)$('#volume').value=a.volume;
$('#volume-value').textContent=a.volume===undefined?'—':a.volume+'%';$('#mute').textContent=a.muted?'Unmute':'Mute';
$('#audio-output').textContent=(a.output?'Output: '+a.output:'Choose HDMI in Kodi’s System → Audio settings.')+(a.passthrough?' · Passthrough enabled: adjust volume on your TV or receiver.':'');
const tracks=a.tracks||[];$('#audio-track').disabled=!s.tv.online||!tracks.length;
if(document.activeElement!==$('#audio-track')){$('#audio-track').innerHTML=tracks.length?tracks.map(t=>'<option value="'+t.index+'">'+escapeHTML((t.name||t.language||'Track '+(t.index+1))+' · '+(t.codec||'')+' · '+(t.channels||'?')+' channels')+'</option>').join(''):'<option>Start a movie to select a track</option>';if(a.track!==undefined)$('#audio-track').value=a.track;}}catch(e){$('#tv-state').textContent='Frame server is unreachable';}
}
document.querySelectorAll('[data-control]').forEach(b=>b.onclick=async()=>{try{const action=b.dataset.control;const power=['reboot','shutdown'].includes(action);if(power&&!confirm(action==='reboot'?'Stop playback and restart the Pi?':'Shut down the Pi? You will need to power it on physically afterward.'))return;await api('/api/tv/control',{action,confirmed:power});if(power)toast('Power request sent to the Pi.');}catch(e){toast(e.message);}});
let uploadRequest=null;
$('#cancel-upload').onclick=()=>uploadRequest?.abort();
$('#upload-files').addEventListener('change',async e=>{
 const files=Array.from(e.target.files);if(!files.length)return;
 e.target.disabled=true;$('#cancel-upload').hidden=false;$('#upload-progress').hidden=false;
 let completed=0;
 try{for(const file of files){
   $('#upload-label').textContent='Uploading '+file.name;
   await new Promise((resolve,reject)=>{
     const xhr=uploadRequest=new XMLHttpRequest();xhr.open('POST','/api/upload?name='+encodeURIComponent(file.name));xhr.setRequestHeader('Content-Type','application/octet-stream');
     xhr.upload.onprogress=event=>{if(event.lengthComputable){$('#upload-progress').value=event.loaded/event.total*100;$('#upload-label').textContent='Uploading '+file.name+' · '+Math.round(event.loaded/event.total*100)+'%';}};
     xhr.onload=()=>{let result;try{result=JSON.parse(xhr.responseText);}catch{reject(Error('Upload failed. Please retry.'));return;}if(xhr.status>=200&&xhr.status<300)resolve(result);else reject(Error(result.error||'Upload failed'));};
     xhr.onerror=()=>reject(Error('Connection lost. Please retry the upload.'));xhr.onabort=()=>reject(Error('Upload cancelled.'));xhr.send(file);
   });completed++;await load();
 }toast(completed+' movie'+(completed===1?'':'s')+' added. Choose Refresh library on your TV.');
 }catch(err){toast(err.message);}finally{uploadRequest=null;e.target.disabled=false;e.target.value='';$('#cancel-upload').hidden=true;$('#upload-progress').hidden=true;$('#upload-label').textContent='Choose movies to upload';status();}
});
load().catch(e=>toast(e.message));status();setInterval(status,4000);

$('#volume').oninput=e=>$('#volume-value').textContent=e.target.value+'%';
$('#volume').onchange=async e=>{try{await api('/api/tv/control',{action:'volume',value:Number(e.target.value)});}catch(err){toast(err.message);}};
$('#audio-track').onchange=async e=>{try{await api('/api/tv/control',{action:'audio_track',value:Number(e.target.value)});}catch(err){toast(err.message);}};
async function updateStatus(){try{const u=await api('/api/update');$('#update-state').textContent='Frame '+u.installed+(u.staged?' · Version '+u.staged+' ready for approval on TV':' · No update staged')+(u.running!==u.installed?' · Server restart required':'');}catch(e){$('#update-state').textContent=e.message;}}
$('#update-file').onchange=async e=>{const f=e.target.files[0];if(!f)return;e.target.disabled=true;try{if(f.size>10*1024*1024)throw Error('Choose an update ZIP under 10 MB');$('#update-state').textContent='Uploading and checking update…';const r=await fetch('/api/update/stage',{method:'POST',headers:{'Content-Type':'application/zip'},body:f});const result=await r.json();if(!r.ok)throw Error(result.error);toast('Update ready. Approve installation on your TV.');}catch(err){toast(err.message);}finally{e.target.disabled=false;e.target.value='';updateStatus();}};
updateStatus();setInterval(updateStatus,10000);

let micDirty=false,pendingVoiceFile=null;
async function voiceStatus(){try{const v=await api('/api/voice');$('#voice-enabled').checked=v.enabled;
pendingVoiceFile=v.pending_storage;$('#voice-file-request').hidden=!pendingVoiceFile;if(pendingVoiceFile)$('#voice-file-description').textContent='Move / rename: '+pendingVoiceFile.source+' → '+pendingVoiceFile.destination+' (expires after 2 minutes)';
const selected=v.settings?.device||'';
if(document.activeElement!==$('#mic-enhancement'))$('#mic-enhancement').value=v.settings?.enhancement||'balanced';
const quality=v.audio_quality||{};$('#mic-quality').textContent='Speech level '+(quality.rms||0)+'% · gain '+(quality.gain||1)+'× · clipped '+(quality.clipped||0)+'% · dropped blocks '+(v.dropped_blocks||0)+(quality.clipped>1?' — reduce microphone input volume.':'');
if(!micDirty&&document.activeElement!==$('#mic-device')){const devices=v.devices||[];$('#mic-device').innerHTML='<option value="">System default / voice.env</option>'+devices.map(d=>'<option value="'+escapeHTML(d.id)+'">'+escapeHTML(d.name)+' (input '+escapeHTML(d.id)+')</option>').join('');if(selected&&!devices.some(d=>d.id===selected)){$('#mic-device').insertAdjacentHTML('beforeend','<option value="'+escapeHTML(selected)+'">Saved input: '+escapeHTML(selected)+' (not currently listed)</option>');}$('#mic-device').value=selected;}
if(!micDirty&&document.activeElement!==$('#mic-secondary')){const select=$('#mic-secondary');select.innerHTML='<option value="">Disabled</option>'+(v.devices||[]).map(d=>'<option value="'+escapeHTML(d.id)+'">'+escapeHTML(d.name)+'</option>').join('');const saved=v.settings?.secondary_device||'';if(saved&&!Array.from(select.options).some(o=>o.value===saved))select.add(new Option('Saved input '+saved+' (unavailable)',saved));select.value=saved;}
const level=v.online&&v.enabled?Number(v.level||0):0;$('#mic-level').value=level;$('#mic-level-value').textContent=level+'%';$('#voice-status').textContent=v.error?v.error:!v.online?'Microphone service offline · Run the voice installer on your Pi':v.enabled?'Listening offline · '+v.device:'Microphone commands paused';$('#voice-message').textContent=v.message||'Speech stays on your Pi. Only explicit web-search queries are sent online.';$('#voice-results').innerHTML=(v.results||[]).map(r=>'<a href="'+escapeHTML(r.url)+'" target="_blank" rel="noopener noreferrer">'+escapeHTML(r.title)+'</a><p>'+escapeHTML(r.snippet)+'</p>').join('');}catch(e){$('#voice-status').textContent='Voice status unavailable';}}
$('#voice-enabled').onchange=async e=>{try{await api('/api/voice/settings',{enabled:e.target.checked});await voiceStatus();}catch(err){toast(err.message);}};
voiceStatus();setInterval(voiceStatus,3000);

$('#mic-device').onchange=()=>{micDirty=true;$('#mic-save-status').textContent='Unsaved microphone selection';};
$('#mic-save').onclick=async()=>{const b=$('#mic-save');b.disabled=true;try{await api('/api/voice/settings',{device:$('#mic-device').value,secondary_device:$('#mic-secondary').value});micDirty=false;$('#mic-save-status').textContent='Saved. The voice service will switch inputs within a few seconds.';await voiceStatus();}catch(e){$('#mic-save-status').textContent=e.message;}finally{b.disabled=false;}};
$('#mic-refresh').onclick=async()=>{try{await api('/api/voice/settings',{refresh:true});micDirty=false;$('#mic-save-status').textContent='Refresh requested. Allow the voice service time to restart and reload its model.';}catch(e){$('#mic-save-status').textContent=e.message;}};

async function healthStatus(run=false){
 try{const h=await api('/api/health'+(run?'/check':''),run?{}:undefined);
 $('#health-auto').checked=h.auto_recovery;
 $('#health-status').textContent=(h.checked?'Last check: '+new Date(h.checked*1000).toLocaleTimeString():'Waiting for first check')+(h.storage_error?' · '+h.storage_error:'');
 $('#health-checks').innerHTML=h.checks.map(c=>'<li>'+ (c.ok?'✓ ':'⚠ ')+escapeHTML(c.name)+': '+escapeHTML(c.message)+'</li>').join('');
 $('#health-events').innerHTML=h.events.slice(-20).reverse().map(e=>'<li>'+escapeHTML(new Date(e.time*1000).toLocaleString())+' · '+escapeHTML(e.component)+': '+escapeHTML(e.message)+'</li>').join('')||'<li>No recorded errors</li>';
 }catch(e){$('#health-status').textContent='Health monitor unreachable: '+e.message;}
}
$('#health-check').onclick=async()=>{const b=$('#health-check');b.disabled=true;try{await healthStatus(true);}finally{b.disabled=false;}};
$('#health-auto').onchange=async e=>{try{await api('/api/health/settings',{auto_recovery:e.target.checked});}catch(err){toast(err.message);}await healthStatus();};
$('#health-download').onclick=async()=>{try{const report=await api('/api/health');const url=URL.createObjectURL(new Blob([JSON.stringify(report,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='frame-error-report.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}catch(e){toast(e.message);}};
healthStatus();setInterval(healthStatus,15000);

// Keep configuration in Settings so the library stays focused on movies.
$('#management').append(document.querySelector('.voice-panel'),document.querySelector('.device-settings'));

let githubRelease=null;
$('#github-check').onclick=async()=>{const b=$('#github-check');b.disabled=true;$('#github-download').hidden=true;githubRelease=null;$('#github-status').textContent='Checking GitHub…';try{githubRelease=await api('/api/update/github/check',{});$('#github-status').textContent=githubRelease.available?'Version '+githubRelease.version+' is available from '+githubRelease.repository:'You are up to date.';$('#github-download').hidden=!githubRelease.available;}catch(e){$('#github-status').textContent=e.message;}finally{b.disabled=false;}};
$('#github-download').onclick=async()=>{if(!githubRelease)return;const b=$('#github-download');b.disabled=true;$('#github-status').textContent='Downloading and verifying release…';try{await api('/api/update/github/download',{version:githubRelease.version,digest:githubRelease.digest});$('#github-status').textContent='Downloaded. Select Review update on TV to install.';b.hidden=true;await updateStatus();}catch(e){$('#github-status').textContent=e.message;}finally{b.disabled=false;}};

$('#mic-enhancement').onchange=async e=>{try{await api('/api/voice/settings',{enhancement:e.target.value});toast('Microphone enhancement saved.');}catch(err){toast(err.message);}};

for(const choice of ['confirm','cancel'])$('#voice-file-'+choice).onclick=async()=>{if(!pendingVoiceFile)return;const token=pendingVoiceFile.token;try{await api('/api/voice/storage/'+choice,{token});await voiceStatus();}catch(e){toast(e.message);}};



$('#mic-secondary').onchange=()=>{micDirty=true;$('#mic-save-status').textContent='Unsaved microphone selection';};
const settingsNav=document.createElement('nav');settingsNav.className='settings-nav';settingsNav.setAttribute('aria-label','Settings sections');
const settingsGroups=['Library','Sound & power','Hey Hyper','Updates','Remote access','System'];
document.querySelector('.voice-panel').dataset.settings='Hey Hyper';document.querySelector('.device-settings').dataset.settings='Sound & power';
$('#management').insertBefore(settingsNav,$('#management').children[1]);
let activeSettings='Library';
function settingsSection(name){activeSettings=name;document.querySelector('.collection').hidden=page==='Manage'&&name!=='Library';$('#scan').hidden=name!=='Library';document.querySelectorAll('[data-settings]').forEach(el=>{el.hidden=el.dataset.settings!==name;});settingsNav.querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',String(b.textContent===name)));if(name==='Sound & power')document.querySelector('.device-settings').open=true;}
for(const name of settingsGroups){const button=document.createElement('button');button.textContent=name;button.onclick=()=>settingsSection(name);settingsNav.append(button);}
navigate('Library');settingsSection('Library');
if(location.hash==='#hey-hyper'){navigate('Manage');settingsSection('Hey Hyper');document.querySelector('.mic-config').open=true;}

function openSettingsHash(){if(location.hash==='#settings'){navigate('Manage');settingsSection('Library');}if(location.hash==='#remote'){navigate('Manage');settingsSection('Remote access');}}
window.addEventListener('hashchange',openSettingsHash);openSettingsHash();

let remoteAddress='';
$('#remote-check').onclick=async()=>{const button=$('#remote-check');button.disabled=true;$('#remote-status').textContent='Checking…';$('#remote-url').hidden=true;$('#remote-copy').hidden=true;try{const state=await api('/api/remote');$('#remote-status').textContent=state.message;if(state.ready){remoteAddress=state.url;$('#remote-url').href=state.url;$('#remote-url').textContent=state.url;$('#remote-url').hidden=false;$('#remote-copy').hidden=false;}}catch(e){$('#remote-status').textContent=e.message;}finally{button.disabled=false;}};
$('#remote-copy').onclick=async()=>{try{await navigator.clipboard.writeText(remoteAddress);toast('Address copied');}catch(e){toast('Select and copy the address shown above.');}};
