import sqlite3
import logging
import sys
from pathlib import Path
from typing import List, Tuple

class DatabaseRepository:
    def __init__(self, db_file: Path, logger: logging.Logger):
        self.db_file = db_file
        self.logger = logger
        self.conn = self._setup_database()

    def _setup_database(self) -> sqlite3.Connection:
        """データベース接続をセットアップし、テーブルを作成する"""
        try:
            self.db_file.parent.mkdir(exist_ok=True)
            conn = sqlite3.connect(self.db_file, timeout=10)
            cursor = conn.cursor()
            self.logger.info(f"データベースに接続: {self.db_file}")

            # Create funding_rates table
            self.logger.info("テーブル 'funding_rates' の準備中...")
            cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS funding_rates (
                symbol TEXT NOT NULL,
                funding_rate REAL NOT NULL,
                funding_rate_timestamp INTEGER NOT NULL,
                next_funding_time INTEGER,
                funding_interval INTEGER,
                funding_rate_cap REAL,
                funding_rate_floor REAL,
                created_at INTEGER NOT NULL DEFAULT (strftime('%s', 'now')),
                updated_at INTEGER NOT NULL DEFAULT (strftime('%s', 'now')),
                PRIMARY KEY (symbol, funding_rate_timestamp)
            )
            """)
            conn.commit()
            self.logger.info("テーブルの準備完了。")
            return conn
        except sqlite3.Error as e:
            self.logger.error(f"データベースのセットアップに失敗: {e}")
            sys.exit(1)

    def upsert_funding_rate_data(self, records: List[Tuple]):
        """ Funding Rate データをデータベースにUPSERTする """
        if not records:
            return

        table_name = "funding_rates"
        self.logger.info(f"{len(records)} 件のFunding Rateレコードをテーブル '{table_name}' にUPSERTします...")
        cursor = self.conn.cursor()
        try:
            upsert_sql = f"""
            INSERT INTO {table_name} (
                symbol, funding_rate, funding_rate_timestamp, next_funding_time, 
                funding_interval, funding_rate_cap, funding_rate_floor, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, strftime('%s', 'now'))
            ON CONFLICT(symbol, funding_rate_timestamp) DO UPDATE SET
                funding_rate=excluded.funding_rate,
                next_funding_time=excluded.next_funding_time,
                funding_interval=excluded.funding_interval,
                funding_rate_cap=excluded.funding_rate_cap,
                funding_rate_floor=excluded.funding_rate_floor,
                updated_at=excluded.updated_at
            """
            cursor.executemany(upsert_sql, records)
            self.conn.commit()
            self.logger.info("Funding RateのUPSERTが完了しました。")
        except sqlite3.Error as e:
            self.logger.error(f"Funding RateのDB保存中にエラー: {e}")
            self.conn.rollback()

    def close(self):
        if self.conn:
            self.conn.close()
            self.logger.info("データベース接続をクローズしました。")
