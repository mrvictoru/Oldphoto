// Elements
const fileInput = document.getElementById('fileInput')
const dropArea = document.getElementById('dropArea')
const createBtn = document.getElementById('createBtn')
const status = document.getElementById('status')
const beforeImg = document.getElementById('beforeImg')
const afterImg = document.getElementById('afterImg')
const placeholder = document.getElementById('placeholder')
const slider = document.getElementById('slider')
const handle = document.getElementById('handle')
const previewWrap = document.getElementById('previewWrap')
const historyUl = document.getElementById('history')
const refreshHistoryBtn = document.getElementById('refreshHistory')
const themeToggle = document.getElementById('themeToggle')

// Theme handling
function applyTheme(t){
  document.body.classList.toggle('light', t==='light')
  document.body.classList.toggle('dark', t==='dark')
  themeToggle.textContent = t==='light' ? '🌙' : '☀️'
  localStorage.setItem('theme', t)
}
const storedTheme = localStorage.getItem('theme') || (window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark')
applyTheme(storedTheme)
themeToggle.addEventListener('click', ()=>{
  const next = document.body.classList.contains('light') ? 'dark' : 'light'
  applyTheme(next)
})

let selectedFile = null

// Drop area behaviour
dropArea.addEventListener('click', () => fileInput.click())
dropArea.addEventListener('dragover', (e) => { e.preventDefault(); dropArea.style.opacity = 0.9 })
dropArea.addEventListener('dragleave', () => { dropArea.style.opacity = 1 })
dropArea.addEventListener('drop', (e) => {
  e.preventDefault(); dropArea.style.opacity = 1
  const f = e.dataTransfer.files && e.dataTransfer.files[0]
  if (f) { fileInput.files = e.dataTransfer.files; onFileSelected(f) }
})

fileInput.addEventListener('change', (e) => {
  const f = e.target.files && e.target.files[0]
  if (f) onFileSelected(f)
})

function onFileSelected(f) {
  selectedFile = f
  placeholder.style.display = 'none'
  beforeImg.src = URL.createObjectURL(f)
  beforeImg.style.display = 'block'
  afterImg.style.display = 'none'
  slider.parentElement.style.display = 'none'
  handle.style.display = 'none'
  status.textContent = ''
}

slider && slider.addEventListener('input', (e) => updateClip(e.target.value))

function updateClip(val){
  const v = Number(val)
  afterImg.style.clipPath = `inset(0 ${100 - v}% 0 0)`
  handle.style.left = `calc(${v}% - 20px)`
}

// Pointer drag on handle / image
let dragging = false
function pointerPosToValue(clientX){
  const rect = previewWrap.getBoundingClientRect()
  let x = Math.min(Math.max(clientX - rect.left,0), rect.width)
  return (x / rect.width) * 100
}
function startDrag(e){ if(!afterImg.src) return; dragging = true; handle.classList.add('dragging') }
function endDrag(){ dragging=false; handle.classList.remove('dragging') }
function moveDrag(e){ if(!dragging) return; const val = pointerPosToValue(e.clientX); slider.value = val; updateClip(val) }
handle.addEventListener('pointerdown', (e)=>{ startDrag(e); e.preventDefault() })
window.addEventListener('pointerup', endDrag)
window.addEventListener('pointermove', moveDrag)
// Also allow dragging anywhere on the image region
previewWrap.addEventListener('pointerdown', (e)=>{ if(afterImg.style.display==='block'){ startDrag(e); moveDrag(e) }})

createBtn.addEventListener('click', async () => {
  if (!selectedFile) { alert('Please select an image to restore') ; return }
  createBtn.disabled = true
  setStatus('Uploading and restoring...','info',true)

  try {
    const fd = new FormData()
    fd.append('file', selectedFile)
    const res = await fetch('/restore', { method: 'POST', body: fd })
    if(!res.ok){ throw new Error('Server returned '+res.status) }
    const j = await res.json()
    if (j.after) {
      afterImg.src = j.after
      afterImg.style.display = 'block'
      slider.parentElement.style.display = 'block'
      handle.style.display = 'block'
      // set initial positions
      slider.value = 50
      afterImg.style.clipPath = 'inset(0 50% 0 0)'
      handle.style.left = 'calc(50% - 20px)'
      setStatus('Restoration complete','ok')
      // Add to history quickly (optimistic) then refresh
      appendHistory([j], true)
    } else {
      setStatus('No restored image returned.','warn')
    }
  } catch (err) {
    console.error(err)
    setStatus('Error: ' + (err.message || err),'error')
  } finally {
    createBtn.disabled = false
  }
})

function setStatus(msg,type='info', showSpinner=false){
  status.classList.remove('error')
  if(type==='error') status.classList.add('error')
  status.innerHTML = (showSpinner?'<span class="spinner"></span>':'') + msg
}

// History functions
async function loadHistory(){
  try {
    const res = await fetch('/history')
    if(!res.ok) throw new Error('history fetch failed')
    const arr = await res.json()
    appendHistory(arr)
  } catch(e){
    console.warn('history error', e)
  }
}

function appendHistory(items, prepend=false){
  if(!Array.isArray(items)) items=[items]
  if(prepend){ items.forEach(i=>{ renderHistoryItem(i,true) }) }
  else {
    historyUl.innerHTML=''
    items.forEach(i=> renderHistoryItem(i,false))
  }
}

function renderHistoryItem(job, prepend){
  if(!job || !job.job_id) return
  const li = document.createElement('li')
  li.innerHTML = `<span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${job.job_id}</span>`+
                 `<span class="pill">${job.after? '✓':'…'}</span>`
  li.addEventListener('click', ()=> loadJob(job.job_id))
  if(prepend) { historyUl.prepend(li) } else { historyUl.appendChild(li) }
}

async function loadJob(jobId){
  try {
    setStatus('Loading job '+jobId,'info',true)
    const res = await fetch('/history/'+jobId)
    if(!res.ok) throw new Error('job not found')
    const j = await res.json()
    placeholder.style.display='none'
    beforeImg.src = j.before
    beforeImg.style.display='block'
    if(j.after){
      afterImg.src = j.after
      afterImg.style.display='block'
      slider.parentElement.style.display='block'
      handle.style.display='block'
      slider.value=50; updateClip(50)
    }
    setStatus('Loaded job '+jobId,'ok')
  } catch(e){
    setStatus('Could not load job: '+ e.message,'error')
  }
}

refreshHistoryBtn.addEventListener('click', ()=> loadHistory())
// Initial history load
loadHistory()
