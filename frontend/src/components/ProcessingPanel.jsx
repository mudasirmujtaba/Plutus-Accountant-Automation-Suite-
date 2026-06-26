import { Upload, Cpu, FileText, CheckCircle, Loader2 } from 'lucide-react'

const STEPS = [
  { key: 'uploading',    label: 'Uploading file',        icon: Upload,      progress: 5  },
  { key: 'parsing',      label: 'Parsing transactions',  icon: FileText,    progress: 10 },
  { key: 'categorising', label: 'AI categorisation',     icon: Cpu,         progress: 40 },
  { key: 'writing',      label: 'Writing Excel file',    icon: FileText,    progress: 75 },
  { key: 'done',         label: 'Complete',              icon: CheckCircle, progress: 100 },
]

function stepIndex(step) {
  return STEPS.findIndex(s => s.key === step)
}

export default function ProcessingPanel({ job }) {
  if (!job) return null

  const currentIdx = stepIndex(job.step ?? 'uploading')
  const progress   = job.progress ?? 0

  return (
    <div className="rounded-2xl border border-slate-700 bg-slate-800/60 p-6 space-y-6">
      {/* File name */}
      <div className="flex items-center gap-3">
        <div className="w-9 h-9 rounded-lg bg-slate-700 flex items-center justify-center flex-shrink-0">
          <FileText className="w-4 h-4 text-slate-300" />
        </div>
        <div className="min-w-0">
          <p className="text-white font-medium text-sm truncate">{job.filename}</p>
          <p className="text-slate-400 text-xs">{job.message || 'Processing…'}</p>
        </div>
        <Loader2 className="w-4 h-4 text-indigo-400 animate-spin ml-auto flex-shrink-0" />
      </div>

      {/* Progress bar */}
      <div className="space-y-1.5">
        <div className="flex justify-between text-xs text-slate-500">
          <span>Progress</span>
          <span>{progress}%</span>
        </div>
        <div className="h-1.5 bg-slate-700 rounded-full overflow-hidden">
          <div
            className="h-full bg-indigo-500 rounded-full transition-all duration-700"
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>

      {/* Step list */}
      <div className="space-y-2">
        {STEPS.filter(s => s.key !== 'done').map((step, idx) => {
          const Icon = step.icon
          const done    = idx < currentIdx
          const active  = idx === currentIdx
          return (
            <div key={step.key} className={`flex items-center gap-3 px-3 py-2 rounded-lg transition-colors ${
              active  ? 'bg-indigo-500/10 border border-indigo-500/20' :
              done    ? 'opacity-50' : 'opacity-30'
            }`}>
              {done ? (
                <CheckCircle className="w-4 h-4 text-emerald-400 flex-shrink-0" />
              ) : active ? (
                <Loader2 className="w-4 h-4 text-indigo-400 animate-spin flex-shrink-0" />
              ) : (
                <Icon className="w-4 h-4 text-slate-500 flex-shrink-0" />
              )}
              <span className={`text-sm ${active ? 'text-indigo-300 font-medium' : done ? 'text-slate-400' : 'text-slate-600'}`}>
                {step.label}
              </span>
              {active && job.transaction_count && (
                <span className="ml-auto text-xs text-indigo-400/70">{job.transaction_count} txns</span>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
