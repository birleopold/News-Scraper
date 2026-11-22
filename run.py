import argparse
import logging
import threading

from ugwatch.app import create_app
from ugwatch.service import scheduler, start_run


def main():
    parser=argparse.ArgumentParser(description='Uganda Business Watch')
    parser.add_argument('--fetch',action='store_true',help='Fetch once and exit (suitable for an external scheduler)')
    parser.add_argument('--port',type=int,default=5050)
    parser.add_argument('--no-scheduler',action='store_true')
    args=parser.parse_args()
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    app=create_app()
    if args.fetch:
        run_id,started=start_run(app.config['DATABASE'],background=False)
        print(f'Fetch run {run_id}: '+('finished; check Sources for results.' if started else 'another fetch is already running.'))
        return
    stop=threading.Event()
    if not args.no_scheduler:
        threading.Thread(target=scheduler,args=(app.config['DATABASE'],stop),daemon=True).start()
    print(f'Uganda Business Watch: http://127.0.0.1:{args.port}')
    try: app.run(host='127.0.0.1',port=args.port,debug=False,use_reloader=False)
    finally: stop.set()


if __name__=='__main__': main()
