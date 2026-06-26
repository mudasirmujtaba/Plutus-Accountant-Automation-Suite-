import { useLocation, useNavigate } from 'react-router-dom'
import { ArrowLeft, AlertCircle } from 'lucide-react'

export default function ErrorPage() {
  const location = useLocation()
  const navigate = useNavigate()
  const message  = location.state?.message || 'An unexpected error occurred.'

  return (
    <div className="space-y-4">
      <button
        onClick={() => navigate('/')}
        className="flex items-center gap-1.5 text-slate-400 hover:text-white text-sm transition-colors"
      >
        <ArrowLeft className="w-4 h-4" />
        Back
      </button>

      <div className="rounded-2xl border border-red-500/30 bg-red-500/10 p-8 text-center space-y-3">
        <div className="flex justify-center">
          <AlertCircle className="w-10 h-10 text-red-400" />
        </div>
        <p className="text-white font-semibold text-lg">Processing failed</p>
        <p className="text-red-300/70 text-sm max-w-md mx-auto">{message}</p>
        <button
          onClick={() => navigate('/')}
          className="mt-2 px-5 py-2 rounded-lg bg-slate-700 hover:bg-slate-600 text-white text-sm transition-colors"
        >
          Try again
        </button>
      </div>
    </div>
  )
}
