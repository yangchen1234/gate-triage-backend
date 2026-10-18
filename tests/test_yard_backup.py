from contextlib import closing
import sqlite3

import pytest

from scripts.backup_yard import backup


def test_online_backup_includes_committed_wal(tmp_path):
    source, output = tmp_path / 'source.sqlite3', tmp_path / 'backup.sqlite3'
    with closing(sqlite3.connect(source)) as writer:
        writer.execute('PRAGMA journal_mode=WAL')
        writer.execute('CREATE TABLE evidence (note TEXT NOT NULL)')
        writer.execute("INSERT INTO evidence VALUES ('verified gate-out')")
        writer.commit()
        assert source.with_name(source.name + '-wal').exists()
        assert backup(source, output) == output
        with closing(sqlite3.connect(output)) as reader:
            assert reader.execute('SELECT note FROM evidence').fetchall() == [('verified gate-out',)]
            assert reader.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    assert output.stat().st_mode & 0o777 == 0o600


def test_backup_never_overwrites_existing_file(tmp_path):
    source, output = tmp_path / 'source.sqlite3', tmp_path / 'backup.sqlite3'
    with closing(sqlite3.connect(source)) as db:
        db.execute('CREATE TABLE evidence (note TEXT)')
    output.write_bytes(b'original backup')
    with pytest.raises(ValueError, match='never overwritten'):
        backup(source, output)
    assert output.read_bytes() == b'original backup'


def test_invalid_source_leaves_no_partial_backup(tmp_path):
    source, output = tmp_path / 'source.sqlite3', tmp_path / 'backup.sqlite3'
    with pytest.raises(ValueError, match='does not exist'):
        backup(source, output)
    assert not output.exists()
    source.write_bytes(b'invalid database')
    with pytest.raises(sqlite3.DatabaseError):
        backup(source, output)
    assert not output.exists()
