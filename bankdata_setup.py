#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
CBSA Banking Data Setup Script - Python Equivalent of BANKDATA.JCL

This script performs the same functions as the mainframe JCL:
1. Creates VSAM-equivalent data structures
2. Defines and initializes database objects
3. Executes the banking data generation program equivalent

Copyright IBM Corp. 2023
Converted from JCL to Python - August 2025
"""

import argparse
import json
import logging
import random
import sqlite3
import sys
from collections.abc import Callable, Sequence
from contextlib import closing
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any


@dataclass
class BankDataConfig:
    """Configuration class equivalent to JCL symbolic parameters."""

    bank_prefix: str = "CBSA.CICSBSA"
    db2_hlq: str = "DSNC10"
    bank_dbrmlib: str = "CBSA.CICSBSA.DBRM"
    db2_subsystem: str = "DBCG"
    db2_plan: str = "CBSA"
    bank_loadlib: str = "CBSA.CICSBSA.LOADLIB"

    # Data generation parameters (equivalent to BANKDATA program PARM).
    start_customer_number: int = 1
    final_customer_number: int = 10000
    customer_increment: int = 1
    random_seed: int = 1000000000000000

    # Directory holding the SQLite databases that stand in for VSAM datasets.
    data_dir: str = "./data"


class VSAMFileManager:
    """Manage VSAM-equivalent file operations using SQLite.

    Equivalent to IDCAMS operations in the JCL.
    """

    def __init__(
        self,
        config: BankDataConfig,
        data_dir: str | Path | None = None,
    ) -> None:
        self.config = config
        self.data_dir = Path(data_dir if data_dir is not None else config.data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger(__name__)

    def delete_dataset(self, dataset_name: str) -> bool:
        """Delete a dataset, mirroring ``DELETE`` plus ``SET MAXCC=0``."""
        try:
            db_path = self.data_dir / f"{dataset_name.lower()}.db"
            if db_path.exists():
                db_path.unlink()
                self.logger.info("Deleted dataset: %s", dataset_name)
            return True
        except OSError as exc:
            self.logger.warning("Could not delete %s: %s", dataset_name, exc)
            # SET MAXCC=0 equivalent - continue processing.
            return True

    def define_abndfile_cluster(self) -> bool:
        """Define the ABNDFILE cluster.

        Equivalent to DEFINE CLUSTER for ABNDFILE:
        - CYL(6 6) -> Initial size allocation
        - KEYS(12 0) -> Primary key length 12, offset 0
        - RECORDSIZE(681 681) -> Fixed record length 681
        - INDEXED -> SQLite table with primary key
        - REUSE -> Allow overwrite
        """
        try:
            db_path = self.data_dir / "abndfile.db"
            with closing(sqlite3.connect(db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS abndfile (
                        primary_key TEXT PRIMARY KEY,  -- KEYS(12 0)
                        record_data TEXT,               -- RECORDSIZE(681 681)
                        created_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_abndfile_timestamp "
                    "ON abndfile(created_timestamp)"
                )
                conn.commit()

            self.logger.info("ABNDFILE cluster defined successfully")
            return True
        except (OSError, sqlite3.Error) as exc:
            self.logger.error("Failed to define ABNDFILE cluster: %s", exc)
            return False

    def define_customer_cluster(self) -> bool:
        """Define the CUSTOMER cluster.

        Equivalent to DEFINE CLUSTER for CUSTOMER:
        - CYL(50 50) -> Large initial allocation
        - KEYS(16 4) -> Primary key length 16, offset 4
        - RECORDSIZE(259,259) -> Fixed record length 259
        - LOG(UNDO) -> Transaction logging enabled
        """
        try:
            db_path = self.data_dir / "customer.db"
            with closing(sqlite3.connect(db_path)) as conn:
                cursor = conn.cursor()
                # Better concurrency, equivalent to LOG(UNDO).
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS customer (
                        eyecatcher TEXT,                 -- First 4 bytes
                        customer_number TEXT PRIMARY KEY, -- KEYS(16 4)
                        customer_name TEXT,
                        customer_address TEXT,
                        customer_phone TEXT,
                        customer_credit_score INTEGER,
                        customer_review_date DATE,
                        date_of_birth DATE,
                        created_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                        last_modified DATETIME DEFAULT CURRENT_TIMESTAMP,
                        record_data TEXT                 -- 259-byte compatibility record
                    )
                    """
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_customer_name ON customer(customer_name)"
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_customer_created ON customer(created_timestamp)"
                )
                conn.commit()

            self.logger.info("CUSTOMER cluster defined successfully")
            return True
        except (OSError, sqlite3.Error) as exc:
            self.logger.error("Failed to define CUSTOMER cluster: %s", exc)
            return False


