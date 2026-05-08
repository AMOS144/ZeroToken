"""数据库迁移测试"""

import sqlite3


def test_migration_runner_creates_tables():
    """MigrationRunner 在空数据库上创建所有表"""
    from zerotoken.repository.migrations import MigrationRunner

    conn = sqlite3.connect(":memory:")
    runner = MigrationRunner(conn)
    runner.run()
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = {row[0] for row in cursor.fetchall()}
    assert "scripts" in tables
    assert "trajectories" in tables
    assert "session_headers" in tables
    assert "session_steps" in tables
    assert "session_runtime" in tables
    assert "fingerprints" in tables
    assert "script_bindings" in tables
    assert "_migrations" in tables


def test_migration_runner_idempotent():
    """多次调用 run() 不会报错"""
    from zerotoken.repository.migrations import MigrationRunner

    conn = sqlite3.connect(":memory:")
    runner = MigrationRunner(conn)
    runner.run()
    runner.run()
    cursor = conn.execute("SELECT COUNT(*) FROM _migrations")
    count = cursor.fetchone()[0]
    assert count > 0


def test_migration_runner_tracks_versions():
    """已执行的迁移有版本记录"""
    from zerotoken.repository.migrations import MigrationRunner, MIGRATIONS

    conn = sqlite3.connect(":memory:")
    runner = MigrationRunner(conn)
    runner.run()
    cursor = conn.execute("SELECT version FROM _migrations ORDER BY version")
    versions = [row[0] for row in cursor.fetchall()]
    assert versions == [m[0] for m in MIGRATIONS]
