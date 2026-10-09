#!/usr/bin/env python3
"""Connect Python ports via a duplex ALSA MIDI Through port used by Mixxx.
Run only after dj midi-serve/midi-fade has opened its ports.
"""
import argparse
import re
import subprocess


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--through',default='Midi Through Port-0')
    p.add_argument('--dry-run',action='store_true')
    a=p.parse_args()
    listing=subprocess.run(['aconnect','-l'],capture_output=True,text=True,check=True).stdout
    ports=[]; client=None; client_name=''
    for line in listing.splitlines():
        m=re.match(r"client (\d+): '([^']+)'",line)
        if m: client,client_name=m.groups()
        m=re.match(r"\s+(\d+) '([^']+)'",line)
        if m and client:
            number,name=m.groups(); ports.append((f'{client}:{number}',client_name+' '+name))
    def find(name):
        matches=[address for address,label in ports if name in label]
        if len(matches)!=1:
            raise SystemExit(f'Attesa una porta {name!r}, trovate {matches}. Eseguire aconnect -l e scegliere --through.')
        return matches[0]
    source=find('DJ-to-Mixxx'); destination=find('DJ-from-Mixxx'); through=find(a.through)
    for src,dst in ((source,through),(through,destination)):
        print(f'aconnect {src} {dst}')
        if not a.dry_run:
            r=subprocess.run(['aconnect',src,dst],capture_output=True,text=True)
            if r.returncode:
                raise SystemExit(r.stderr or 'Connessione già presente oppure fallita: verificare aconnect -l')

if __name__=='__main__': main()
