import { useState } from 'react'
import './App.css'

const initialForm = {
  resumeUrl: 'https://drive.google.com/file/d/1-ZB4-SN3h2Wp3CTRNyHjTn0iWwZupZ1E/view?usp=sharing',
  formatReference: '',
  jobDescription: 'Looking for a Python engineer with FastAPI, PostgreSQL, AWS, and 3+ years of backend experience.',
  feedback: '',
}

function App() {
  const [form, setForm] = useState(initialForm)
  const [loading, setLoading] = useState(false)
  const [validating, setValidating] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [validation, setValidation] = useState(null)
  const [copyStatus, setCopyStatus] = useState('idle')
  const [formatFileName, setFormatFileName] = useState('')
  const [selectedFormatFile, setSelectedFormatFile] = useState(null)

  const handleChange = (event) => {
    const { name, value } = event.target
    setForm((prev) => ({ ...prev, [name]: value }))
  }

  const handleValidateUrl = async () => {
    if (!form.resumeUrl.trim()) {
      setValidation({ valid: false, message: 'Please enter a Google Drive URL first.' })
      return
    }

    setValidating(true)
    setError('')
    setValidation(null)

    try {
      const response = await fetch('http://localhost:8000/api/validate-drive-url', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ resume_url: form.resumeUrl }),
      })

      const data = await response.json()
      if (!response.ok) {
        throw new Error(data.detail || 'URL validation failed')
      }

      setValidation({ valid: true, message: data.message || 'Google Drive URL is valid.' })
    } catch (err) {
      setValidation({ valid: false, message: err.message || 'This link is not working.' })
    } finally {
      setValidating(false)
    }
  }

  const handleFormatFileChange = (event) => {
    const file = event.target.files?.[0]
    if (!file) {
      setSelectedFormatFile(null)
      setFormatFileName('')
      return
    }

    setSelectedFormatFile(file)
    setFormatFileName(file.name)
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    setLoading(true)
    setError('')

    if (!validation || !validation.valid) {
      setError('Please validate the Google Drive URL before generating the resume.')
      setLoading(false)
      return
    }

    try {
      const formData = new FormData()
      formData.append('resume_url', form.resumeUrl)
      formData.append('job_description', form.jobDescription)
      formData.append('feedback', form.feedback)
      formData.append('format_reference', form.formatReference)
      if (formatFileName) {
        formData.append('format_file_name', formatFileName)
      }
      if (selectedFormatFile) {
        formData.append('format_file', selectedFormatFile)
      }

      const response = await fetch('http://localhost:8000/api/generate-resume', {
        method: 'POST',
        body: formData,
      })

      const data = await response.json()
      if (!response.ok) {
        throw new Error(data.detail || 'Something went wrong')
      }

      setResult(data)
      setCopyStatus('idle')
    } catch (err) {
      setError(err.message || 'Failed to generate resume.')
    } finally {
      setLoading(false)
    }
  }

  const handleCopyResume = async () => {
    if (!result?.generated_resume) return

    try {
      await navigator.clipboard.writeText(result.generated_resume)
      setCopyStatus('copied')
      window.setTimeout(() => setCopyStatus('idle'), 1500)
    } catch (err) {
      setCopyStatus('failed')
      window.setTimeout(() => setCopyStatus('idle'), 1500)
    }
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <h1>Resume Tailor</h1>
      </header>

      <main className="layout">
        <form className="panel form-panel" onSubmit={handleSubmit}>
          <label className="url-label">
            <span>Resume Google Drive URL</span>
            <div className="url-row">
              <input
                name="resumeUrl"
                value={form.resumeUrl}
                onChange={handleChange}
                placeholder="https://drive.google.com/..."
              />
              <button
                type="button"
                className="secondary-button"
                onClick={handleValidateUrl}
                disabled={validating}
              >
                {validating ? 'Checking...' : 'Check URL'}
              </button>
            </div>
          </label>

          {validation && (
            <p className={validation.valid ? 'success' : 'error'}>
              {validation.message}
            </p>
          )}

          <label className="format-label">
            <span>Format reference</span>
            <textarea
              name="formatReference"
              value={form.formatReference}
              onChange={handleChange}
              rows={4}
              placeholder="Paste a LaTeX snippet, DOC/PDF link, or image reference here."
            />
            <div className="format-upload-row">
              <input
                type="file"
                accept=".tex,.doc,.docx,.pdf,image/*"
                onChange={handleFormatFileChange}
              />
              {formatFileName && <span className="file-name">Selected: {formatFileName}</span>}
            </div>
          </label>

          <label>
            Job description
            <textarea
              name="jobDescription"
              value={form.jobDescription}
              onChange={handleChange}
              rows={10}
            />
          </label>

          <label>
            Feedback
            <textarea
              name="feedback"
              value={form.feedback}
              onChange={handleChange}
              rows={4}
              placeholder="Optional revisions"
            />
          </label>

          <button
            type="submit"
            disabled={loading || !validation || !validation.valid}
            className={validation?.valid ? 'submit-success' : 'submit-disabled'}
          >
            {loading ? 'Generating...' : 'Generate resume'}
          </button>

          {error && <p className="error">{error}</p>}
        </form>

        <div className="panel output-panel">
          <div className="output-header">
            <h2>Output</h2>
            {result?.generated_resume && (
              <button type="button" className="copy-button" onClick={handleCopyResume}>
                {copyStatus === 'copied' ? 'Copied!' : 'Copy'}
              </button>
            )}
          </div>

          {!result ? (
            <p>Submit a resume URL and JD to generate output.</p>
          ) : (
            <>
              <div className="metrics">
                <span>Match score: {result.match_score}</span>
                <span>Missing: {result.missing_keywords?.length || 0}</span>
              </div>

              <pre>{result.generated_resume}</pre>
            </>
          )}
        </div>
      </main>
    </div>
  )
}

export default App
