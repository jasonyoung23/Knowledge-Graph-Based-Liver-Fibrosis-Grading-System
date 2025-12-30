import React, {useEffect, useState} from 'react'
import {listCases, uploadCase, deleteCase, batchProcess, clearDatabase} from '../services/api'

export default function CaseList({onSelect, selected}){
  const [cases, setCases] = useState([])
  const [uploading, setUploading] = useState(false)
  const [batchResults, setBatchResults] = useState(null)
  const [batchStatus, setBatchStatus] = useState('')
  const [dragOver, setDragOver] = useState(false)
  const [clearingDb, setClearingDb] = useState(false)
  const [uploadedFiles, setUploadedFiles] = useState([])
  const [uploadProgress, setUploadProgress] = useState(null) // {current, total, currentFile}

  const refreshCases = () => {
    listCases()
      .then(r => setCases(r.cases || []))
      .catch(e => {
        console.error(e)
        setCases([])
      })
  }

  // 不自动加载现有文件，让用户手动管理
  // useEffect(() => { refreshCases() }, [])

  const handleFileUpload = async (e) => {
    const files = Array.from(e.target.files || [])
    if (files.length === 0) return

    // 过滤出.txt文件
    const txtFiles = files.filter(file => file.name.endsWith('.txt'))

    if (txtFiles.length === 0) {
      alert('没有找到有效的 .txt 文件')
      return
    }

    if (txtFiles.length === 1) {
      // 单文件上传
      const file = txtFiles[0]
      setUploading(true)
      try {
        await uploadCase(file)
        // 添加到上传文件列表
        setUploadedFiles(prev => [...prev, file.name])
        e.target.value = ''
      } catch (err) {
        alert('上传失败: ' + err.message)
      }
      setUploading(false)
    } else {
      // 多文件批量上传
      await handleBatchFileUpload(txtFiles)
      e.target.value = ''
    }
  }

  const handleDelete = async (name) => {
    if (!confirm(`确定要从界面中移除病例 "${name}" 吗？`)) return
    try {
      await deleteCase(name)
      // 从上传文件列表中移除
      setUploadedFiles(prev => prev.filter(file => file !== name))
      if (selected === name) {
        onSelect(null)
      }
    } catch (err) {
      alert('移除失败: ' + err.message)
    }
  }

  const handleBatchProcess = async () => {
    if (uploadedFiles.length === 0) {
      alert('没有病例文件可以处理，请先上传文件')
      return
    }

    setBatchStatus('processing')
    setBatchResults(null)

    try {
      const r = await batchProcess(uploadedFiles)
      setBatchResults(r)
      setBatchStatus('completed')
    } catch (e) {
      setBatchStatus('failed')
      console.error('Batch process failed:', e)
      alert('批量处理失败: ' + e.message)
    }
  }

  const handleDeleteAll = async () => {
    if (uploadedFiles.length === 0) {
      alert('没有病例文件需要删除')
      return
    }

    if (!confirm(`确定要删除所有 ${uploadedFiles.length} 个病例文件吗？\n\n⚠️ 此操作不可撤销！`)) {
      return
    }

    try {
      // 删除所有病例文件
      for (const fileName of uploadedFiles) {
        await deleteCase(fileName)
      }
      setUploadedFiles([])

      // 如果当前选中的病例被删除了，清空选择
      if (selected && uploadedFiles.includes(selected)) {
        onSelect(null)
      }

      alert('所有病例文件已删除')
    } catch (err) {
      alert('批量删除失败: ' + err.message)
    }
  }

  const handleClearDatabase = async () => {
    if (!confirm(`确定要清空 Neo4j 数据库吗？\n\n⚠️ 此操作将删除所有存储的病例数据、分级结果和证据关系！\n\n此操作不可撤销！`)) {
      return
    }

    setClearingDb(true)
    try {
      await clearDatabase()
      alert('Neo4j 数据库已清空')
    } catch (err) {
      alert('清空数据库失败: ' + err.message)
    }
    setClearingDb(false)
  }

  const handleDragOver = (e) => {
    e.preventDefault()
    setDragOver(true)
  }

  const handleDragLeave = (e) => {
    e.preventDefault()
    setDragOver(false)
  }

  const handleDrop = (e) => {
    e.preventDefault()
    setDragOver(false)

    const files = Array.from(e.dataTransfer.files)
    const txtFiles = files.filter(file => file.name.endsWith('.txt'))

    if (txtFiles.length === 0) {
      alert('没有找到有效的 .txt 文件')
      return
    }

    if (txtFiles.length === 1) {
      // 单文件上传
      const fakeEvent = { target: { files: [txtFiles[0]] } }
      handleFileUpload(fakeEvent)
    } else {
      // 多文件批量上传
      handleBatchFileUpload(txtFiles)
    }
  }

  const handleBatchFileUpload = async (files) => {
    setUploading(true)
    setUploadProgress({ current: 0, total: files.length, currentFile: '' })

    const uploadedFilesList = []
    const failedFiles = []
    let errorMessage = ''

    try {
      for (let i = 0; i < files.length; i++) {
        const file = files[i]
        setUploadProgress({
          current: i + 1,
          total: files.length,
          currentFile: file.name
        })

        // 添加小延迟以避免并发问题
        if (i > 0) {
          await new Promise(resolve => setTimeout(resolve, 200))
        }

        const uploadFileWithRetry = async (file, maxRetries = 3) => {
          for (let attempt = 1; attempt <= maxRetries; attempt++) {
            try {
              const formData = new FormData()
              formData.append('file', file)

              console.log(`Uploading file: ${file.name}, size: ${file.size} bytes (attempt ${attempt}/${maxRetries})`)

              const controller = new AbortController()
              const timeoutId = setTimeout(() => controller.abort(), 30000) // 30秒超时

              const result = await fetch('/api/case/upload', {
                method: 'POST',
                body: formData,
                signal: controller.signal
              })

              clearTimeout(timeoutId)

              console.log(`Upload response for ${file.name}:`, result.status, result.statusText)

              if (!result.ok) {
                let errorText = 'Unknown error'
                try {
                  errorText = await result.text()
                } catch (e) {
                  console.warn('Could not read error response:', e)
                }

                // 如果是服务器错误且不是最后一次尝试，继续重试
                if (result.status >= 500 && attempt < maxRetries) {
                  console.warn(`Server error for ${file.name}, retrying... (${attempt}/${maxRetries})`)
                  await new Promise(resolve => setTimeout(resolve, 1000 * attempt)) // 递增延迟
                  continue
                }

                throw new Error(`HTTP ${result.status} ${result.statusText}: ${errorText}`)
              }

              const data = await result.json()
              console.log(`Upload successful for ${file.name}:`, data)
              return data

            } catch (error) {
              if (error.name === 'AbortError') {
                throw new Error('Upload timeout (30s)')
              }

              if (attempt === maxRetries) {
                throw error
              }

              console.warn(`Upload attempt ${attempt} failed for ${file.name}:`, error.message)
              await new Promise(resolve => setTimeout(resolve, 1000 * attempt))
            }
          }
        }

        try {
          await uploadFileWithRetry(file)
          uploadedFilesList.push(file.name)
        } catch (fileError) {
          const errorMsg = `${file.name}: ${fileError.message}`
          console.error('File upload failed after all retries:', errorMsg)
          failedFiles.push(errorMsg)
        }
      }

      // 更新成功上传的文件列表
      if (uploadedFilesList.length > 0) {
        setUploadedFiles(prev => [...prev, ...uploadedFilesList])
      }

      setUploadProgress(null)

      // 构建结果消息
      let message = ''
      if (uploadedFilesList.length > 0) {
        message += `成功上传 ${uploadedFilesList.length} 个文件`
      }
      if (failedFiles.length > 0) {
        message += `\n\n上传失败 ${failedFiles.length} 个文件:`
        failedFiles.forEach(error => {
          message += `\n• ${error}`
        })
      }

      alert(message)

    } catch (error) {
      errorMessage = error.message
      alert('批量上传过程中发生错误: ' + errorMessage)
      setUploadProgress(null)
    } finally {
      setUploading(false)
    }
  }

  const handleUploadClick = () => {
    // 触发隐藏的文件输入元素
    const input = document.querySelector('.upload-input')
    if (input) {
      input.click()
    }
  }

  const getStatusDisplay = () => {
    switch (batchStatus) {
      case 'processing':
        return <span className="status-indicator status-info">🔄 处理中...</span>
      case 'completed':
        return <span className="status-indicator status-success">✅ 处理完成</span>
      case 'failed':
        return <span className="status-indicator status-error">❌ 处理失败</span>
      default:
        return null
    }
  }

  return (
    <div className="fade-in">
      {/* 文件上传区域 */}
      <div
        className={`upload-area ${dragOver ? 'dragover' : ''}`}
        onClick={handleUploadClick}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        style={{cursor: uploading ? 'not-allowed' : 'pointer'}}
      >
        <span className="upload-icon">📤</span>
        <p className="upload-text">
          {uploading ? (uploadProgress ? `上传中... (${uploadProgress.current}/${uploadProgress.total})` : '上传中...') : '拖拽或点击上传病例文件'}
        </p>
        {uploadProgress && (
          <div className="upload-progress">
            <div className="progress-bar">
              <div
                className="progress-fill"
                style={{width: `${(uploadProgress.current / uploadProgress.total) * 100}%`}}
              ></div>
            </div>
            <p className="progress-text">{uploadProgress.currentFile}</p>
          </div>
        )}
        <p className="upload-subtext">支持 .txt 格式的病理报告（可多选）</p>
        <input
          type="file"
          accept=".txt"
          multiple
          onChange={handleFileUpload}
          disabled={uploading}
          className="upload-input"
        />
      </div>


      {/* 操作按钮组 */}
      <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '16px'}}>
        <button
          onClick={handleBatchProcess}
          disabled={batchStatus === 'processing' || uploadedFiles.length === 0}
          className={`btn btn-success ${batchStatus === 'processing' ? 'loading' : ''}`}
        >
          {batchStatus === 'processing' ? (
            <>
              <span className="loading-spinner"></span>
              处理中...
            </>
          ) : (
            <>🚀 批量处理所有病例</>
          )}
        </button>

        <button
          onClick={handleDeleteAll}
          disabled={uploadedFiles.length === 0}
          className="btn btn-danger"
          title="删除所有病例文件（不可恢复）"
        >
          🗑️ 删除所有病例
        </button>

        <button
          onClick={handleClearDatabase}
          disabled={clearingDb}
          className={`btn ${clearingDb ? 'btn-secondary' : 'btn-danger'}`}
          style={{gridColumn: 'span 2'}}
          title="清空 Neo4j 数据库中的所有数据"
        >
          {clearingDb ? (
            <>
              <span className="loading-spinner"></span>
              清空中...
            </>
          ) : (
            <>💥 清空 Neo4j 数据库</>
          )}
        </button>
      </div>

      {/* 状态显示 */}
      {getStatusDisplay()}

      {/* 批量处理结果 */}
      {batchResults && (
        <div className="card" style={{marginTop: '16px'}}>
          <div className="card-header">
            📊 处理结果
          </div>
          <div className="card-body">
            <div style={{marginBottom: '12px', fontSize: '14px', color: '#64748b'}}>
              总计: {batchResults.total} 个病例 | 成功: {batchResults.processed} 个
            </div>
            <div style={{maxHeight: '200px', overflowY: 'auto', fontSize: '12px'}}>
              {batchResults.results.map((result, index) => (
                <div key={index} style={{
                  padding: '4px 8px',
                  marginBottom: '4px',
                  borderRadius: '4px',
                  backgroundColor: result.status === 'success' ? '#f0fdf4' : '#fef2f2',
                  border: `1px solid ${result.status === 'success' ? '#bbf7d0' : '#fecaca'}`,
                  color: result.status === 'success' ? '#166534' : '#991b1b'
                }}>
                  <div style={{fontWeight: '500'}}>
                    {result.file}
                    {result.grade && <span style={{marginLeft: '8px'}}>({result.grade})</span>}
                  </div>
                  {result.error && (
                    <div style={{fontSize: '11px', marginTop: '2px'}}>
                      {result.error}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* 已上传的病例列表 */}
      {uploadedFiles.length > 0 && (
        <div className="card" style={{marginTop: '20px'}}>
          <div className="card-header">
            📁 已上传病例 ({uploadedFiles.length})
          </div>
          <div className="card-body" style={{padding: '0'}}>
            {uploadedFiles.map(fileName => (
              <div
                key={fileName}
                className={`case-item ${selected === fileName ? 'selected' : ''}`}
                onClick={() => onSelect(fileName)}
              >
                <span className="case-item-name">{fileName}</span>
                <div className="case-item-actions">
                  <button
                    className="case-delete-btn"
                    onClick={(e) => {
                      e.stopPropagation()
                      handleDelete(fileName)
                    }}
                    title="从界面中移除"
                  >
                    ❌
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