class BankDataGenerator:
    """Python equivalent of the COBOL BANKDATA program."""

    def __init__(
        self,
        config: BankDataConfig,
        data_dir: str | Path | None = None,
    ) -> None:
        self.config = config
        self.data_dir = Path(data_dir if data_dir is not None else config.data_dir)
        self.logger = logging.getLogger(__name__)
        self._rng = random.Random(config.random_seed)

        self.first_names = [
            "JOHN",
            "MARY",
            "JAMES",
            "PATRICIA",
            "ROBERT",
            "JENNIFER",
            "MICHAEL",
            "LINDA",
            "WILLIAM",
            "ELIZABETH",
            "DAVID",
            "BARBARA",
            "RICHARD",
            "SUSAN",
            "JOSEPH",
            "JESSICA",
            "THOMAS",
            "SARAH",
            "CHARLES",
            "KAREN",
            "CHRISTOPHER",
            "NANCY",
            "DANIEL",
            "LISA",
        ]
        self.last_names = [
            "SMITH",
            "JOHNSON",
            "WILLIAMS",
            "BROWN",
            "JONES",
            "GARCIA",
            "MILLER",
            "DAVIS",
            "RODRIGUEZ",
            "MARTINEZ",
            "HERNANDEZ",
            "LOPEZ",
            "GONZALEZ",
            "WILSON",
            "ANDERSON",
            "THOMAS",
            "TAYLOR",
            "MOORE",
            "JACKSON",
            "MARTIN",
            "LEE",
            "PEREZ",
            "THOMPSON",
            "WHITE",
        ]
        self.street_names = [
            "MAIN ST",
            "FIRST ST",
            "SECOND ST",
            "THIRD ST",
            "PARK AVE",
            "OAK ST",
            "PINE ST",
            "MAPLE ST",
            "CEDAR ST",
            "ELM ST",
            "WASHINGTON ST",
            "LINCOLN ST",
            "MADISON ST",
            "JEFFERSON ST",
            "FRANKLIN ST",
            "CHURCH ST",
            "MILL ST",
            "SCHOOL ST",
            "HIGH ST",
        ]

    def generate_customer_data(self, customer_number: int) -> dict[str, Any]:
        """Generate random customer data equivalent to COBOL BANKDATA logic."""
        first_name = self._rng.choice(self.first_names)
        last_name = self._rng.choice(self.last_names)
        full_name = f"{first_name} {last_name}"

        house_number = self._rng.randint(1, 9999)
        street_name = self._rng.choice(self.street_names)
        address = f"{house_number} {street_name}"

        phone = (
            f"{self._rng.randint(100, 999)}-"
            f"{self._rng.randint(100, 999)}-"
            f"{self._rng.randint(1000, 9999)}"
        )
        credit_score = self._rng.randint(300, 850)

        # Date of birth (18-80 years old).
        birth_year = datetime.now().year - self._rng.randint(18, 80)
        birth_month = self._rng.randint(1, 12)
        birth_day = self._rng.randint(1, 28)  # Safe day for all months.
        date_of_birth = date(birth_year, birth_month, birth_day)

        # Review date within the last year.
        review_date = date.today() - timedelta(days=self._rng.randint(0, 365))
        timestamp = datetime.now().isoformat()

        return {
            "eyecatcher": "CUST",
            "customer_number": f"{customer_number:010d}",
            "customer_name": full_name,
            "customer_address": address,
            "customer_phone": phone,
            "customer_credit_score": credit_score,
            "customer_review_date": review_date.isoformat(),
            "date_of_birth": date_of_birth.isoformat(),
            "created_timestamp": timestamp,
            "last_modified": timestamp,
        }

    def create_record_data(self, customer_data: dict[str, Any]) -> str:
        """Create the fixed-width record equivalent to the COBOL structure."""
        record = {
            "eyecatcher": str(customer_data["eyecatcher"]).ljust(4)[:4],
            "customer_number": str(customer_data["customer_number"]).ljust(10)[:10],
            "customer_name": str(customer_data["customer_name"]).ljust(50)[:50],
            "customer_address": str(customer_data["customer_address"]).ljust(80)[:80],
            "customer_phone": str(customer_data["customer_phone"]).ljust(15)[:15],
            "credit_score": str(customer_data["customer_credit_score"]).rjust(3)[:3],
            "review_date": str(customer_data["customer_review_date"]).ljust(10)[:10],
            "date_of_birth": str(customer_data["date_of_birth"]).ljust(10)[:10],
            "filler": " " * 77,
        }
        return json.dumps(record, separators=(",", ":"))

    def run_data_generation(self) -> bool:
        """Generate customer rows.

        Equivalent to: RUN PROGRAM(BANKDATA) PLAN(@DB2_PLAN@)
        PARM('1,10000,1,1000000000000000')
        """
        records_processed = 0
        try:
            db_path = self.data_dir / "customer.db"
            with closing(sqlite3.connect(db_path)) as conn:
                cursor = conn.cursor()
                start_num = self.config.start_customer_number
                end_num = self.config.final_customer_number
                increment = self.config.customer_increment

                self.logger.info(
                    "Starting data generation: %s to %s, increment %s",
                    start_num,
                    end_num,
                    increment,
                )

                for customer_num in range(start_num, end_num + 1, increment):
                    customer_data = self.generate_customer_data(customer_num)
                    record_data = self.create_record_data(customer_data)
                    cursor.execute(
                        """
                        INSERT OR REPLACE INTO customer (
                            eyecatcher, customer_number, customer_name, customer_address,
                            customer_phone, customer_credit_score, customer_review_date,
                            date_of_birth, created_timestamp, last_modified, record_data
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            customer_data["eyecatcher"],
                            customer_data["customer_number"],
                            customer_data["customer_name"],
                            customer_data["customer_address"],
                            customer_data["customer_phone"],
                            customer_data["customer_credit_score"],
                            customer_data["customer_review_date"],
                            customer_data["date_of_birth"],
                            customer_data["created_timestamp"],
                            customer_data["last_modified"],
                            record_data,
                        ),
                    )
                    records_processed += 1
                    if records_processed % 1000 == 0:
                        conn.commit()
                        self.logger.info("Processed %s customer records...", records_processed)

                conn.commit()

            self.logger.info(
                "Data generation completed successfully. %s records processed.",
                records_processed,
            )
            return True
        except (OSError, sqlite3.Error) as exc:
            self.logger.error("Data generation failed: %s", exc)
            return False


class BankDataSetup:
    """Orchestrate the entire BANKDATA.JCL equivalent process."""

    def __init__(
        self,
        config_overrides: dict[str, Any] | None = None,
        *,
        log_file: str | Path | None = "bankdata_setup.log",
    ) -> None:
        self.logger = logging.getLogger(__name__)
        if not self.logger.handlers:
            self.logger.setLevel(logging.INFO)
            self.logger.propagate = False
            formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
            stream_handler = logging.StreamHandler(sys.stdout)
            stream_handler.setFormatter(formatter)
            self.logger.addHandler(stream_handler)
            if log_file is not None:
                file_handler = logging.FileHandler(log_file)
                file_handler.setFormatter(formatter)
                self.logger.addHandler(file_handler)

        self.config = BankDataConfig()
        if config_overrides:
            for key, value in config_overrides.items():
                if hasattr(self.config, key):
                    setattr(self.config, key, value)

        self.logger.info("CBSA Banking Data Setup - Python Version")
        self.logger.info("Configuration: %s", self.config)

        self.vsam_manager = VSAMFileManager(self.config)
        self.data_generator = BankDataGenerator(self.config)

    def run_bankdat0_step(self) -> bool:
        """Equivalent to ``//BANKDAT0 EXEC PGM=IDCAMS``."""
        self.logger.info("=== BANKDAT0 Step: ABNDFILE Setup ===")
        if not self.vsam_manager.delete_dataset("ABNDFILE"):
            return False
        if not self.vsam_manager.define_abndfile_cluster():
            return False
        self.logger.info("BANKDAT0 step completed successfully")
        return True

    def run_bankdat1_step(self) -> bool:
        """Equivalent to ``//BANKDAT1 EXEC PGM=IDCAMS``."""
        self.logger.info("=== BANKDAT1 Step: CUSTOMER File Setup ===")
        if not self.vsam_manager.delete_dataset("CUSTOMER"):
            return False
        if not self.vsam_manager.define_customer_cluster():
            return False
        self.logger.info("BANKDAT1 step completed successfully")
        return True

    def run_bankdat5_step(self) -> bool:
        """Equivalent to ``//BANKDAT5 EXEC PGM=IKJEFT01``."""
        self.logger.info("=== BANKDAT5 Step: Data Generation ===")
        if not self.data_generator.run_data_generation():
            return False
        self.logger.info("BANKDAT5 step completed successfully")
        return True

    def run_complete_setup(self) -> bool:
        """Execute all JCL steps in sequence."""
        try:
            self.logger.info("Starting complete CBSA Banking Data Setup...")
            steps: list[tuple[str, Callable[[], bool]]] = [
                ("BANKDAT0", self.run_bankdat0_step),
                ("BANKDAT1", self.run_bankdat1_step),
                ("BANKDAT5", self.run_bankdat5_step),
            ]
            for step_name, step_function in steps:
                self.logger.info("Executing %s step...", step_name)
                if not step_function():
                    self.logger.error("%s step failed!", step_name)
                    return False
                self.logger.info("%s step completed successfully", step_name)
            self.logger.info("CBSA Banking Data Setup completed successfully!")
            self.print_summary()
            return True
        except (OSError, sqlite3.Error) as exc:
            self.logger.error("Setup failed with exception: %s", exc)
            return False

    def print_summary(self) -> None:
        """Print setup summary equivalent to JCL job completion."""
        self.logger.info("=" * 60)
        self.logger.info("CBSA BANKING DATA SETUP SUMMARY")
        self.logger.info("=" * 60)
        self.logger.info("Bank Prefix: %s", self.config.bank_prefix)
        self.logger.info("Data Directory: %s", self.vsam_manager.data_dir)
        self.logger.info(
            "Customer Records: %s to %s",
            self.config.start_customer_number,
            self.config.final_customer_number,
        )
        self.logger.info("Random Seed: %s", self.config.random_seed)

        try:
            db_path = self.vsam_manager.data_dir / "customer.db"
            if db_path.exists():
                with closing(sqlite3.connect(db_path)) as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT COUNT(*) FROM customer")
                    row = cursor.fetchone()
                    count = row[0] if row is not None else 0
                    self.logger.info("Total Customer Records Created: %s", count)
        except (OSError, sqlite3.Error) as exc:
            self.logger.warning("Could not verify record count: %s", exc)

        self.logger.info("=" * 60)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the JCL-equivalent setup and return a process exit code."""
    parser = argparse.ArgumentParser(
        description="CBSA Banking Data Setup - Python Equivalent of BANKDATA.JCL"
    )
    parser.add_argument("--start-customer", type=int, default=1, help="Starting customer")
    parser.add_argument("--end-customer", type=int, default=10000, help="Final customer")
    parser.add_argument("--increment", type=int, default=1, help="Customer increment")
    parser.add_argument(
        "--seed",
        type=int,
        default=1000000000000000,
        help="Random number seed",
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default="./data",
        help="Data directory path",
    )
    parser.add_argument(
        "--bank-prefix",
        type=str,
        default="CBSA.CICSBSA",
        help="Bank dataset prefix",
    )
    args = parser.parse_args(argv)

    config_overrides = {
        "start_customer_number": args.start_customer,
        "final_customer_number": args.end_customer,
        "customer_increment": args.increment,
        "random_seed": args.seed,
        "bank_prefix": args.bank_prefix,
        "data_dir": args.data_dir,
    }

    setup = BankDataSetup(config_overrides)
    if setup.run_complete_setup():
        print("\n✅ CBSA Banking Data Setup completed successfully!")
        return 0

    print("\n❌ CBSA Banking Data Setup failed!")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
