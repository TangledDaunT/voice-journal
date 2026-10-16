import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { fetchRuntime, microphoneApi } from '@/lib/api'
import { Card, CardContent } from '@/components/ui/card'
import { flatProfile, SoundGraph, soundRequest, type SoundProfile } from '@/lib/sound'

export function LiveMicrophone({profile}: {profile?: SoundProfile}) {
  const runtime = useQuery({ queryKey: ['runtime'], queryFn: fetchRuntime, refetchInterval: 2000 })
  const saved = useQuery({queryKey:['sound-profile'],queryFn:()=>soundRequest<SoundProfile>('settings')})
  const settings=profile || saved.data || flatProfile
  const [listening,setListening]=useState(false), [connecting,setConnecting]=useState(false), [message,setMessage]=useState('')
  const [source,setSource]=useState('hp'),[devices,setDevices]=useState<MediaDeviceInfo[]>([]),[device,setDevice]=useState(''),[level,setLevel]=useState(-100)
  const context=useRef<AudioContext|null>(null),graph=useRef<SoundGraph|null>(null),stream=useRef<MediaStream|null>(null)
  const controller=useRef<AbortController|null>(null),alive=useRef(false),generation=useRef(0),meterTimer=useRef<ReturnType<typeof setInterval>>()
  const stop=()=>{
    generation.current++;alive.current=false;controller.current?.abort();stream.current?.getTracks().forEach(track=>track.stop());stream.current=null
    clearInterval(meterTimer.current);void context.current?.close();context.current=null;graph.current=null;setListening(false);setConnecting(false);setLevel(-100);setMessage('Listening stopped')
    if(source==='hp')void microphoneApi.listen(false).catch(()=>{})
  }
  useEffect(()=>{graph.current?.apply(settings)},[settings])
  useEffect(()=>()=>{generation.current++;alive.current=false;controller.current?.abort();stream.current?.getTracks().forEach(track=>track.stop());clearInterval(meterTimer.current);void context.current?.close();void microphoneApi.listen(false).catch(()=>{})},[])
  const start=async()=>{
    const run=++generation.current
    try {
      setConnecting(true);setMessage(source==='hp'?'Connecting to HP…':'Allow microphone access in your browser and macOS Privacy & Security. Waiting for permission…')
      const audio=new AudioContext();context.current=audio;await audio.resume();const chain=new SoundGraph(audio,settings);graph.current=chain
      if(source==='local'){
        if(!navigator.mediaDevices?.getUserMedia)throw new Error('This computer’s microphone requires HTTPS and browser microphone permission.')
        let permissionTimer: ReturnType<typeof setTimeout> | undefined
        const request = navigator.mediaDevices.getUserMedia({audio:{deviceId:device?{exact:device}:undefined,echoCancellation:false,autoGainControl:false,noiseSuppression:false}}).then(local => {
          if(run!==generation.current){local.getTracks().forEach(track=>track.stop());throw new Error('Microphone request cancelled')}
          return local
        })
        const local = await Promise.race([request, new Promise<never>((_, reject) => {
          permissionTimer=setTimeout(()=>reject(new Error('Microphone permission is still pending. Allow access in your browser and macOS System Settings → Privacy & Security → Microphone, then try again.')),25000)
        })]).finally(()=>clearTimeout(permissionTimer))
        if(run!==generation.current){local.getTracks().forEach(track=>track.stop());return}
        stream.current=local;audio.createMediaStreamSource(local).connect(chain.input);setDevices((await navigator.mediaDevices.enumerateDevices()).filter(item=>item.kind==='audioinput'))
      }else await microphoneApi.listen(true)
      if(run!==generation.current)return
      alive.current=true;setListening(true);setConnecting(false)
      const samples=new Float32Array(chain.meter.fftSize)
      meterTimer.current=setInterval(()=>{chain.meter.getFloatTimeDomainData(samples);setLevel(20*Math.log10(Math.max(1e-5,Math.sqrt(samples.reduce((n,x)=>n+x*x,0)/samples.length))))},100)
      if(source==='local'){setMessage('Monitoring this computer locally. Audio stays in this browser.');return}
      controller.current=new AbortController();let sequence='0',next=audio.currentTime+.4,renewed=Date.now(),received=Date.now()
      while(alive.current && run===generation.current){
        if(Date.now()-renewed>2000){await microphoneApi.listen(true);renewed=Date.now()}
        const response=await microphoneApi.audio(sequence,controller.current.signal)
        if(response.status===200){
          const buffer=await audio.decodeAudioData(await response.arrayBuffer());if(!alive.current || run!==generation.current)break
          sequence=response.headers.get('X-Audio-Sequence') || '0';if(next<audio.currentTime || next>audio.currentTime+2)next=audio.currentTime+.35
          const block=audio.createBufferSource();block.buffer=buffer;block.connect(chain.input);block.start(next);next+=buffer.duration;received=Date.now();setMessage('Listening live from HP')
        }else if(response.status!==204)throw new Error('Live microphone unavailable. Check the external journal drive and HP microphone.')
        if(Date.now()-received>10000)throw new Error('No live audio received. Check the HP microphone and journal drive.')
        await new Promise(resolve=>setTimeout(resolve,60))
      }
    }catch(error){if(run===generation.current){stop();setMessage(error instanceof Error?error.message:'Listening failed')}}
  }
  const capture=runtime.data?.capture
  return <Card><CardContent className="space-y-4 p-5">
    <div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="font-semibold">Live microphone</h2><p className="mt-1 text-sm text-muted-foreground">{source==='hp'?capture?.selected_device || 'HP input status unavailable':'This computer · Mac or PC'}</p></div><button className="rounded-xl bg-primary px-4 py-2 text-sm text-primary-foreground disabled:opacity-50" disabled={!connecting && !listening && source==='hp' && (!capture?.fresh || !capture.stream_active || !!capture.device_error)} onClick={()=>listening || connecting?stop():void start()}>{connecting?'Cancel connection':listening?'Stop listening':'Listen live'}</button></div>
    <label className="block text-sm">Audio source<select aria-label="Audio source" className="ml-3 rounded-lg border border-border bg-background p-2" disabled={listening || connecting} value={source} onChange={e=>setSource(e.target.value)}><option value="hp">HP journal microphone</option><option value="local">This computer’s microphone (Mac / PC)</option></select></label>
    {source==='local' && devices.length>0 && <label className="block text-sm">Input device<select aria-label="Local input device" disabled={listening || connecting} value={device} onChange={e=>setDevice(e.target.value)} className="ml-3 max-w-full rounded-lg border bg-background p-2"><option value="">System default</option>{devices.map(item=><option key={item.deviceId} value={item.deviceId}>{item.label}</option>)}</select></label>}
    <div role="meter" aria-label="Monitor level" aria-valuemin={-100} aria-valuemax={0} aria-valuenow={Math.min(0,Math.round(level))} className="h-2 overflow-hidden rounded-full bg-muted/20"><div className={`h-full ${level>-3?'bg-destructive':'bg-accent'}`} style={{width:`${Math.min(100,Math.max(0,level+100))}%`}} /></div>
    <p className="text-xs text-muted-foreground">{listening?`${level.toFixed(0)} dBFS · `:''}Use headphones. HP listening works while journaling is muted. Mac monitoring stays local and does not create journal entries. <Link className="text-primary underline" to="/settings">Open microphone studio</Link></p>
    {(message || capture?.device_error || (source==='hp' && runtime.isError)) && <p role="status" className="text-sm">{message || capture?.device_error || 'HP service unavailable. Check the external journal drive; automatic recovery will reconnect it.'}</p>}
  </CardContent></Card>
}
