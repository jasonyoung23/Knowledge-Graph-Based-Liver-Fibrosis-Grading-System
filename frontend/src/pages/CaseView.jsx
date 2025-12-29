import React, {useEffect, useState} from 'react'
import {getCaseRaw, parseCase, gradeStruct, ingest} from '../services/api'

export default function CaseView({caseFile}){
  const [raw,setRaw] = useState('')
  const [normalized,setNormalized] = useState(null)
  const [struct,setStruct] = useState(null)
  const [grading,setGrading] = useState(null)
  const [status,setStatus] = useState('')

  useEffect(()=>{ if(caseFile){ setRaw('Loading...'); setNormalized(null); setStruct(null); setGrading(null); getCaseRaw(caseFile).then(r=>setRaw(r.raw)).catch(e=>setRaw('ERROR: '+e.message)) } },[caseFile])

  if(!caseFile) return <div>Select a case from the left</div>

  return (
    <div>
      <h2>{caseFile}</h2>
      <div style={{marginBottom:12}}>
        <button onClick={async ()=>{ setStatus('Parsing...'); try{ const r = await parseCase(raw); setNormalized(r.normalized); setStruct(r.struct); setStatus('Parsed') }catch(e){ setStatus('Parse failed: '+e.message) } }}>Parse (LLM Normalize)</button>
        <button style={{marginLeft:8}} onClick={async ()=>{ if(!struct){ setStatus('Parse first'); return } setStatus('Grading...'); try{ const r = await gradeStruct(struct); setGrading(r.grading); setStatus('Graded') }catch(e){ setStatus('Grade failed: '+e.message) } }}>Grade</button>
        <button style={{marginLeft:8}} onClick={async ()=>{ if(!struct||!grading){ setStatus('Parse+Grade required'); return } setStatus('Ingesting...'); try{ const r = await ingest(struct,grading,caseFile.replace('.txt','')); setStatus('Ingested: '+(r.slice_id||'ok')) }catch(e){ setStatus('Ingest failed: '+e.message) } }}>Ingest</button>
      </div>

      <div style={{display:'flex',gap:16}}>
        <div style={{flex:1}}>
          <h4>Raw Text</h4>
          <pre style={{whiteSpace:'pre-wrap',background:'#fafafa',padding:12,border:'1px solid #eee',maxHeight:300,overflow:'auto'}}>{raw}</pre>
        </div>

        <div style={{flex:1}}>
          <h4>LLM Normalized</h4>
          <pre style={{whiteSpace:'pre-wrap',background:'#f0fff0',padding:12,border:'1px solid #0a0',maxHeight:300,overflow:'auto'}}>{normalized || '—'}</pre>
        </div>
      </div>

      <div style={{marginTop:16}}>
        <div>
          <h4>Grading</h4>
          <pre style={{whiteSpace:'pre-wrap',background:'#fff',padding:12,border:'1px solid #eee',maxHeight:400,overflow:'auto'}}>{grading?JSON.stringify(grading,null,2):'—'}</pre>
        </div>
      </div>

      <div style={{marginTop:8,color:'#666'}}>Status: {status}</div>
    </div>
  )
}
