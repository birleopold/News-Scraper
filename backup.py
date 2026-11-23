"""Create a consistent online SQLite backup without stopping the app."""
from ugwatch.backup import make_backup
from ugwatch.paths import database_path


def main():
    source=database_path()
    if not source.exists(): raise SystemExit('No database yet. Start the application first.')
    print(f'Backup saved: {make_backup(source)}')


if __name__=='__main__': main()
