import React, {useState} from 'react'
import CaseList from './pages/CaseList'
import CaseView from './pages/CaseView'

export default function App(){
  const [selected, setSelected] = useState(null)

  return (
    <div style={{display:'flex',height:'100vh',fontFamily:'sans-serif'}}>
      <div style={{width:300,borderRight:'1px solid #ddd',padding:12,overflow:'auto'}}>
        <h3>Cases</h3>
        <CaseList onSelect={setSelected} selected={selected} />
      </div>
      <div style={{flex:1,padding:16,overflow:'auto'}}>
        <CaseView caseFile={selected} />
      </div>
    </div>
  )
}
