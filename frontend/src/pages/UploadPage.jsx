import { useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import axios from 'axios'
import { Upload, FileSpreadsheet, FileText, CheckCircle, X } from 'lucide-react'

function FilePicker({ label, accept, icon: Icon, iconColor, file, onFile, onClear, hint }) {
  const inputRef = useRef(null)
  const [dragging, setDragging] = useState(false)

  const handleDrop = (e) => {
    e.preventDefault()
    setDragging(false)
    const f = e.dataTransfer.files[0]
    if (f) onFile(f)
  }

  const handleChange = (e) => {
    const f = e.target.files[0]
    if (f) onFile(f)
    e.target.value = ''
  }

  if (file) {
    return (
      <div className="rounded-xl border border-emerald-500/40 bg-emerald-500/5 px-4 py-3 flex items-center gap-3">
        <CheckCircle className="w-5 h-5 text-emerald-400 flex-shrink-0" />
        <div className="flex-1 min-w-0">
          <p className="text-slate-300 text-sm font-medium truncate">{file.name}</p>
          <p className="text-slate-500 text-xs">{label}</p>
        </div>
        <button
          onClick={onClear}
          className="text-slate-500 hover:text-slate-300 flex-shrink-0 transition-colors"
        >
          <X className="w-4 h-4" />
        </button>
      </div>
    )
  }

  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      onClick={() => inputRef.current?.click()}
      className={`
        cursor-pointer rounded-xl border-2 border-dashed px-5 py-6 text-center transition-all duration-200
        ${dragging
          ? 'border-indigo-400 bg-indigo-500/10'
          : 'border-slate-600 bg-slate-800/50 hover:border-slate-500 hover:bg-slate-800'
        }
      `}
    >
      <input ref={inputRef} type="file" accept={accept} className="hidden" onChange={handleChange} />
      <div className="flex flex-col items-center gap-2">
        <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${dragging ? 'bg-indigo-500/20' : 'bg-slate-700'}`}>
          <Icon className={`w-5 h-5 ${dragging ? 'text-indigo-400' : iconColor}`} />
        </div>
        <div>
          <p className="text-slate-300 text-sm font-medium">{label}</p>
          {hint && <p className="text-slate-500 text-xs mt-0.5">{hint}</p>}
        </div>
        <p className="text-slate-500 text-xs">
          Drop here or <span className="text-indigo-400 underline underline-offset-2">browse</span>
        </p>
      </div>
    </div>
  )
}

export default function UploadPage() {
  const [statementFile, setStatementFile] = useState(null)
  const [templateFile, setTemplateFile]   = useState(null)
  const [uploading, setUploading]         = useState(false)
  const [error, setError]                 = useState(null)
  const navigate = useNavigate()

  const canProcess = statementFile && templateFile && !uploading

  const handleProcess = async () => {
    setError(null)
    setUploading(true)

    const form = new FormData()
    form.append('file', statementFile)
    form.append('template', templateFile)

    try {
      const { data } = await axios.post('/api/upload', form)
      navigate(`/processing/${data.job_id}`, { state: { filename: statementFile.name } })
    } catch (err) {
      setError(err.response?.data?.detail || err.message)
      setUploading(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="text-center">
        <h1 className="text-3xl font-bold text-white tracking-tight mb-2">
          Bank Statement Processor
        </h1>
        <p className="text-slate-400 text-base max-w-lg mx-auto">
          Upload your bank statement and Excel template workbook. Transactions are
          categorised automatically and appended to your workbook.
        </p>
      </div>

      {error && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-red-400 text-sm text-center">
          {error}
        </div>
      )}

      {uploading ? (
        <div className="rounded-2xl border border-slate-700 bg-slate-800/60 p-12 flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
          <p className="text-slate-400 text-sm">Uploading…</p>
        </div>
      ) : (
        <div className="space-y-3">
          <FilePicker
            label="Bank Statement"
            accept=".csv,.pdf,.xlsx"
            icon={FileText}
            iconColor="text-sky-400"
            file={statementFile}
            onFile={setStatementFile}
            onClear={() => setStatementFile(null)}
            hint="CSV, PDF or XLSX"
          />
          <FilePicker
            label="Excel Template Workbook"
            accept=".xlsx"
            icon={FileSpreadsheet}
            iconColor="text-emerald-400"
            file={templateFile}
            onFile={setTemplateFile}
            onClear={() => setTemplateFile(null)}
            hint="Your working papers XLSX file"
          />

          <button
            onClick={handleProcess}
            disabled={!canProcess}
            className={`
              w-full flex items-center justify-center gap-2 px-4 py-3 rounded-xl
              font-semibold text-sm transition-all duration-200
              ${canProcess
                ? 'bg-indigo-500 hover:bg-indigo-400 text-white shadow-lg shadow-indigo-500/20 cursor-pointer'
                : 'bg-slate-700 text-slate-500 cursor-not-allowed'
              }
            `}
          >
            <Upload className="w-4 h-4" />
            {canProcess ? 'Process Statement' : 'Select both files to continue'}
          </button>
        </div>
      )}

      <div className="flex flex-wrap justify-center gap-2">
        {['UK FY labels (FY24, 24/25)', 'AI categorisation', 'Live Excel formulas',
          'Analysis pivot rebuild', 'Any bank format'].map(f => (
          <span key={f} className="px-3 py-1 rounded-full bg-slate-800 border border-slate-700 text-slate-400 text-xs">
            {f}
          </span>
        ))}
      </div>
    </div>
  )
}
