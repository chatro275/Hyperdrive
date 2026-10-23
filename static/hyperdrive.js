const $=s=>document.querySelector(s);
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const size=n=>n>=1024**3?(n/1024**3).toFixed(2)+' GB':n>=1024**2?(n/1024**2).toFixed(1)+' MB':n>=1024?(n/1024).toFixed(1)+' KB':n+' B';
async function api(path,body){const r=await fetch(path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const data=await r.json();if(!r.ok)throw Error(data.error||'Request failed');return data;}
let currentFolder='',refreshSerial=0;
function breadcrumbs(){
 const parts=currentFolder?currentFolder.split('/'):[];
 $('#folder-path').innerHTML='<button data-folder="">All files</button>'+parts.map((part,i)=>'<span> / </span><button data-folder="'+esc(encodeURIComponent(parts.slice(0,i+1).join('/')))+'">'+esc(part)+'</button>').join('');
}
async function refresh(){const serial=++refreshSerial;const folder=currentFolder;try{
 const s=await api('/api/storage');const files=await api('/api/files?folder='+encodeURIComponent(folder));if(serial!==refreshSerial)return;
 $('#storage-state').textContent=(s.usb?'USB drive · ':'USB not configured · Current storage: ')+size(s.free)+' free of '+size(s.total);$('#storage-meter').value=(s.total-s.free)/s.total*100;$('#file-upload').disabled=uploading;
 breadcrumbs();$('#file-list').innerHTML=files.length?files.map(f=>{const path=folder?folder+'/'+f.name:f.name;return '<tr><td>'+(f.directory?'<button data-folder="'+esc(encodeURIComponent(path))+'">▣ '+esc(f.name)+'</button>':esc(f.name)+(f.movie?' <small>· Frame</small>':''))+'</td><td>'+(f.directory?'Folder':size(f.size))+'</td><td>'+(f.directory?'':'<a href="/api/files/download?folder='+encodeURIComponent(folder)+'&amp;name='+encodeURIComponent(f.name)+'" download>Download ↓</a>')+'</td></tr>';}).join(''):'<tr><td colspan="3">This folder is empty. Upload files or create a folder.</td></tr>';
 if($('#file-search').value)$('#file-search').dispatchEvent(new Event('input'));
 }catch(e){if(serial!==refreshSerial)return;$('#storage-state').textContent=e.message;$('#file-list').innerHTML='<tr><td colspan="3">Unable to open this folder. Use All files to return.</td></tr>';breadcrumbs();$('#file-upload').disabled=true;}}
document.addEventListener('click',e=>{const b=e.target.closest('[data-folder]');if(b&&!uploading){currentFolder=decodeURIComponent(b.dataset.folder);refresh();}});
$('#new-folder').onclick=async()=>{if(uploading)return;const name=prompt('New folder name');if(name===null)return;try{await api('/api/files/folder',{folder:currentFolder,name});await refresh();}catch(e){$('#file-status').textContent=e.message;}};
function videoChoice(name){return new Promise(resolve=>{const dialog=$('#video-choice');dialog.returnValue='cancel';$('#video-choice-name').textContent=name;dialog.addEventListener('close',()=>resolve(dialog.returnValue),{once:true});dialog.showModal();});}

let request=null,uploading=false;
$('#cancel').onclick=()=>request?.abort();
$('#file-upload').onchange=async e=>{const files=[...e.target.files];if(!files.length)return;uploading=true;e.target.disabled=true;$('#cancel').hidden=false;$('#file-progress').hidden=false;let completed=0;const destination=currentFolder;try{for(const file of files){let show=false;if(/\.(mp4|mkv|m4v|webm|mov|avi|ts)$/i.test(file.name)){const choice=await videoChoice(file.name);if(choice!=='yes'&&choice!=='no')throw Error('Upload cancelled');show=choice==='yes';}$('#file-status').textContent='Uploading '+file.name;await new Promise((resolve,reject)=>{const xhr=request=new XMLHttpRequest();xhr.open('POST','/api/files/upload?name='+encodeURIComponent(file.name)+'&folder='+encodeURIComponent(destination)+'&frame='+show);xhr.upload.onprogress=e=>{if(e.lengthComputable)$('#file-progress').value=e.loaded/e.total*100;};xhr.onload=()=>{try{const data=JSON.parse(xhr.responseText);if(xhr.status>=200&&xhr.status<300)resolve(data);else reject(Error(data.error||'Upload failed'));}catch(e){reject(e);}};xhr.onerror=()=>reject(Error('Connection lost. Please retry.'));xhr.onabort=()=>reject(Error('Upload cancelled'));xhr.send(file);});completed++;}$('#file-status').textContent=completed+' file(s) uploaded.';}catch(err){$('#file-status').textContent=err.message+' · '+completed+' completed.';}finally{request=null;uploading=false;e.target.value='';$('#cancel').hidden=true;$('#file-progress').hidden=true;await refresh();}};
refresh();setInterval(()=>{if(!uploading)refresh();},15000);

$('#file-search').oninput=e=>{const query=e.target.value.toLocaleLowerCase();document.querySelectorAll('#file-list tr').forEach(row=>row.hidden=!row.cells[0].textContent.toLocaleLowerCase().includes(query));};
