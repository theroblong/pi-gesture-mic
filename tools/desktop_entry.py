"""Write desktop launchers without interpolating installation paths into shell code."""
import argparse
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def exec_quote(value):
    # Desktop Entry Exec escaping is separate from shell escaping.
    value = str(value)
    if any(c in value for c in '\n\r\x00'):
        raise ValueError('Installation paths may not contain newlines or NUL')
    value = value.replace('%','%%').replace('\\','\\\\\\\\')
    for char in ('"', '`', '$'):
        value = value.replace(char, '\\\\' + char)
    return '"' + value + '"'


def write_entry(path, name, script, arguments=(), terminal=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = ('[Desktop Entry]\nType=Application\nName='+name+'\nExec=/bin/bash '+exec_quote(script)+
            ''.join(' '+exec_quote(v) for v in arguments)+'\nTerminal='+str(terminal).lower()+
            '\nCategories=Utility;Accessibility;\nX-GNOME-Autostart-enabled=true\n')
    tmp = path.with_suffix('.tmp')
    tmp.write_text(text)
    tmp.replace(path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=('launchers','resume','autostart','disable-autostart','clear-resume'))
    args = parser.parse_args()
    config = Path(os.environ.get('XDG_CONFIG_HOME',Path.home()/'.config'))
    data = Path(os.environ.get('XDG_DATA_HOME',Path.home()/'.local/share'))
    auto = config/'autostart'
    if args.mode == 'launchers':
        write_entry(data/'applications/pi-gesture-mic.desktop','Gesture Control',ROOT/'run_pi.sh',('--desktop',))
        write_entry(data/'applications/pi-gesture-mic-stop.desktop','Stop Gesture Control',ROOT/'stop_pi.sh')
        write_entry(data/'applications/pi-gesture-mic-setup.desktop','Gesture Control Setup',ROOT/'run_pi.sh',('--desktop','--setup'))
    elif args.mode == 'resume':
        write_entry(auto/'pi-gesture-mic-resume.desktop','Finish Gesture Control Setup',ROOT/'install_pi.sh',('--resume',),True)
    elif args.mode == 'autostart':
        write_entry(auto/'gesture-control-pi.desktop','Gesture Control',ROOT/'run_pi.sh',('--desktop',))
    elif args.mode == 'disable-autostart':
        (auto/'gesture-control-pi.desktop').unlink(missing_ok=True)
    else:
        (auto/'pi-gesture-mic-resume.desktop').unlink(missing_ok=True)


if __name__ == '__main__':
    main()
