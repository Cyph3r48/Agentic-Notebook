from pathlib import Path

from app.core import migrations


def test_alembic_config_points_to_backend_paths():
    cfg = migrations._alembic_config()
    backend_root = Path(__file__).resolve().parents[1]

    assert Path(cfg.config_file_name).resolve() == (backend_root / "alembic.ini").resolve()
    assert Path(cfg.get_main_option("script_location")).resolve() == (backend_root / "alembic").resolve()


def test_single_migration_head_is_the_provider_credentials_revision():
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(migrations._alembic_config())
    assert script.get_heads() == ["20261012_000003"]
    assert script.get_revision("20261012_000003").down_revision == "20260217_000002"
