export interface SoundProfile { gain_db: number; output_db: number; highpass_hz: number; lowpass_hz: number; eq_db: number[]; compressor: boolean; threshold_db: number; ratio: number; attack_ms: number; release_ms: number; noise_reduction: number }
export const frequencies = [80, 160, 315, 630, 1250, 2500, 5000, 7000]
export const flatProfile: SoundProfile = {gain_db:0, output_db:0, highpass_hz:70, lowpass_hz:7400, eq_db:[0,0,0,0,0,0,0,0], compressor:false, threshold_db:-18, ratio:3, attack_ms:10, release_ms:150, noise_reduction:0}
export async function soundRequest<T>(path: string, values?: unknown): Promise<T> {
  const response = await fetch(`/api/microphone/${path}`, values === undefined ? undefined : {method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(values)})
  const body = await response.json()
  if (!response.ok) throw new Error(body.error || 'Microphone settings unavailable')
  return body
}
export class SoundGraph {
  input: GainNode; output: GainNode; high: BiquadFilterNode; low: BiquadFilterNode; bands: BiquadFilterNode[]; compressor: DynamicsCompressorNode; limiter: DynamicsCompressorNode; meter: AnalyserNode
  constructor(public context: AudioContext, settings: SoundProfile) {
    this.input=context.createGain();this.output=context.createGain();this.high=context.createBiquadFilter();this.high.type='highpass';this.low=context.createBiquadFilter();this.low.type='lowpass'
    this.bands=frequencies.map(hz=>{const band=context.createBiquadFilter();band.type='peaking';band.frequency.value=hz;band.Q.value=1.4;return band})
    this.compressor=context.createDynamicsCompressor();this.limiter=context.createDynamicsCompressor();this.limiter.threshold.value=-1;this.limiter.knee.value=0;this.limiter.ratio.value=20;this.limiter.attack.value=.001;this.limiter.release.value=.08
    this.meter=context.createAnalyser();this.meter.fftSize=1024
    const chain: AudioNode[]=[this.input,this.high,...this.bands,this.low,this.compressor,this.output,this.limiter,this.meter,context.destination]
    chain.slice(0,-1).forEach((node,i)=>node.connect(chain[i+1]));this.apply(settings)
  }
  apply(s: SoundProfile) {
    const set=(p: AudioParam,v:number)=>p.setTargetAtTime(v,this.context.currentTime,.025)
    set(this.input.gain,10**(s.gain_db/20));set(this.output.gain,10**(s.output_db/20));set(this.high.frequency,s.highpass_hz);set(this.low.frequency,s.lowpass_hz)
    this.bands.forEach((band,i)=>set(band.gain,s.eq_db[i]));set(this.compressor.threshold,s.compressor?s.threshold_db:0);set(this.compressor.ratio,s.compressor?s.ratio:1);set(this.compressor.attack,s.attack_ms/1000);set(this.compressor.release,s.release_ms/1000)
  }
}
