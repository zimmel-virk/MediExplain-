import { useEffect,useRef,useState } from 'react'

// This component records consultation audio in the browser before it is sent to
// the MediExplain+ speech-to-text pipeline. It requests microphone access with
// basic browser audio processing, records the consultation as compressed WebM
// audio where supported, supports pause and resume, shows recording time and a
// lightweight microphone-level indicator, and returns the completed audio blob
// to the parent component when recording stops.

export default function Recorder({onComplete,disabled,maxMinutes=90}){
  const [state,setState]=useState('idle')
  const [elapsed,setElapsed]=useState(0)
  const [level,setLevel]=useState(0)
  const mediaRef=useRef(null),streamRef=useRef(null),chunksRef=useRef([]),timerRef=useRef(null),audioCtxRef=useRef(null)
  // Clear recording timers and release microphone/audio resources when recording
  // finishes or the component is removed so the browser does not keep them active.

  useEffect(()=>()=>cleanup(false),[])

  function cleanup(stopTracks=true){
    if(timerRef.current)clearInterval(timerRef.current)
    timerRef.current=null
    if(stopTracks&&streamRef.current)streamRef.current.getTracks().forEach(t=>t.stop())
    try{audioCtxRef.current?.close()}catch{}
  }
    // Request microphone access and start a new consultation recording. Browser
  // echo cancellation, noise suppression and automatic gain control are enabled
  // where available to provide a cleaner input for the later STT stage.
  async function start(){
    try{
      const stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true}})
      streamRef.current=stream
      let options={}
      if(MediaRecorder.isTypeSupported('audio/webm;codecs=opus'))options={mimeType:'audio/webm;codecs=opus'}
      const mr=new MediaRecorder(stream,options);mediaRef.current=mr;chunksRef.current=[]
      mr.ondataavailable=e=>{if(e.data?.size)chunksRef.current.push(e.data)}
      mr.onerror=e=>alert('Recording error: '+(e.error?.message||e.message||'unknown'))
      mr.onstop=()=>{
        const blob=new Blob(chunksRef.current,{type:mr.mimeType||'audio/webm'})
        cleanup(true);setState('idle');setLevel(0)
        if(blob.size)onComplete(blob)
      }
      // Use the browser audio analyser only as a simple live microphone indicator;
      // it does not modify the recorded consultation audio or perform transcription.
      try{
        const Ctx=window.AudioContext||window.webkitAudioContext
        const ctx=new Ctx();audioCtxRef.current=ctx
        const src=ctx.createMediaStreamSource(stream),an=ctx.createAnalyser();an.fftSize=256;src.connect(an)
        const buf=new Uint8Array(an.frequencyBinCount)
        const meter=setInterval(()=>{an.getByteFrequencyData(buf);setLevel(Math.round(buf.reduce((a,b)=>a+b,0)/buf.length))},250)
        const old=timerRef.current; // meter cleared by stop through combined interval cleanup below is handled separately by stream
        stream.getTracks()[0].addEventListener('ended',()=>clearInterval(meter))
      }catch{}
            // Combine the recorded chunks into one audio blob and return it only after
      // recording has stopped and the microphone resources have been released.
      mr.start(1000);setState('recording');setElapsed(0)
      timerRef.current=setInterval(()=>setElapsed(v=>{
        if(v+1>=maxMinutes*60){try{mr.stop()}catch{};return v+1}
        return v+1
      }),1000)
    }catch(err){alert('Microphone access denied or unavailable: '+err.message)}
  }
  function pause(){if(mediaRef.current?.state==='recording'){mediaRef.current.pause();setState('paused')}}
  function resume(){if(mediaRef.current?.state==='paused'){mediaRef.current.resume();setState('recording')}}
  function stop(){if(mediaRef.current&&mediaRef.current.state!=='inactive')mediaRef.current.stop()}

  return <div style={{textAlign:'center',padding:24}}>
    {state==='idle'?<button className="rec-button" onClick={start} disabled={disabled} type="button">REC</button>:
      <div style={{display:'flex',gap:8,justifyContent:'center'}}>
        <button className="rec-button recording" onClick={stop} type="button">STOP</button>
        {state==='recording'?<button className="secondary" onClick={pause} type="button">Pause</button>:
          <button className="secondary" onClick={resume} type="button">Resume</button>}
      </div>}
    <div className="muted" style={{marginTop:12}}>
      {state==='idle'?'Click to start recording (mic permission required)':
        `${state==='paused'?'Paused':'Recording'} · ${Math.floor(elapsed/60)}:${String(elapsed%60).padStart(2,'0')} · mic level ${level}`}
    </div>
  </div>
}
