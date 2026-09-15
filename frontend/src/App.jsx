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
  const [missingSkills, setMissingSkills] = useState([])
  const [selectedSkills, setSelectedSkills] = useState([])
  const [jobSkills, setJobSkills] = useState([])
  const [showSkillModal, setShowSkillModal] = useState(false)
  const [showEvaluation, setShowEvaluation] = useState(false)
  const [evaluationFeedback, setEvaluationFeedback] = useState('')

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

  const requestAnalysis = async () => {
    const response = await fetch('http://localhost:8000/api/analyze-resume', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ resume_url: form.resumeUrl, job_description: form.jobDescription }),
    })
    const data = await response.json()
    if (!response.ok) throw new Error(data.detail || 'Resume analysis failed')
    return data
  }

  const requestGeneration = async (addedSkills = [], feedback = '', hrFeedback = '') => {
    const formData = new FormData()
    formData.append('resume_url', form.resumeUrl)
    formData.append('job_description', form.jobDescription)
    formData.append('feedback', feedback || form.feedback)
    formData.append('hr_feedback', hrFeedback)
    formData.append('added_skills', JSON.stringify(addedSkills))
    formData.append('job_skills', JSON.stringify(jobSkills))
    formData.append('format_reference', form.formatReference)
    if (formatFileName) formData.append('format_file_name', formatFileName)
    if (selectedFormatFile) formData.append('format_file', selectedFormatFile)

    const response = await fetch('http://localhost:8000/api/generate-resume', {
      method: 'POST',
      body: formData,
    })
    const data = await response.json()
    if (!response.ok) throw new Error(data.detail || 'Something went wrong')
    setResult(data)
    setCopyStatus('idle')
    setShowEvaluation(true)
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
      const analysis = await requestAnalysis()
      setJobSkills(analysis.keywords || [])
      if (analysis.missing_keywords?.length) {
        setMissingSkills(analysis.missing_keywords)
        setSelectedSkills([])
        setShowSkillModal(true)
      } else {
        await requestGeneration()
      }
    } catch (err) {
      setError(err.message || 'Failed to generate resume.')
    } finally {
      setLoading(false)
    }
  }

  const handleSkillSave = async () => {
    setShowSkillModal(false)
    setLoading(true)
    setError('')
    try {
      await requestGeneration(selectedSkills)
    } catch (err) {
      setError(err.message || 'Failed to generate resume.')
    } finally {
      setLoading(false)
    }
  }

  const handleSkillToggle = (skill) => {
    setSelectedSkills((current) => (
      current.includes(skill)
        ? current.filter((item) => item !== skill)
        : [...current, skill]
    ))
  }

  const handleEvaluationIterate = async () => {
    setShowEvaluation(false)
    setLoading(true)
    setError('')
    try {
      await requestGeneration(
        selectedSkills,
        evaluationFeedback,
        result?.hr_evaluation ? JSON.stringify(result.hr_evaluation) : '',
      )
      setEvaluationFeedback('')
    } catch (err) {
      setError(err.message || 'Failed to iterate on the resume.')
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
    } catch {
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

      {showSkillModal && (
        <div className="modal-backdrop" role="presentation">
          <section className="modal" role="dialog" aria-modal="true" aria-labelledby="skills-title">
            <p className="eyebrow">Master resume check</p>
            <h2 id="skills-title">Missing skills found</h2>
            <p>These skills were found in the job description but not in your master resume. Keep only skills you genuinely have.</p>
            <div className="skill-list">
              {missingSkills.map((skill) => (
                <button
                  type="button"
                  className={`skill-tile ${selectedSkills.includes(skill) ? 'selected' : ''}`}
                  key={skill}
                  onClick={() => handleSkillToggle(skill)}
                >
                  {skill}
                </button>
              ))}
            </div>
            <div className="selected-skills-field">
              <span>Skills to emphasize</span>
              <div className="selected-skills-box">
                {selectedSkills.length === 0 && <span className="empty-selection">Click a skill above to add it here.</span>}
                {selectedSkills.map((skill) => (
                  <button
                    type="button"
                    className="selected-skill"
                    key={skill}
                    onClick={() => handleSkillToggle(skill)}
                    aria-label={`Remove ${skill}`}
                  >
                    {skill}<span aria-hidden="true">×</span>
                  </button>
                ))}
              </div>
            </div>
            <div className="modal-actions">
              <button type="button" className="quiet-button" onClick={() => setShowSkillModal(false)}>Exit</button>
              <button type="button" onClick={handleSkillSave} disabled={loading}>Save and continue</button>
            </div>
          </section>
        </div>
      )}

      {showEvaluation && result && (
        <div className="modal-backdrop" role="presentation">
          <section className="modal" role="dialog" aria-modal="true" aria-labelledby="evaluation-title">
            <p className="eyebrow">HR evaluation complete</p>
            <h2 id="evaluation-title">{result.hr_evaluation?.pass ? 'Would pass HR screening' : 'Needs improvement before HR screening'}</h2>
            <div className="evaluation-summary">
              <strong>Keyword match: {Math.round((result.match_score || 0) * 100)}%</strong>
              {result.hr_evaluation?.score != null && <strong>HR score: {result.hr_evaluation.score}/100</strong>}
            </div>
            {result.hr_evaluation?.verdict && <p>{result.hr_evaluation.verdict}</p>}
            {result.hr_evaluation?.low_lying_areas?.length > 0 && (
              <>
                <h3>Low-lying areas</h3>
                <ul className="evaluation-list">
                  {result.hr_evaluation.low_lying_areas.map((area) => <li key={area}>{area}</li>)}
                </ul>
              </>
            )}
            {result.hr_evaluation?.strengths?.length > 0 && (
              <>
                <h3>Strengths</h3>
                <ul className="evaluation-list">
                  {result.hr_evaluation.strengths.map((strength) => <li key={strength}>{strength}</li>)}
                </ul>
              </>
            )}
            <p>{result.missing_keywords?.length ? 'These keywords are still missing:' : 'All identified keywords are present.'}</p>
            {result.missing_keywords?.length > 0 && (
              <div className="skill-list">{result.missing_keywords.map((skill) => <span key={skill}>{skill}</span>)}</div>
            )}
            <label>
              Feedback for one more iteration
              <textarea value={evaluationFeedback} onChange={(event) => setEvaluationFeedback(event.target.value)} rows={4} placeholder="Tell the model what to improve..." />
            </label>
            <div className="modal-actions">
              <button type="button" className="quiet-button" onClick={() => setShowEvaluation(false)}>Finish</button>
              <button type="button" onClick={handleEvaluationIterate} disabled={loading}>Iterate once</button>
            </div>
          </section>
        </div>
      )}
    </div>
  )
}

export default App
