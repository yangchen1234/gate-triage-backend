"""Consistent online SQLite backup, including committed WAL contents."""
import argparse
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import sys
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gate_triage.config import Settings


def backup(database: Path, output: Path):
    database, output = database.resolve(), output.resolve()
    if not database.is_file(): raise ValueError('Source database does not exist')
    if output.exists() or output == database: raise ValueError('Choose a new backup path; existing files are never overwritten')
    output.parent.mkdir(parents=True, exist_ok=True)
    # Reserve the destination atomically; never truncate another backup if two
    # operators choose the same filename at the same time.
    try:
        fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise ValueError('Choose a new backup path; existing files are never overwritten') from None
    os.close(fd)
    try:
        with closing(sqlite3.connect(f'file:{quote(str(database))}?mode=ro', uri=True)) as src, closing(sqlite3.connect(output)) as dst:
            src.backup(dst)
            if dst.execute('PRAGMA integrity_check').fetchone()[0] != 'ok': raise ValueError('Backup integrity check failed')
        output.chmod(0o600)
    except Exception:
        output.unlink(missing_ok=True)
        raise
    return output


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',type=Path,default=Settings.from_env().yard_database_path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    try: print(backup(args.database,args.output))
    except (ValueError,sqlite3.Error,OSError) as exc: parser.exit(1,f'Backup failed: {exc}\n')
