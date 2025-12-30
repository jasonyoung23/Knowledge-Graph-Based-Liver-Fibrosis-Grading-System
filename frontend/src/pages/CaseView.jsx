import React, {useEffect, useState} from 'react'
import {getCaseRaw, parseCase, gradeStruct, ingest} from '../services/api'

export default function CaseView({caseFile}){
  const [raw, setRaw] = useState('')
  const [normalized, setNormalized] = useState(null)
  const [struct, setStruct] = useState(null)
  const [grading, setGrading] = useState(null)
  const [status, setStatus] = useState('')
  const [currentStep, setCurrentStep] = useState(0)

  useEffect(() => {
    if (caseFile) {
      setRaw('Loading...')
      setNormalized(null)
      setStruct(null)
      setGrading(null)
      setStatus('')
      setCurrentStep(0)

      getCaseRaw(caseFile)
        .then(r => {
          setRaw(r.raw)
          setCurrentStep(1)
        })
        .catch(e => {
          setRaw('ERROR: ' + e.message)
          setStatus('加载失败')
        })
    }
  }, [caseFile])

  const handleParse = async () => {
    setStatus('parsing')
    try {
      const r = await parseCase(raw)
      setNormalized(r.normalized)
      setStruct(r.struct)
      setStatus('parsed')
      setCurrentStep(2)
    } catch(e) {
      setStatus('parse-failed')
      console.error('Parse failed:', e)
    }
  }

  const handleGrade = async () => {
    if (!struct) return

    setStatus('grading')
    try {
      const r = await gradeStruct(struct)
      setGrading(r.grading)
      setStatus('graded')
      setCurrentStep(3)
    } catch(e) {
      setStatus('grade-failed')
      console.error('Grade failed:', e)
    }
  }

  const handleIngest = async () => {
    if (!struct || !grading) return

    setStatus('ingesting')
    try {
      const r = await ingest(struct, grading, caseFile.replace('.txt', ''))
      setStatus('ingested')
      setCurrentStep(4)
    } catch(e) {
      setStatus('ingest-failed')
      console.error('Ingest failed:', e)
    }
  }

  const getStatusDisplay = () => {
    switch (status) {
      case 'parsing':
        return <span className="status-indicator status-info">🔄 解析中...</span>
      case 'parsed':
        return <span className="status-indicator status-success">✅ 解析完成</span>
      case 'parse-failed':
        return <span className="status-indicator status-error">❌ 解析失败</span>
      case 'grading':
        return <span className="status-indicator status-info">🔄 分级中...</span>
      case 'graded':
        return <span className="status-indicator status-success">✅ 分级完成</span>
      case 'grade-failed':
        return <span className="status-indicator status-error">❌ 分级失败</span>
      case 'ingesting':
        return <span className="status-indicator status-info">🔄 存储中...</span>
      case 'ingested':
        return <span className="status-indicator status-success">✅ 存储完成</span>
      case 'ingest-failed':
        return <span className="status-indicator status-error">❌ 存储失败</span>
      default:
        return null
    }
  }

  if (!caseFile) {
    return (
      <div className="fade-in" style={{textAlign: 'center', padding: '60px 20px'}}>
        <div style={{fontSize: '64px', marginBottom: '24px'}}>🏥</div>
        <h2 style={{color: '#64748b', margin: '0 0 16px 0'}}>欢迎使用肝纤维化分级系统</h2>
        <p style={{color: '#94a3b8', fontSize: '16px', margin: 0}}>
          请从左侧选择一个病例文件进行分析
        </p>
      </div>
    )
  }

  return (
    <div className="fade-in">
      {/* 头部信息 */}
      <div className="content-header">
        <h1 className="content-title">{caseFile}</h1>
        <p className="content-subtitle">病理报告分析与纤维化分级</p>
        {getStatusDisplay()}
      </div>

      {/* 处理步骤进度条 */}
      <div style={{marginBottom: '24px'}}>
        <div style={{display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px'}}>
          {['📄 原始文本', '🔍 AI解析', '📊 智能分级', '💾 知识存储'].map((step, index) => (
            <div key={index} style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              color: index <= currentStep ? '#667eea' : '#cbd5e1',
              fontWeight: index <= currentStep ? '600' : '400',
              fontSize: '14px'
            }}>
              <span style={{
                width: '8px',
                height: '8px',
                borderRadius: '50%',
                backgroundColor: index <= currentStep ? '#667eea' : '#cbd5e1'
              }}></span>
              {step}
            </div>
          ))}
        </div>
        <div className="progress-bar">
          <div className="progress-fill" style={{width: `${(currentStep / 4) * 100}%`}}></div>
        </div>
      </div>

      {/* 操作按钮 */}
      <div style={{display: 'flex', gap: '12px', marginBottom: '24px', flexWrap: 'wrap'}}>
        <button
          onClick={handleParse}
          disabled={status === 'parsing' || currentStep < 1}
          className="btn btn-primary"
        >
          🤖 AI解析文本
        </button>

        <button
          onClick={handleGrade}
          disabled={status === 'grading' || currentStep < 2}
          className="btn btn-primary"
        >
          📊 智能分级
        </button>

        <button
          onClick={handleIngest}
          disabled={status === 'ingesting' || currentStep < 3}
          className="btn btn-success"
        >
          💾 存储到知识图谱
        </button>
      </div>

      {/* 内容区域 */}
      <div style={{display: 'grid', gap: '24px', gridTemplateColumns: currentStep >= 2 ? '1fr 1fr' : '1fr'}}>

        {/* 原始文本 */}
        <div className="card">
          <div className="card-header">
            📄 原始病理报告
          </div>
          <div className="card-body">
            <pre className="code-block code-block-raw">{raw}</pre>
          </div>
        </div>

        {/* AI标准化文本 */}
        {currentStep >= 2 && (
          <div className="card">
            <div className="card-header">
              🤖 AI标准化文本
            </div>
            <div className="card-body">
              <pre className="code-block code-block-normalized">
                {normalized || '暂无标准化结果'}
              </pre>
            </div>
          </div>
        )}

        {/* 分级结果 */}
        {currentStep >= 3 && grading && (
          <div className="card" style={{gridColumn: '1 / -1'}}>
            <div className="card-header">
              📊 纤维化分级结果
            </div>
            <div className="card-body">
              <div style={{display: 'grid', gap: '16px', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))'}}>
                <div style={{textAlign: 'center', padding: '20px', background: '#f8fafc', borderRadius: '8px'}}>
                  <div style={{fontSize: '48px', marginBottom: '8px'}}>
                    {grading.stage?.startsWith('F') ? '🏥' : '✅'}
                  </div>
                  <div style={{fontSize: '24px', fontWeight: 'bold', color: '#667eea'}}>
                    {grading.stage || '未知'}
                  </div>
                  <div style={{color: '#64748b', fontSize: '14px'}}>Ishak分级</div>
                </div>

                <div>
                  <h4 style={{margin: '0 0 12px 0', color: '#374151'}}>分级依据</h4>
                  <p style={{margin: 0, color: '#6b7280', fontSize: '14px'}}>
                    {grading.rule_reason || '暂无分级依据'}
                  </p>
                </div>

                {grading.llm_explanation && (
                  <div>
                    <h4 style={{margin: '0 0 12px 0', color: '#374151'}}>AI解释</h4>
                    <p style={{margin: 0, color: '#6b7280', fontSize: '14px'}}>
                      {grading.llm_explanation}
                    </p>
                  </div>
                )}
              </div>

              <details style={{marginTop: '16px'}}>
                <summary style={{cursor: 'pointer', fontWeight: '500', color: '#667eea'}}>
                  📋 完整技术详情
                </summary>
                <pre className="code-block code-block-json" style={{marginTop: '8px'}}>
                  {JSON.stringify(grading, null, 2)}
                </pre>
              </details>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
