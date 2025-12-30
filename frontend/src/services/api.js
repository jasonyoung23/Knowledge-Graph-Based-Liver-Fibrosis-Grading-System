const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

async function fetchJSON(path, opts){
  const res = await fetch(API_BASE + path, opts)
  if(!res.ok){
    const t = await res.text()
    throw new Error(t || res.statusText)
  }
  return res.json()
}

export async function listCases(){
  return fetchJSON('/api/cases')
}

export async function getCaseRaw(name){
  return fetchJSON(`/api/case/${encodeURIComponent(name)}/raw`)
}

export async function parseCase(text){
  return fetchJSON('/api/case/parse',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text})})
}

export async function gradeStruct(struct){
  return fetchJSON('/api/case/grade',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({struct})})
}

export async function ingest(struct, grading, slice_hint){
  return fetchJSON('/api/case/ingest',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({struct,grading,slice_hint})})
}

export async function getReport(){
  return fetchJSON('/api/report')
}

export async function batchProcess(files = null){
  const body = files && files.length > 0 ? { files_to_process: files } : {}
  return fetchJSON('/api/batch-process', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)})
}

export async function uploadCase(file){
  const formData = new FormData()
  formData.append('file', file)
  const res = await fetch(API_BASE + '/api/case/upload', {method:'POST', body:formData})
  if(!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function deleteCase(name){
  return fetchJSON(`/api/case/${encodeURIComponent(name)}`, {method:'DELETE'})
}

export async function clearDatabase(){
  return fetchJSON('/api/clear-database', {method:'DELETE'})
}
