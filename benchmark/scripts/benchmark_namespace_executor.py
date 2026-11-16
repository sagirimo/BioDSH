"""Linux/WSL offline tool executor; private mounts only, no host config changes.

Trusted controller supplies public_dir, output_dir and an argv list. Not a
complete BioDSH adapter or security certification. No network/API key belongs
inside this worker. Needs existing unshare, mount and setpriv in the distro.
"""
import argparse
import ctypes
import json
import os
from pathlib import Path
import resource
import selectors
import signal
import subprocess
import sys
import time

RESOURCE_PROFILES = {
    'default': dict(address_space_bytes=1024**3, cpu_seconds=15,
                    file_bytes=8*1024**2),
    # User-approved task-specific change, 2026-10-13. Never accepted from agent
    # tool arguments; the trusted launcher must supply the exact public task.
    'nwtco_complete_v1': dict(address_space_bytes=1024**3, cpu_seconds=120,
                              file_bytes=64*1024**2),
    # User-approved task-specific changes, 2026-10-15: complete per-sample
    # reference tables exceed the default 8MiB file limit. Same trust rules.
    'fission_complete_v1': dict(address_space_bytes=1024**3, cpu_seconds=120,
                                file_bytes=128*1024**2),
    'zeller_complete_v1': dict(address_space_bytes=1024**3, cpu_seconds=120,
                               file_bytes=128*1024**2),
}
NWTCO_TASK = 'biodsh-candidate-nwtco-complete-casecohort-workflow-001'
PROFILE_TASKS = {'nwtco_complete_v1': NWTCO_TASK,
                 'fission_complete_v1': 'biodsh-candidate-fission-timecourse-workflow-001',
                 'zeller_complete_v1': 'biodsh-candidate-zeller-crc-microbiome-workflow-001'}
PROFILE_WALL = {}
# User-approved general rule (2026-10-15): task-bound profiles at about twice the
# measured reference need, capped below; set only by the trusted launcher.
GENERAL_PROFILE_CAPS = dict(address_space_bytes=2*1024**3, cpu_seconds=300, file_bytes=512*1024**2, wall_seconds=600)
_GENERAL = Path(__file__).resolve().parent.parent/'benchmarks/runtime_profiles.json'
if _GENERAL.is_file():
    for _name, _p in json.loads(_GENERAL.read_text('utf-8'))['profiles'].items():
        if _name in RESOURCE_PROFILES or set(_p) != {'task_id', 'limits', 'wall_seconds', 'basis'}:
            raise ValueError('Invalid general runtime profile: '+_name)
        if set(_p['limits']) != {'address_space_bytes', 'cpu_seconds', 'file_bytes'} or any(
                type(v) is not int or not 0 < v <= GENERAL_PROFILE_CAPS[k] for k, v in _p['limits'].items()):
            raise ValueError('Runtime profile exceeds approved caps: '+_name)
        if type(_p['wall_seconds']) not in (int, float) or not 0 < _p['wall_seconds'] <= GENERAL_PROFILE_CAPS['wall_seconds']:
            raise ValueError('Runtime profile wall exceeds approved cap: '+_name)
        RESOURCE_PROFILES[_name] = dict(_p['limits'])
        PROFILE_TASKS[_name] = _p['task_id']
        PROFILE_WALL[_name] = _p['wall_seconds']


def resource_limits(profile):
    if not isinstance(profile,str) or profile not in RESOURCE_PROFILES:
        raise ValueError('Unknown bounded resource profile')
    return dict(RESOURCE_PROFILES[profile])

def mount(source,target,kind=None,flags=0,data=None):
    libc=ctypes.CDLL(None,use_errno=True)
    libc.mount.argtypes=[ctypes.c_char_p,ctypes.c_char_p,ctypes.c_char_p,ctypes.c_ulong,ctypes.c_char_p]
    encode=lambda x:None if x is None else os.fsencode(x)
    if libc.mount(encode(source),encode(target),encode(kind),flags,encode(data))!=0:
        err=ctypes.get_errno();raise OSError(err,os.strerror(err),str(target))

