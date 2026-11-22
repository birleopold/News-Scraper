"""Create a consistent online SQLite backup without stopping the app."""
from pathlib import Path

from ugwatch.backup import make_backup


def main():
    source=Path(__file__).resolve().parent/'data'/'uganda_watch.sqlite3'
    if not source.exists(): raise SystemExit('No database yet. Start the application first.')
    print(f'Backup saved: {make_backup(source)}')


if __name__=='__main__': main()
