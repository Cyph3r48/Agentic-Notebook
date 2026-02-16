from pathlib import Path

from app.core import migrations


def test_alembic_config_points_to_backend_paths():
    cfg = migrations._alembic_config()
    backend_root = Path(__file__).resolve().parents[1]

    assert Path(cfg.config_file_name).resolve() == (backend_root / "alembic.ini").resolve()
    assert Path(cfg.get_main_option("script_location")).resolve() == (backend_root / "alembic").resolve()

