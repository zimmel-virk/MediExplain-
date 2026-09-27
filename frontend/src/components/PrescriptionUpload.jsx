import { useState } from 'react'
import { api } from '../api/client'

// This component handles prescription-image review in MediExplain+. It uploads
// the selected prescription to the backend OCR pipeline, shows the extracted text,
// OCR engine, confidence and any warning, and lets the user correct recognition
// errors before the structured medication fields are extracted again. Medication
// candidates returned from this step are not treated as confirmed prescriptions
// or automatically turned into schedules.

export default function PrescriptionUpload({ consultationId, onExtracted }) {
  const [file,setFile]=useState(null)
  const [result,setResult]=useState(null)
  const [text,setText]=useState('')
  const [busy,setBusy]=useState(false)
  const [err,setErr]=useState(null)


    // Send the selected prescription image to the backend OCR workflow and keep
  // both the raw recognised text and the structured extraction result available
  // for review in the interface.

  async function upload(){
    if(!file)return
    setBusy(true);setErr(null)
    try{
      const res=await api.uploadPrescription(consultationId,file)
      setResult(res);setText(res.text||'');onExtracted?.(res)
    }catch(e){setErr(e.message)}finally{setBusy(false)}
  }

    // Save the manually corrected OCR text and ask the backend to re-extract the
  // structured prescription fields from the corrected version rather than using
  // potentially inaccurate recognition output.
  
  async function saveCorrection(){
    if(!text.trim())return
    setBusy(true);setErr(null)
    try{
      const res=await api.correctPrescriptionOcr(consultationId,text)
      setResult(res);onExtracted?.(res)
    }catch(e){setErr(e.message)}finally{setBusy(false)}
  }
  return <div>
    <label className={`drop-zone ${file?'has-file':''}`} style={{display:'block'}}>
      <input type="file" accept="image/*,.heic,.heif" style={{display:'none'}}
        onChange={e=>{setFile(e.target.files?.[0]||null);setResult(null);setErr(null)}} />
      {file?<>📎 <strong>{file.name}</strong> ({(file.size/1024).toFixed(0)} KB)</>:
        <>📷 Choose a prescription photo</>}
    </label>
    <button style={{marginTop:10}} disabled={!file||busy} onClick={upload}>
      {busy?'Processing…':'Run OCR'}
    </button>
    {err?<div className="error">{err}</div>:null}
    {result?<div style={{marginTop:12}}>
      <div className="muted">
        OCR engine: <strong>{result.engine||'unavailable'}</strong> · confidence <strong>{Math.round((result.confidence||0)*100)}%</strong>
      </div>
      {result.warning?<div className="quality-warning">⚠ {result.warning}</div>:null}
      <label>Extracted text — correct OCR errors before using it</label>
      <textarea value={text} onChange={e=>setText(e.target.value)} style={{minHeight:120}} />
      <button className="secondary" disabled={busy||text===result.text} onClick={saveCorrection}>
        Save corrected OCR text & re-extract fields
      </button>
      {result.structured?.medications?.length?<div className="muted" style={{marginTop:8}}>
        {result.structured.medications.length} medication candidate(s) extracted. They are not automatically confirmed or scheduled.
      </div>:null}
    </div>:null}
  </div>
}
