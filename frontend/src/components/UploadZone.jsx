import { useState, useRef } from 'react'
import { Upload, FileText, FileSpreadsheet } from 'lucide-react'

export default function UploadZone({ onFile }) {
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef(null)

  const validate = (file) => {
    const ext = file.name.split('.').pop().toLowerCase()
    if (!['csv', 'pdf', 'xlsx'].includes(ext)) {
      alert('Please upload a CSV, PDF or XLSX file.')
      return false
    }
    return true
  }

  const handleDrop = (e) => {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files[0]
    if (file && validate(file)) onFile(file)
  }

  const handleChange = (e) => {
    const file = e.target.files[0]
    if (file && validate(file)) onFile(file)
  }

  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      onClick={() => inputRef.current?.click()}
      className={`
        relative cursor-pointer rounded-2xl border-2 border-dashed p-12 text-center transition-all duration-200
        ${dragging
          ? 'border-indigo-400 bg-indigo-500/10 scale-[1.01]'
          : 'border-slate-600 bg-slate-800/50 hover:border-indigo-500/60 hover:bg-slate-800'
        }
      `}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".csv,.pdf,.xlsx"
        className="hidden"
        onChange={handleChange}
      />

      <div className="flex flex-col items-center gap-4">
        <div className={`w-16 h-16 rounded-2xl flex items-center justify-center transition-colors ${dragging ? 'bg-indigo-500/20' : 'bg-slate-700'}`}>
          <Upload className={`w-7 h-7 transition-colors ${dragging ? 'text-indigo-400' : 'text-slate-400'}`} />
        </div>

        <div>
          <p className="text-white font-semibold text-lg mb-1">
            {dragging ? 'Drop to upload' : 'Drop your statement here'}
          </p>
          <p className="text-slate-400 text-sm">
            or <span className="text-indigo-400 underline underline-offset-2">browse files</span>
          </p>
        </div>

        {/* Accepted formats */}
        <div className="flex gap-2 mt-2 flex-wrap justify-center">
          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-700/60 border border-slate-600">
            <FileSpreadsheet className="w-3.5 h-3.5 text-emerald-400" />
            <span className="text-xs text-slate-300 font-medium">CSV</span>
          </div>
          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-700/60 border border-slate-600">
            <FileText className="w-3.5 h-3.5 text-red-400" />
            <span className="text-xs text-slate-300 font-medium">PDF</span>
          </div>
          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-700/60 border border-slate-600">
            <FileSpreadsheet className="w-3.5 h-3.5 text-indigo-400" />
            <span className="text-xs text-slate-300 font-medium">XLSX</span>
          </div>
        </div>

        <p className="text-slate-600 text-xs">Barclays bank statements only · Your data never leaves this machine</p>
      </div>
    </div>
  )
}
