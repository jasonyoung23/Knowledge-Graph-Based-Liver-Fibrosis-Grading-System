import React, {useState} from 'react'
import CaseList from './pages/CaseList'
import CaseView from './pages/CaseView'
import './styles.css'

export default function App(){
  const [selected, setSelected] = useState(null)

  return (
    <div className="app-container">
      {/* 侧边栏 */}
      <div className="sidebar">
        <div className="sidebar-header">
          <h2>
            🏥 肝纤维化分级系统
          </h2>
        </div>
        <div className="sidebar-content">
          <CaseList onSelect={setSelected} selected={selected} />
        </div>
      </div>

      {/* 主要内容区域 */}
      <div className="main-content">
        <CaseView caseFile={selected} />
      </div>
    </div>
  )
}
