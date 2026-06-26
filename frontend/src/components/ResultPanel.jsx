import { CheckCircle, Download, FileSpreadsheet, Tag } from 'lucide-react'
import axios from 'axios'

const CATEGORY_COLOURS = {
  'Lunch':            'bg-amber-500/10 text-amber-400 border-amber-500/20',
  'Travel':           'bg-blue-500/10  text-blue-400  border-blue-500/20',
  'Parking':          'bg-cyan-500/10  text-cyan-400  border-cyan-500/20',
  'Income':           'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  'Bank charges':     'bg-red-500/10   text-red-400   border-red-500/20',
  'Postage':          'bg-purple-500/10 text-purple-400 border-purple-500/20',
  'Directors salary': 'bg-indigo-500/10 text-indigo-400 border-indigo-500/20',
  'Mother Salary':    'bg-pink-500/10  text-pink-400  border-pink-500/20',
  'Sundry':           'bg-slate-500/10 text-slate-400 border-slate-500/20',
  'default':          'bg-slate-700/50 text-slate-300 border-slate-600',
}

function colourFor(cat) {
  return CATEGORY_COLOURS[cat] || CATEGORY_COLOURS['default']
}

export default function ResultPanel({ job }) {
  const handleDownload = async () => {
    const response = await axios.get(`/api/download/${job.job_id}`, { responseType: 'blob' })
    const blob = new Blob([response.data], {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = job.output_name || 'processed.xlsx'
    a.click()
    URL.revokeObjectURL(a.href)
  }

  return (
    <div className="rounded-2xl border border-emerald-500/30 bg-emerald-500/5 p-6 space-y-5">
      {/* Success header */}
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-full bg-emerald-500/20 flex items-center justify-center flex-shrink-0">
          <CheckCircle className="w-5 h-5 text-emerald-400" />
        </div>
        <div>
          <p className="text-white font-semibold">Processing complete</p>
          <p className="text-slate-400 text-sm">{job.message}</p>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-xl bg-slate-800/60 border border-slate-700 p-4 text-center">
          <p className="text-2xl font-bold text-white">{job.transaction_count ?? '—'}</p>
          <p className="text-slate-400 text-xs mt-0.5">Transactions</p>
        </div>
        <div className="rounded-xl bg-slate-800/60 border border-slate-700 p-4 text-center">
          <p className="text-2xl font-bold text-white">
            {job.top_categories ? Object.keys(job.top_categories).length : '—'}
          </p>
          <p className="text-slate-400 text-xs mt-0.5">Categories used</p>
        </div>
      </div>

      {/* Top categories */}
      {job.top_categories && Object.keys(job.top_categories).length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center gap-1.5 text-slate-400 text-xs font-medium">
            <Tag className="w-3 h-3" />
            <span>Top categories</span>
          </div>
          <div className="flex flex-wrap gap-2">
            {Object.entries(job.top_categories).map(([cat, count]) => (
              <span
                key={cat}
                className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-xs font-medium ${colourFor(cat)}`}
              >
                {cat}
                <span className="opacity-70">{count}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Output file name */}
      <div className="flex items-center gap-2 px-3 py-2.5 rounded-lg bg-slate-800/50 border border-slate-700">
        <FileSpreadsheet className="w-4 h-4 text-emerald-400 flex-shrink-0" />
        <span className="text-slate-300 text-sm truncate flex-1">{job.output_name}</span>
      </div>

      {/* Download button */}
      <button
        onClick={handleDownload}
        className="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-xl bg-indigo-500 hover:bg-indigo-400 text-white font-semibold text-sm transition-colors shadow-lg shadow-indigo-500/20"
      >
        <Download className="w-4 h-4" />
        Download Excel
      </button>
    </div>
  )
}
