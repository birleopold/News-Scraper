import pytest
from datetime import datetime,timedelta
from ugwatch.db import connect,upsert_notice,EAT
from ugwatch.collectors import extract_deadline,canonical,category,public_url,collect_feed,collect_egp
from ugwatch import service
from helpers import insert,JsonClient,start_fake_run,insert_job,MONITOR_PAGE


def test_second_copy_detects_running_dashboard():
    import socket
    from run import already_running
    with socket.socket() as server:
        server.bind(('127.0.0.1',0)); server.listen(1)
        port=server.getsockname()[1]
        assert already_running(port)
    assert not already_running(port)


def test_only_one_copy_can_hold_the_app_lock(tmp_path):
    import subprocess,sys,textwrap
    from pathlib import Path
    from run import acquire_instance_lock
    lock=tmp_path/'app.lock'
    held=acquire_instance_lock(lock)
    assert held is not None
    probe=textwrap.dedent(f'''
        import sys; sys.path.insert(0,{str(Path(__file__).resolve().parent.parent)!r})
        from pathlib import Path
        from run import acquire_instance_lock
        print('free' if acquire_instance_lock(Path({str(lock)!r})) else 'taken')''')
    second=subprocess.run([sys.executable,'-c',probe],capture_output=True,text=True,timeout=60)
    assert second.stdout.strip()=='taken', second.stderr
    held.close()
    third=subprocess.run([sys.executable,'-c',probe],capture_output=True,text=True,timeout=60)
    assert third.stdout.strip()=='free', third.stderr


def test_second_server_cannot_share_the_port(app):
    from werkzeug.serving import make_server
    from run import exclusive_port_binding
    exclusive_port_binding()
    first=make_server('127.0.0.1',0,app)
    try:
        # Werkzeug reports the refused bind by exiting; either form means the port is protected.
        with pytest.raises((OSError,SystemExit)):
            make_server('127.0.0.1',first.server_port,app)
    finally:
        first.server_close()