def bind(source,target,readonly=True,device=False):
    source=Path(source)
    if source.is_dir():target.mkdir(parents=True,exist_ok=True)
    else:target.parent.mkdir(parents=True,exist_ok=True);target.touch()
    mount(source,target,flags=4096) # MS_BIND, deliberately not recursive.
    flags=4096|32|2 # bind remount nosuid
    if readonly:flags|=1
    if not device:flags|=4
    mount(None,target,flags=flags)

def inner(config):
    cfg=json.loads(Path(config).read_text('utf-8'));root=Path(cfg['root'])
    limits=resource_limits(cfg.get('resource_profile','default'))
    if os.getpid()!=1 or os.getuid()!=0:raise ValueError('Expected fresh mapped-root PID namespace')
    # Explicit private propagation even on util-linux versions with that default.
    mount(None,'/',flags=16384|262144) # MS_REC|MS_PRIVATE
    mount('tmpfs',root,'tmpfs',2|4,'size=16m,mode=755')
    # WSL mounts drivers/modules below /usr; copying that mount tree is neither
    # needed nor permitted in this user namespace. Explicit offline runtime.
    runtime_dirs=['/usr/bin','/usr/sbin','/usr/lib/x86_64-linux-gnu',
                  '/usr/lib/python'+str(sys.version_info.major)+'.'+str(sys.version_info.minor),'/usr/lib64']
    for directory in runtime_dirs:
        if Path(directory).is_dir():bind(directory,root/directory.lstrip('/'))
    for name in ['bin','sbin','lib','lib64']:
        src=Path('/'+name)
        if src.is_symlink():os.symlink(os.readlink(src),root/name)
        elif src.exists():bind(src,root/name)
    if Path('/etc/ld.so.cache').exists():bind('/etc/ld.so.cache',root/'etc/ld.so.cache')
    for name in ['null','zero','urandom','random']:bind('/dev/'+name,root/'dev'/name,device=True)
    for name,size in [('tmp','32m'),('home/agent','8m')]:
        dst=root/name;dst.mkdir(parents=True);mount('tmpfs',dst,'tmpfs',2|4,'size='+size+',mode=700')
    (root/'proc').mkdir();mount('proc',root/'proc','proc',2|4|8)
    bind(cfg['public_dir'],root/'work/task')
    bind(cfg['output_dir'],root/'work/output',readonly=False)
    if cfg.get('science_dir'):
        bind(cfg['science_dir'],root/'opt/science')
    # Root tree readonly; only output, temporary and home files are writable.
    mount(None,root,flags=32|1|2|4)
    os.chdir(root);os.chroot('.');os.chdir('/work/output')
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    resource.setrlimit(resource.RLIMIT_AS,(limits['address_space_bytes'],)*2)
    resource.setrlimit(resource.RLIMIT_CPU,(limits['cpu_seconds'],)*2)
    resource.setrlimit(resource.RLIMIT_FSIZE,(limits['file_bytes'],)*2)
    resource.setrlimit(resource.RLIMIT_NOFILE,(64,64))
    # Do not inherit host sockets, directory descriptors or environment secrets.
    os.closerange(3,65536)
    env={'PATH':'/usr/bin:/bin','HOME':'/home/agent','LANG':'C.UTF-8','TMPDIR':'/tmp',
        'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','PYTHONDONTWRITEBYTECODE':'1'}
    os.execve('/usr/bin/setpriv',['setpriv','--no-new-privs','--bounding-set=-all',
        '--inh-caps=-all','--ambient-caps=-all',*cfg['argv']],env)

