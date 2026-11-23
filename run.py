import argparse
import logging
import os
import socket
import sys
import threading
import webbrowser
from logging.handlers import RotatingFileHandler

from ugwatch.app import create_app
from ugwatch.db import connect
from ugwatch.paths import data_dir, frozen
from ugwatch.service import scheduler, start_run

LOG_FILE=data_dir()/'app.log'


LOCK_FILE=data_dir()/'app.lock'


def acquire_instance_lock(path=LOCK_FILE):
    """Hold an OS file lock for the life of the process so only one dashboard copy runs.

    Unlike checking the port, this has no gap between checking and starting: two copies
    launched seconds apart (sign-in task and a manual start) cannot both win. The OS
    releases the lock automatically if the process exits or crashes. Returns the open
    lock file to keep, or None when another copy holds it."""
    path.parent.mkdir(parents=True,exist_ok=True)
    handle=open(path,'a+')
    try:
        if os.name=='nt':
            import msvcrt
            handle.seek(0); msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except OSError:
        handle.close(); return None
    return handle


def exclusive_port_binding():
    """On Windows, SO_REUSEADDR (Python's default for HTTP servers) lets a second program
    listen on the same port, and requests then go to either. Bind exclusively instead."""
    if os.name!='nt': return
    from werkzeug.serving import BaseWSGIServer
    BaseWSGIServer.allow_reuse_address=False
    original=BaseWSGIServer.server_bind
    def server_bind(self):
        self.socket.setsockopt(socket.SOL_SOCKET,getattr(socket,'SO_EXCLUSIVEADDRUSE',-5),1)
        original(self)
    BaseWSGIServer.server_bind=server_bind


def already_running(port):
    """True when something already answers on the dashboard port (e.g. the sign-in task)."""
    with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex(('127.0.0.1',port))==0


def setup_logging(to_file):
    fmt='%(asctime)s %(levelname)s %(message)s'
    if not to_file:
        logging.basicConfig(level=logging.INFO,format=fmt); return
    # pythonw.exe (no console window) has no stdout/stderr; keep a small rotating log instead.
    LOG_FILE.parent.mkdir(parents=True,exist_ok=True)
    handler=RotatingFileHandler(LOG_FILE,maxBytes=1_000_000,backupCount=3,encoding='utf-8')
    logging.basicConfig(level=logging.INFO,format=fmt,handlers=[handler])
    stream=handler.stream
    sys.stdout=sys.stdout or stream; sys.stderr=sys.stderr or stream


def main():
    parser=argparse.ArgumentParser(description='Uganda Business Watch')
    parser.add_argument('--fetch',action='store_true',help='Fetch once and exit (suitable for an external scheduler)')
    parser.add_argument('--port',type=int,default=5050)
    parser.add_argument('--no-scheduler',action='store_true')
    parser.add_argument('--log-file',action='store_true',help=f'Write the log to {LOG_FILE} (automatic without a console)')
    parser.add_argument('--open',action='store_true',help='Open the dashboard in the browser (the default for the installed app)')
    parser.add_argument('--background',action='store_true',help='Never open the browser (used when starting at sign-in)')
    args=parser.parse_args()
    # The installed app opens the dashboard when started from its shortcut; at sign-in it starts quietly.
    show=(args.open or frozen()) and not args.background and not args.fetch
    url=f'http://127.0.0.1:{args.port}'
    setup_logging(args.log_file or sys.stdout is None)
    if not args.fetch:
        lock=acquire_instance_lock()
        if lock is None or already_running(args.port):
            print(f'Uganda Business Watch is already running: open http://127.0.0.1:{args.port}')
            logging.info('Not starting a second copy: %s.','another copy holds the app lock' if lock is None else f'port {args.port} is already in use')
            if show: webbrowser.open(url)   # already running in the background: just show it
            return
        exclusive_port_binding()
    app=create_app()
    if args.fetch:
        run_id,started=start_run(app.config['DATABASE'],background=False)
        print(f'Fetch run {run_id}: '+('finished; check Sources for results.' if started else 'another fetch is already running.'))
        return
    # Alerts link back to the dashboard, including when run later with --fetch.
    with connect(app.config['DATABASE']) as db:
        db.execute("INSERT OR REPLACE INTO settings VALUES ('dashboard_port',?)",(str(args.port),))
    stop=threading.Event()
    if not args.no_scheduler:
        threading.Thread(target=scheduler,args=(app.config['DATABASE'],stop),daemon=True).start()
    print(f'Uganda Business Watch: http://127.0.0.1:{args.port}')
    logging.info('Dashboard at http://127.0.0.1:%s',args.port)
    if show: threading.Timer(1.5,webbrowser.open,args=(url,)).start()
    try: app.run(host='127.0.0.1',port=args.port,debug=False,use_reloader=False)
    finally: stop.set()


if __name__=='__main__': main()
