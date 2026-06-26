import { useEffect, useRef, useState } from 'react'
import { useParams, useLocation, useNavigate } from 'react-router-dom'
import axios from 'axios'
import { ArrowLeft } from 'lucide-react'
import ProcessingPanel from '../components/ProcessingPanel'

const POLL_INTERVAL = 1500

export default function ProcessingPage() {
  const { jobId }  = useParams()
  const location   = useLocation()
  const navigate   = useNavigate()
  const filename   = location.state?.filename || 'Statement'
  const pollRef    = useRef(null)

  const [job, setJob] = useState({
    filename,
    progress: 5,
    step: 'parsing',
    message: 'Parsing bank statement…',
    status: 'processing',
  })

  useEffect(() => {
    pollRef.current = setInterval(async () => {
      try {
        const { data } = await axios.get(`/api/progress/${jobId}`)
        setJob(prev => ({ ...prev, ...data }))

        if (data.status === 'done') {
          clearInterval(pollRef.current)
          navigate(`/result/${jobId}`, {
            state: { job: { ...data, job_id: jobId }, filename },
          })
        } else if (data.status === 'error') {
          clearInterval(pollRef.current)
          navigate('/error', { state: { message: data.message } })
        }
      } catch {
        // network blip – keep polling
      }
    }, POLL_INTERVAL)

    return () => clearInterval(pollRef.current)
  }, [jobId])

  const handleBack = () => {
    clearInterval(pollRef.current)
    navigate('/')
  }

  return (
    <div className="space-y-4">
      <button
        onClick={handleBack}
        className="flex items-center gap-1.5 text-slate-400 hover:text-white text-sm transition-colors"
      >
        <ArrowLeft className="w-4 h-4" />
        Back
      </button>

      <div>
        <h2 className="text-xl font-semibold text-white">Processing</h2>
        <p className="text-slate-400 text-sm truncate">{filename}</p>
      </div>

      <ProcessingPanel job={job} />
    </div>
  )
}
