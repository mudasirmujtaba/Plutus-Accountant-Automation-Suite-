import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import axios from 'axios'
import UploadZone from '../components/UploadZone'

export default function UploadPage() {
  const [uploading, setUploading] = useState(false)
  const [error, setError]         = useState(null)
  const navigate = useNavigate()

  const handleFile = async (file) => {
    setError(null)
    setUploading(true)

    const form = new FormData()
    form.append('file', file)

    try {
      const { data } = await axios.post('/api/upload', form)
      navigate(`/processing/${data.job_id}`, { state: { filename: file.name } })
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
          Upload a Barclays statement in CSV, PDF or XLSX format. Transactions
          are categorised automatically and appended to your Excel workbook.
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
        <UploadZone onFile={handleFile} />
      )}

      <div className="flex flex-wrap justify-center gap-2">
        {['UK FY labels (FY24, 24/25)', 'AI categorisation', 'Live Excel formulas',
          'Analysis pivot rebuild', 'CSV, PDF & XLSX support'].map(f => (
          <span key={f} className="px-3 py-1 rounded-full bg-slate-800 border border-slate-700 text-slate-400 text-xs">
            {f}
          </span>
        ))}
      </div>
    </div>
  )
}
