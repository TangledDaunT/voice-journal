#!/usr/bin/python3
"""Recover only Voice Journal after its known external disk reconnects."""
import fcntl
import json
import os
from pathlib import Path
import subprocess

MOUNT=Path('/mnt/music-drive')
UUID='6EFF-790D'
DEVICE=Path('/dev/disk/by-uuid')/UUID
DATABASE=MOUNT/'voice-journal/voice-journal/voice-journal/db/voice_journal.db'
FLAG=Path('/run/voice-journal-drive-rebind')
FAILURES=Path('/run/voice-journal-health-failures')

def run(args, **kwargs):
    return subprocess.run(args,check=True,timeout=75,**kwargs)

def readable_database():
    try:
        with DATABASE.open('rb') as f:return f.read(16)==b'SQLite format 3\x00'
    except OSError:return False

def main():
    if Path('/run/voice-journal-maintenance').exists():return
    release=Path('/etc/voice-journal-release').read_text().strip()
    if not release.startswith('/home/shreyansh/voice-journal-'):raise ValueError('Unexpected release path')
    compose=['docker','compose','-p','voice-journal-stabilized','-f',str(Path(release)/'compose.yml')]
    if not DEVICE.exists():
        if not FLAG.exists():
            print('Journal USB drive absent; stopping journal services until it reconnects.',flush=True)
            FLAG.touch();run(compose+['stop'])
        return
    if not MOUNT.is_mount():
        FLAG.touch();run(['mount',str(MOUNT)])
    actual=run(['findmnt','-n','-o','UUID','--mountpoint',str(MOUNT)],capture_output=True,text=True).stdout.strip()
    if actual!=UUID or not readable_database():
        print('Journal drive is not readable at the expected mount; retaining all files.',flush=True)
        if not FLAG.exists():FLAG.touch();run(compose+['stop'])
        return
    if not FLAG.exists():
        try:
            result=run(['docker','inspect','voice_journal_daemon','voice_journal_web'],capture_output=True,text=True)
            states=json.loads(result.stdout)
            healthy=all(s['State']['Running'] and not s['State'].get('Restarting') for s in states) and states[1]['State'].get('Health',{}).get('Status')=='healthy'
        except (subprocess.SubprocessError,ValueError):healthy=False
        if healthy:FAILURES.unlink(missing_ok=True);return
        count=int(FAILURES.read_text())+1 if FAILURES.exists() else 1
        FAILURES.write_text(str(count))
        if count<3:return
    print('Recreating journal services against the restored external drive.',flush=True)
    run(compose+['up','-d','--no-build','--force-recreate'])
    FLAG.unlink(missing_ok=True);FAILURES.unlink(missing_ok=True)

if __name__=='__main__':
    with open('/run/voice-journal-recover.lock','w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        main()
