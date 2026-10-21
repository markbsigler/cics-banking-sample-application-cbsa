"""Tests for the CBSA banking sample's Python BANKDATA equivalent."""

import json
import re
import sqlite3
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path

import pytest

import bankdata_setup as bd


def config_for(
    tmp_path: Path,
    *,
    start: int = 1,
    final: int = 5,
    increment: int = 1,
    seed: int = 42,
) -> bd.BankDataConfig:
    """Build a small, deterministic configuration rooted in ``tmp_path``."""
    return bd.BankDataConfig(
        start_customer_number=start,
        final_customer_number=final,
        customer_increment=increment,
        random_seed=seed,
        data_dir=str(tmp_path),
    )


def customer_rows(data_dir: Path) -> list[tuple[str, str, str]]:
    """Read customer number, name, and compatibility record from SQLite."""
    with closing(sqlite3.connect(data_dir / "customer.db")) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT customer_number, customer_name, record_data "
            "FROM customer ORDER BY customer_number"
        )
        return [(str(row[0]), str(row[1]), str(row[2])) for row in cursor.fetchall()]


def table_names(data_dir: Path, filename: str) -> list[str]:
    """Return user table names from one of the generated databases."""
    with closing(sqlite3.connect(data_dir / filename)) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        return [str(row[0]) for row in cursor.fetchall()]


def index_names(data_dir: Path, filename: str) -> list[str]:
    """Return index names from one of the generated databases."""
    with closing(sqlite3.connect(data_dir / filename)) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type = 'index'")
        return [str(row[0]) for row in cursor.fetchall()]


def test_config_defaults_match_the_jcl() -> None:
    config = bd.BankDataConfig()

    assert config.start_customer_number == 1
    assert config.final_customer_number == 10000
    assert config.customer_increment == 1
    assert config.random_seed == 1000000000000000
    assert config.data_dir == "./data"


def test_manager_creates_nested_data_directory(tmp_path: Path) -> None:
    data_dir = tmp_path / "nested" / "data"
    manager = bd.VSAMFileManager(config_for(data_dir))

    assert manager.data_dir == data_dir
    assert data_dir.is_dir()


def test_define_and_delete_abndfile_cluster(tmp_path: Path) -> None:
    manager = bd.VSAMFileManager(config_for(tmp_path))

    assert manager.define_abndfile_cluster() is True
    assert (tmp_path / "abndfile.db").exists()
    assert "abndfile" in table_names(tmp_path, "abndfile.db")
    assert "idx_abndfile_timestamp" in index_names(tmp_path, "abndfile.db")

    assert manager.delete_dataset("ABNDFILE") is True
    assert not (tmp_path / "abndfile.db").exists()
    assert manager.delete_dataset("ABNDFILE") is True


def test_define_and_delete_customer_cluster(tmp_path: Path) -> None:
    manager = bd.VSAMFileManager(config_for(tmp_path))

    assert manager.define_customer_cluster() is True
    assert (tmp_path / "customer.db").exists()
    assert "customer" in table_names(tmp_path, "customer.db")
    indexes = index_names(tmp_path, "customer.db")
    assert "idx_customer_name" in indexes
    assert "idx_customer_created" in indexes

    assert manager.delete_dataset("CUSTOMER") is True
    assert not (tmp_path / "customer.db").exists()


def test_define_clusters_return_false_on_sqlite_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_connect(*args: object, **kwargs: object) -> sqlite3.Connection:
        raise sqlite3.OperationalError("unavailable")

    monkeypatch.setattr(sqlite3, "connect", fail_connect)
    manager = bd.VSAMFileManager(config_for(tmp_path))

    assert manager.define_abndfile_cluster() is False
    assert manager.define_customer_cluster() is False


def test_delete_dataset_continues_when_unlink_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "abndfile.db").write_text("placeholder")

    def fail_unlink(self: Path, missing_ok: bool = False) -> None:
        raise OSError("permission denied")

    monkeypatch.setattr(Path, "unlink", fail_unlink)
    manager = bd.VSAMFileManager(config_for(tmp_path))

    assert manager.delete_dataset("ABNDFILE") is True


def test_generator_uses_configured_data_directory(tmp_path: Path) -> None:
    data_dir = tmp_path / "generated"
    generator = bd.BankDataGenerator(config_for(tmp_path), data_dir=data_dir)

    assert generator.data_dir == data_dir


def test_generator_random_fields_are_deterministic(tmp_path: Path) -> None:
    config = config_for(tmp_path, seed=1234)
    first = bd.BankDataGenerator(config).generate_customer_data(7)
    second = bd.BankDataGenerator(config).generate_customer_data(7)

    for key in (
        "customer_name",
        "customer_address",
        "customer_phone",
        "customer_credit_score",
        "customer_review_date",
        "date_of_birth",
    ):
        assert first[key] == second[key]


