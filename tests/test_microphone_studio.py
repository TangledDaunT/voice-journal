import io
import wave
import subprocess
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
from flask import Flask
from audio_capture.sound_profile import load,save,validate,filters,DEFAULTS
from web.microphone_api import register_microphone_api

@pytest.mark.parametrize('values',[
 {'gain_db':float('nan')},{'output_db':50},{'eq_db':[0]*7},{'eq_db':[float('inf')]*8},
 {'compressor':'yes'},{'attack_ms':0},{'noise_reduction':-1},{'filter':'shell command'},
 {'gain_db':True},None,
])
def test_sound_settings_reject_invalid_input(values):
    with pytest.raises(ValueError):validate(values)


def test_settings_round_trip_and_filter_processes_without_changing_timing(test_config,tmp_path):
    profile=save(test_config,dict(DEFAULTS,compressor=True,eq_db=[-2,0,1,0,2,3,0,0],noise_reduction=6))
    assert load(test_config)==profile
    tone=(np.sin(np.arange(16000)*2*np.pi*440/16000)*.1*32767).astype('<i2')
    result=subprocess.run(['ffmpeg','-v','error','-f','s16le','-ar','16000','-ac','1','-i','pipe:0','-af',filters(test_config),'-f','s16le','pipe:1'],input=tone.tobytes(),capture_output=True,check=True)
    assert len(result.stdout)==len(tone)*2
    assert np.max(np.abs(np.frombuffer(result.stdout,'<i2').astype(float)))<=32767


def test_authenticated_app_routes_validate_hardware_before_any_write(test_config,monkeypatch):
    import audio_capture.mixer as mixer
    calls=[]
    def control(card,key,value=None):
        if value is not None:calls.append((key,value))
        return dict(min=0,max=100 if key=='capture_percent' else 3,value=50 if key=='capture_percent' else 1)
    monkeypatch.setattr(mixer,'control',control)
    monkeypatch.setattr('web.microphone_api.require_external_storage',lambda _:None)
    app=Flask(__name__);register_microphone_api(app,test_config);client=app.test_client()
    assert client.get('/api/microphone/settings').json==validate({})
    assert client.put('/api/microphone/settings',json={'gain_db':6}).status_code==200
    assert client.get('/api/microphone/settings').json['gain_db']==6
    assert client.put('/api/microphone/hardware',json={'capture_percent':70,'boost_step':99}).status_code==400
    assert not calls
    assert client.put('/api/microphone/hardware',json={'capture_percent':70,'boost_step':1}).status_code==200
    assert sorted(calls)==[('boost_step',1),('capture_percent',70)]
    assert client.put('/api/microphone/hardware',json={'device':'other'}).status_code==400


def test_recovery_stops_only_journal_when_drive_absent_and_rebinds_after_return(tmp_path,monkeypatch):
    import importlib.util
    spec=importlib.util.spec_from_file_location('recover',Path(__file__).parents[1]/'deploy/recover_drive.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    device=tmp_path/'known-usb';flag=tmp_path/'rebind';failures=tmp_path/'failures'
    monkeypatch.setattr(module,'DEVICE',device);monkeypatch.setattr(module,'FLAG',flag);monkeypatch.setattr(module,'FAILURES',failures)
    original=Path.read_text
    monkeypatch.setattr(Path,'read_text',lambda self,*a,**kw:'/home/shreyansh/voice-journal-studio-20261016' if str(self)=='/etc/voice-journal-release' else original(self,*a,**kw))
    calls=[]
    monkeypatch.setattr(module,'run',lambda args,**kw:(calls.append(args) or SimpleNamespace(stdout=module.UUID)))
    module.main()
    assert flag.exists() and calls[-1][-1]=='stop' and 'voice-journal-stabilized' in calls[-1]
    module.main();assert len(calls)==1
    device.touch();monkeypatch.setattr(Path,'is_mount',lambda _:True);monkeypatch.setattr(module,'readable_database',lambda:True)
    module.main()
    assert calls[-1][-4:]==['up','-d','--no-build','--force-recreate'] and not flag.exists()
