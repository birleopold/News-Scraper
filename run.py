import argparse
import logging
import socket
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

from ugwatch.app import create_app
from ugwatch.db import connect
from ugwatch.service import scheduler, start_run

LOG_FILE=Path(__file__).resolve().parent/'data'/'app.log'


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
    args=parser.parse_args()
    setup_logging(args.log_file or sys.stdout is None)
    if not args.fetch and already_running(args.port):
        print(f'Uganda Business Watch is already running: open http://127.0.0.1:{args.port}')
        logging.info('Not starting a second copy: port %s is already in use.',args.port)
        return
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
    try: app.run(host='127.0.0.1',port=args.port,debug=False,use_reloader=False)
    finally: stop.set()


if __name__=='__main__': main()
