"""Point-in-time Nifty 500 universe registry (ISIN-keyed, SQLite-backed).

This module stores index membership intervals and exposes date-scoped lookups:
`universe_isins_at_date(as_of)` and `universe_symbols_at_date(as_of)`.

CSV import schema:
  isin,symbol,fyers_symbol,effective_from,effective_to,index_name
"""
from __future__ import annotations

import argparse
import csv
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

DB_PATH = Path("~/.trader_zex/data/momentum_universe.sqlite").expanduser()
DEFAULT_INDEX = "NIFTY 500"


@dataclass(frozen=True)
class UniverseMember:
    isin: str
    symbol: str
    fyers_symbol: str
    effective_from: date
    effective_to: date | None
    index_name: str = DEFAULT_INDEX


def _connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Path = DB_PATH) -> None:
    with _connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS securities (
                isin TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                fyers_symbol TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS memberships (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                index_name TEXT NOT NULL,
                isin TEXT NOT NULL,
                effective_from TEXT NOT NULL,
                effective_to TEXT,
                FOREIGN KEY (isin) REFERENCES securities(isin)
            );

            CREATE INDEX IF NOT EXISTS idx_memberships_lookup
            ON memberships(index_name, effective_from, effective_to, isin);
            """
        )


def _parse_date(raw: str) -> date:
    return datetime.strptime(raw, "%Y-%m-%d").date()


def import_members_csv(csv_path: Path, db_path: Path = DB_PATH) -> int:
    init_db(db_path)
    imported = 0
    with _connect(db_path) as conn:
        with csv_path.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            required = {"isin", "symbol", "fyers_symbol", "effective_from"}
            missing = required - set(reader.fieldnames or [])
            if missing:
                raise ValueError(f"Missing required CSV columns: {sorted(missing)}")

            for row in reader:
                isin = (row.get("isin") or "").strip().upper()
                symbol = (row.get("symbol") or "").strip().upper()
                fyers_symbol = (row.get("fyers_symbol") or "").strip().upper()
                effective_from = (row.get("effective_from") or "").strip()
                effective_to = (row.get("effective_to") or "").strip() or None
                index_name = (row.get("index_name") or DEFAULT_INDEX).strip()
                if not isin or not symbol or not fyers_symbol or not effective_from:
                    continue

                conn.execute(
                    """
                    INSERT INTO securities (isin, symbol, fyers_symbol)
                    VALUES (?, ?, ?)
                    ON CONFLICT(isin) DO UPDATE SET
                        symbol=excluded.symbol,
                        fyers_symbol=excluded.fyers_symbol
                    """,
                    (isin, symbol, fyers_symbol),
                )

                conn.execute(
                    """
                    INSERT INTO memberships (index_name, isin, effective_from, effective_to)
                    VALUES (?, ?, ?, ?)
                    """,
                    (index_name, isin, effective_from, effective_to),
                )
                imported += 1
    return imported


def universe_isins_at_date(as_of: date, index_name: str = DEFAULT_INDEX, db_path: Path = DB_PATH) -> list[str]:
    init_db(db_path)
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT m.isin
            FROM memberships m
            WHERE m.index_name = ?
              AND date(m.effective_from) <= date(?)
              AND (m.effective_to IS NULL OR date(m.effective_to) >= date(?))
            ORDER BY m.isin
            """,
            (index_name, as_of.isoformat(), as_of.isoformat()),
        ).fetchall()
    return [str(r["isin"]) for r in rows]


def universe_symbols_at_date(
    as_of: date,
    index_name: str = DEFAULT_INDEX,
    db_path: Path = DB_PATH,
) -> list[str]:
    init_db(db_path)
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT s.fyers_symbol
            FROM memberships m
            JOIN securities s ON s.isin = m.isin
            WHERE m.index_name = ?
              AND date(m.effective_from) <= date(?)
              AND (m.effective_to IS NULL OR date(m.effective_to) >= date(?))
            ORDER BY s.fyers_symbol
            """,
            (index_name, as_of.isoformat(), as_of.isoformat()),
        ).fetchall()
    return [str(r["fyers_symbol"]) for r in rows]


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Momentum point-in-time universe registry")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="Initialize the SQLite registry")

    p_import = sub.add_parser("import-csv", help="Import PIT constituents from CSV")
    p_import.add_argument("--csv", required=True, help="CSV with isin,symbol,fyers_symbol,effective_from,...")

    p_isins = sub.add_parser("isins-at-date", help="Query ISIN universe at date")
    p_isins.add_argument("--date", required=True, help="YYYY-MM-DD")

    p_symbols = sub.add_parser("symbols-at-date", help="Query Fyers symbols at date")
    p_symbols.add_argument("--date", required=True, help="YYYY-MM-DD")

    args = parser.parse_args()

    if args.cmd == "init":
        init_db()
        print(f"Initialized {DB_PATH}")
        return

    if args.cmd == "import-csv":
        count = import_members_csv(Path(args.csv).expanduser())
        print(f"Imported {count} membership rows into {DB_PATH}")
        return

    if args.cmd == "isins-at-date":
        as_of = _parse_date(args.date)
        isins = universe_isins_at_date(as_of)
        for isin in isins:
            print(isin)
        print(f"Total ISINs: {len(isins)}")
        return

    if args.cmd == "symbols-at-date":
        as_of = _parse_date(args.date)
        symbols = universe_symbols_at_date(as_of)
        for symbol in symbols:
            print(symbol)
        print(f"Total symbols: {len(symbols)}")


if __name__ == "__main__":
    _cli()
