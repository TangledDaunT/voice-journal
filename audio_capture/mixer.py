"""Small ALSA control client: only the configured microphone's capture and boost."""
import ctypes as C
from audio_capture.alsa_guard import _alsa_library

CONTROLS={'capture_percent':'Capture Volume','boost_step':'Mic Boost Volume'}

def control(card,key,value=None):
    if not card or key not in CONTROLS:raise ValueError('Microphone control unavailable')
    lib=_alsa_library();p=C.c_void_p;ctl,info,item=p(),p(),p()
    signatures={
        'snd_ctl_elem_info_malloc':([C.POINTER(p)],C.c_int),
        'snd_ctl_elem_info_free':([p],None),
        'snd_ctl_elem_info_set_interface':([p,C.c_int],None),
        'snd_ctl_elem_info_set_name':([p,C.c_char_p],None),
        'snd_ctl_elem_info':([p,p],C.c_int),
        'snd_ctl_elem_info_get_type':([p],C.c_int),
        'snd_ctl_elem_info_get_count':([p],C.c_uint),
        'snd_ctl_elem_info_get_min':([p],C.c_long),
        'snd_ctl_elem_info_get_max':([p],C.c_long),
        'snd_ctl_elem_value_get_integer':([p,C.c_uint],C.c_long),
        'snd_ctl_elem_value_set_integer':([p,C.c_uint,C.c_long],None),
        'snd_ctl_elem_write':([p,p],C.c_int)}
    for name,(args,result) in signatures.items():
        fn=getattr(lib,name);fn.argtypes=args;fn.restype=result
    if lib.snd_ctl_open(C.byref(ctl),f'hw:{card}'.encode(),0)<0:raise OSError('Cannot open microphone mixer')
    try:
        if lib.snd_ctl_elem_info_malloc(C.byref(info))<0 or lib.snd_ctl_elem_value_malloc(C.byref(item))<0:raise OSError('Mixer allocation failed')
        name=CONTROLS[key].encode()
        lib.snd_ctl_elem_info_set_interface(info,2);lib.snd_ctl_elem_info_set_name(info,name)
        lib.snd_ctl_elem_value_set_interface(item,2);lib.snd_ctl_elem_value_set_name(item,name)
        if lib.snd_ctl_elem_info(ctl,info)<0 or lib.snd_ctl_elem_read(ctl,item)<0:raise OSError('Microphone control unavailable')
        if lib.snd_ctl_elem_info_get_type(info)!=2:raise OSError('Unsupported mixer control')
        low,high=lib.snd_ctl_elem_info_get_min(info),lib.snd_ctl_elem_info_get_max(info)
        count=lib.snd_ctl_elem_info_get_count(info)
        if not 1<=count<=32 or high<=low:raise OSError('Unsupported mixer range')
        if value is not None:
            maximum=100 if key=='capture_percent' else high
            minimum=0 if key=='capture_percent' else low
            if type(value) is not int or not minimum<=value<=maximum:raise ValueError('Hardware gain outside supported range')
            native=round(low+(high-low)*value/100) if key=='capture_percent' else value
            for index in range(count):lib.snd_ctl_elem_value_set_integer(item,index,native)
            if lib.snd_ctl_elem_write(ctl,item)<0:raise OSError('Cannot set microphone gain')
            if lib.snd_ctl_elem_read(ctl,item)<0:raise OSError('Cannot read microphone gain')
        native=lib.snd_ctl_elem_value_get_integer(item,0)
        return dict(value=round((native-low)*100/(high-low)) if key=='capture_percent' else native,min=0 if key=='capture_percent' else low,max=100 if key=='capture_percent' else high)
    finally:
        if info:lib.snd_ctl_elem_info_free(info)
        if item:lib.snd_ctl_elem_value_free(item)
        lib.snd_ctl_close(ctl)