def run(public_dir,output_dir,state_dir,argv,timeout=30,science_dir=None,cancel_file=None,output_limit=1024*1024,resource_profile='default'):
    public_dir=Path(public_dir).resolve(strict=True);output_dir=Path(output_dir).resolve(strict=True)
    state_dir=Path(state_dir).resolve(strict=True)
    limits=resource_limits(resource_profile)
    if resource_profile in PROFILE_TASKS:
        card=json.loads((public_dir/'task_metadata.json').read_text('utf-8'))
        if card.get('task_id')!=PROFILE_TASKS[resource_profile]:
            raise ValueError('Task-specific resource profile requires its exact task')
        if type(timeout) not in (int,float) or not 0<timeout<=PROFILE_WALL.get(resource_profile,180):
            raise ValueError('Task-specific wall limit exceeds the approved profile')
    if science_dir is not None:
        science_dir=Path(science_dir).resolve(strict=True)
        if not science_dir.is_dir():raise ValueError('Science runtime must be a directory')
        for other in (public_dir,output_dir,state_dir):
            if science_dir==other or science_dir in other.parents or other in science_dir.parents:
                raise ValueError('Science runtime must be separate from task/output/state')
    if not public_dir.is_dir() or not output_dir.is_dir():raise ValueError('Directories required')
    if public_dir==output_dir or public_dir in output_dir.parents or output_dir in public_dir.parents:raise ValueError('Separate task/output directories required')
    if not isinstance(argv,list) or not argv or not all(isinstance(x,str) and '\0' not in x for x in argv):raise ValueError('Explicit argv required')
    # Fail closed if the public bundle contains symlinks to private host paths.
    if any(p.is_symlink() for p in public_dir.rglob('*')):raise ValueError('Public directory contains a symlink')
    root=state_dir/'root';root.mkdir();cfg=state_dir/'launch.json'
    cfg.write_text(json.dumps(dict(root=str(root),public_dir=str(public_dir),output_dir=str(output_dir),argv=argv,
        science_dir=str(science_dir) if science_dir is not None else None,resource_profile=resource_profile)),'utf-8')
    cmd=['/usr/bin/unshare','--user','--map-root-user','--mount','--net','--pid','--ipc','--uts','--fork','--kill-child',
        '/usr/bin/python3','-I','-S','-B',str(Path(__file__).resolve()),'--inner',str(cfg)]
    started=time.monotonic()
    p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True,
        close_fds=True,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'})
    timed_out=False;cancelled=False;output_limited=False;killed=False
    selector=selectors.DefaultSelector();chunks={'stdout':bytearray(),'stderr':bytearray()};kept=0
    for name,stream in [('stdout',p.stdout),('stderr',p.stderr)]:selector.register(stream,selectors.EVENT_READ,name)
    try:
        while selector.get_map() or p.poll() is None:
            if not killed:
                cancelled=cancel_file is not None and Path(cancel_file).exists()
                timed_out=not cancelled and time.monotonic()-started>=timeout
                if cancelled or timed_out or output_limited:
                    try:os.killpg(p.pid,signal.SIGKILL)
                    except ProcessLookupError:pass # Owned group already exited.
                    killed=True
            for key,_ in selector.select(.05):
                data=os.read(key.fileobj.fileno(),65536)
                if not data:
                    selector.unregister(key.fileobj);key.fileobj.close();continue
                room=max(0,output_limit-kept)
                chunks[key.data].extend(data[:room]);kept+=min(room,len(data))
                if len(data)>room:output_limited=True
        p.wait()
    finally:
        selector.close()
        if p.poll() is None:
            try:os.killpg(p.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            p.wait()
    stdout=bytes(chunks['stdout']);stderr=bytes(chunks['stderr'])
    return dict(returncode=p.returncode,timed_out=timed_out,stdout=stdout.decode('utf-8','replace'),stderr=stderr.decode('utf-8','replace'),
        cancelled=cancelled,output_limit_exceeded=output_limited,retained_output_bytes=kept,
        elapsed_seconds=time.monotonic()-started,controller_cumulative_child_peak_rss_bytes=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss*1024,
        process_terminal=p.poll() is not None,resource_profile=resource_profile,resource_limits=limits,
        scope='offline tool worker;not complete agent/model runtime')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--inner',type=Path,required=True);inner(parser.parse_args().inner)
