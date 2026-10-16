"""Validated monitor/enhancement settings; raw capture and speaker gating stay untouched."""
import math
from pathlib import Path
import json
from utils.data_lock import write_json

FREQUENCIES = [80, 160, 315, 630, 1250, 2500, 5000, 7000]
DEFAULTS = dict(gain_db=0, output_db=0, highpass_hz=70, lowpass_hz=7400,
                eq_db=[0]*8, compressor=False, threshold_db=-18, ratio=3,
                attack_ms=10, release_ms=150, noise_reduction=0)
LIMITS = dict(gain_db=(-24,24), output_db=(-24,6), highpass_hz=(20,400),
              lowpass_hz=(2000,7900), threshold_db=(-60,-1), ratio=(1,12),
              attack_ms=(1,100), release_ms=(20,1000), noise_reduction=(0,12))

def validate(values):
    if not isinstance(values,dict) or set(values)-set(DEFAULTS):
        raise ValueError('Unknown sound setting')
    result = dict(DEFAULTS, **values)
    for key,(low,high) in LIMITS.items():
        v=result[key]
        if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not low<=v<=high:
            raise ValueError(f'{key} must be between {low} and {high}')
    if type(result['compressor']) is not bool:
        raise ValueError('compressor must be true or false')
    eq=result['eq_db']
    if not isinstance(eq,list) or len(eq)!=8 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not -12<=v<=12 for v in eq):
        raise ValueError('Use eight EQ gains between -12 and +12 dB')
    return result

def path(config):
    return Path(config.database.path).parent.parent/'settings/microphone.json'

def load(config):
    try:return validate(json.loads(path(config).read_text()))
    except (OSError,ValueError):return validate({})

def save(config, values):
    result=validate(values);write_json(path(config),result);return result

def filters(config):
    s=load(config)
    parts=[f"volume={s['gain_db']}dB",f"highpass=f={s['highpass_hz']}",f"lowpass=f={s['lowpass_hz']}"]
    parts += [f'equalizer=f={hz}:t=o:w=1:g={gain}' for hz,gain in zip(FREQUENCIES,s['eq_db']) if gain]
    if s['noise_reduction']:parts.append(f"afftdn=nr={s['noise_reduction']}:nf=-45")
    if s['compressor']:
        parts.append(f"acompressor=threshold={10**(s['threshold_db']/20)}:ratio={s['ratio']}:attack={s['attack_ms']}:release={s['release_ms']}:makeup=1")
    parts += [f"volume={s['output_db']}dB",'alimiter=limit=0.89:level=false:latency=true']
    return ','.join(parts)