def test_generate_customer_data_has_expected_shape(tmp_path: Path) -> None:
    data = bd.BankDataGenerator(config_for(tmp_path)).generate_customer_data(7)

    assert data["eyecatcher"] == "CUST"
    assert data["customer_number"] == "0000000007"
    assert re.fullmatch(r"\d{3}-\d{3}-\d{4}", str(data["customer_phone"]))
    assert 300 <= int(data["customer_credit_score"]) <= 850

    birth_date = date.fromisoformat(str(data["date_of_birth"]))
    today = date.today()
    age = (
        today.year
        - birth_date.year
        - ((today.month, today.day) < (birth_date.month, birth_date.day))
    )
    assert 17 <= age <= 80

    review_date = date.fromisoformat(str(data["customer_review_date"]))
    assert today - timedelta(days=365) <= review_date <= today


def test_create_record_data_pads_fixed_width_fields(tmp_path: Path) -> None:
    generator = bd.BankDataGenerator(config_for(tmp_path))
    data = generator.generate_customer_data(42)

    record = json.loads(generator.create_record_data(data))

    assert record["eyecatcher"] == "CUST"
    assert record["customer_number"] == "0000000042"
    assert len(record["customer_number"]) == 10
    assert len(record["customer_name"]) == 50
    assert len(record["customer_address"]) == 80
    assert len(record["customer_phone"]) == 15
    assert len(record["credit_score"]) == 3
    assert len(record["review_date"]) == 10
    assert len(record["date_of_birth"]) == 10
    assert record["filler"] == " " * 77


def test_run_data_generation_respects_range_and_increment(tmp_path: Path) -> None:
    config = config_for(tmp_path, start=1, final=5, increment=2)
    manager = bd.VSAMFileManager(config)
    assert manager.define_customer_cluster() is True

    generator = bd.BankDataGenerator(config)
    assert generator.run_data_generation() is True

    rows = customer_rows(tmp_path)
    assert [row[0] for row in rows] == [
        "0000000001",
        "0000000003",
        "0000000005",
    ]
    record = json.loads(rows[0][2])
    assert record["eyecatcher"] == "CUST"


def test_run_data_generation_fails_without_customer_cluster(tmp_path: Path) -> None:
    generator = bd.BankDataGenerator(config_for(tmp_path))

    assert generator.run_data_generation() is False


def test_complete_setup_creates_clusters_and_customers(tmp_path: Path) -> None:
    data_dir = tmp_path / "setup-data"
    setup = bd.BankDataSetup(
        {
            "start_customer_number": 1,
            "final_customer_number": 2,
            "customer_increment": 1,
            "random_seed": 7,
            "data_dir": str(data_dir),
        },
        log_file=None,
    )

    assert setup.run_complete_setup() is True
    assert (data_dir / "abndfile.db").exists()
    assert len(customer_rows(data_dir)) == 2


def test_complete_setup_reports_step_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    setup = bd.BankDataSetup({"data_dir": str(tmp_path)}, log_file=None)

    def fail_generation() -> bool:
        return False

    monkeypatch.setattr(setup.data_generator, "run_data_generation", fail_generation)

    assert setup.run_complete_setup() is False


def test_complete_setup_catches_unexpected_step_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    setup = bd.BankDataSetup({"data_dir": str(tmp_path)}, log_file=None)

    def fail_step() -> bool:
        raise sqlite3.OperationalError("boom")

    monkeypatch.setattr(setup, "run_bankdat0_step", fail_step)

    assert setup.run_complete_setup() is False


def test_print_summary_warns_on_unreadable_database(tmp_path: Path) -> None:
    data_dir = tmp_path / "bad-db"
    data_dir.mkdir()
    (data_dir / "customer.db").write_text("not a sqlite database")
    setup = bd.BankDataSetup({"data_dir": str(data_dir)}, log_file=None)

    setup.print_summary()


def test_main_uses_requested_data_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    data_dir = tmp_path / "cli-data"

    exit_code = bd.main(
        [
            "--start-customer",
            "1",
            "--end-customer",
            "2",
            "--data-dir",
            str(data_dir),
            "--seed",
            "7",
        ]
    )

    assert exit_code == 0
    assert len(customer_rows(data_dir)) == 2


def test_main_returns_failure_when_setup_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_setup(self: bd.BankDataSetup) -> bool:
        return False

    monkeypatch.setattr(bd.BankDataSetup, "run_complete_setup", fail_setup)

    assert bd.main(["--data-dir", str(tmp_path / "unused-data")]) == 1
