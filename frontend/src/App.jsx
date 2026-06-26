import { BrowserRouter, Routes, Route } from 'react-router-dom'
import UploadPage     from './pages/UploadPage'
import ProcessingPage from './pages/ProcessingPage'
import ResultPage     from './pages/ResultPage'
import ErrorPage      from './pages/ErrorPage'
import './index.css'

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-800 flex flex-col">

        {/* Header */}
        <header className="border-b border-slate-700/50 bg-slate-900/80 backdrop-blur sticky top-0 z-10">
          <div className="max-w-5xl mx-auto px-6 py-4 flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-indigo-500 flex items-center justify-center text-white font-bold text-sm">
              P
            </div>
            <span className="text-white font-semibold text-lg tracking-tight">Plutus</span>
            <span className="text-slate-500 text-sm font-medium ml-1">Accountant Suite</span>
            <div className="ml-auto">
              <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs font-medium">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                Milestone 1 Live
              </span>
            </div>
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 flex flex-col items-center justify-center px-6 py-12">
          <div className="w-full max-w-2xl">
            <Routes>
              <Route path="/"                    element={<UploadPage />} />
              <Route path="/processing/:jobId"   element={<ProcessingPage />} />
              <Route path="/result/:jobId"       element={<ResultPage />} />
              <Route path="/error"               element={<ErrorPage />} />
            </Routes>
          </div>
        </main>

        {/* Footer */}
        <footer className="text-center text-slate-600 text-xs py-4 border-t border-slate-800">
          Plutus Accountant Automation Suite · Milestone 1
        </footer>

      </div>
    </BrowserRouter>
  )
}
