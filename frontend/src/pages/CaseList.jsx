import React, {useEffect, useState} from 'react'
import {listCases, uploadCase, deleteCase, batchProcess} from '../services/api'

export default function CaseList({onSelect, selected}){
  const [cases,setCases] = useState([])
  const [uploading, setUploading] = useState(false)
  const [batchResults, setBatchResults] = useState(null)
  const [batchStatus, setBatchStatus] = useState('')
  
  const refreshCases = () => {
    listCases()
      .then(r => setCases(r.cases || []))
      .catch(e => {console.error(e); setCases([])})
  }
  
  useEffect(() => { refreshCases() }, [])

  const handleFileUpload = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    
    setUploading(true)
    try {
      await uploadCase(file)
      refreshCases()
      e.target.value = ''
    } catch (err) {
      alert('Upload failed: ' + err.message)
    }
    setUploading(false)
  }

  const handleDelete = async (name) => {
    if (!confirm(`Delete ${name}?`)) return
    try {
      await deleteCase(name)
      refreshCases()
    } catch (err) {
      alert('Delete failed: ' + err.message)
    }
  }

  const handleBatchProcess = async () => {
    setBatchStatus('Running all cases...')
    setBatchResults(null)
    try {
      const r = await batchProcess()
      setBatchResults(r)
      setBatchStatus(`Batch complete: ${r.processed}/${r.total} cases processed`)
    } catch (e) {
      setBatchStatus('Batch failed: ' + e.message)
    }
  }

  return (
    <div>
      <div style={{marginBottom: 12}}>
        <label style={{display: 'block', padding: 8, background: '#eef', border: '1px dashed #66b', cursor: 'pointer'}}>
          📤 Upload .txt
          <input type="file" accept=".txt" onChange={handleFileUpload} disabled={uploading} style={{display: 'none'}} />
        </label>
      </div>

      <button onClick={handleBatchProcess} style={{width:'100%', padding:'10px', marginBottom:12, backgroundColor:'#4CAF50', color:'white', border:'none', cursor:'pointer', fontSize:'14px', fontWeight:'bold'}}>
        ▶ Run All Cases (Parse → Grade → Ingest)
      </button>

      {batchStatus && <div style={{padding:8, marginBottom:8, color:'#333', fontSize:'12px'}}>{batchStatus}</div>}

      {batchResults && (
        <div style={{marginBottom:12, padding:8, border:'1px solid #ccc', backgroundColor:'#f9f9f9', fontSize:'12px', maxHeight:200, overflow:'auto'}}>
          <strong>Results:</strong>
          <pre style={{margin:'4px 0', fontSize:'11px', whiteSpace:'pre-wrap'}}>
            {batchResults.results.map((r,i) => `${i+1}. ${r.file}: ${r.status}${r.grade ? ' ('+r.grade+')' : ''}${r.error ? ' - '+r.error : ''}`).join('\n')}
          </pre>
        </div>
      )}

      {cases.map(c => (
        <div key={c.name} style={{padding:8, marginBottom:6, background:selected===c.name? '#eef':'transparent', cursor:'pointer', display:'flex', justifyContent:'space-between', alignItems:'center'}}>
          <span onClick={() => onSelect(c.name)} style={{flex:1}}>{c.name}</span>
          <button onClick={() => handleDelete(c.name)} style={{background:'#fee', border:'1px solid #a00', color:'#a00', padding:'4px 8px', cursor:'pointer'}}>🗑</button>
        </div>
      ))}
    </div>
  )
}
