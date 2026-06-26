import { useLocation, useNavigate } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import ResultPanel from '../components/ResultPanel'

export default function ResultPage() {
  const location = useLocation()
  const navigate = useNavigate()
  const { job, filename } = location.state || {}

  if (!job) {
    navigate('/')
    return null
  }

  return (
    <div className="space-y-4">
      <button
        onClick={() => navigate('/')}
        className="flex items-center gap-1.5 text-slate-400 hover:text-white text-sm transition-colors"
      >
        <ArrowLeft className="w-4 h-4" />
        Process another statement
      </button>

      <div>
        <h2 className="text-xl font-semibold text-white">Done</h2>
        <p className="text-slate-400 text-sm truncate">{filename}</p>
      </div>

      <ResultPanel job={job} apiBase="" onReset={() => navigate('/')} />
    </div>
  )
}
