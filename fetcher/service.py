import logging
import time
import asyncio
from typing import List, Dict, Any, Protocol, Optional
import aiohttp

from repository import DatabaseRepository
from config import AppConfig

class FundingRateClient(Protocol):
    timeout: aiohttp.ClientTimeout

    async def get_all_linear_symbols(self, session: aiohttp.ClientSession) -> List[str]:
        ...

    async def get_tickers(self, session: aiohttp.ClientSession) -> Dict[str, Dict[str, Any]]:
        ...

    async def get_funding_history(self, session: aiohttp.ClientSession, symbol: str, limit: int = 200) -> Optional[List[Dict[str, Any]]]:
        ...

class DataFetchService:
    def __init__(self, client: FundingRateClient, repository: DatabaseRepository, config: AppConfig, logger: logging.Logger):
        self.client = client
        self.repository = repository
        self.config = config
        self.logger = logger

    async def fetch_and_store_data(self):
        start_time = time.time()
        self.logger.info("====== 新しいデータ取得サイクルを開始 ======")

        async with aiohttp.ClientSession(timeout=self.client.timeout) as session:
            symbols = await self.client.get_all_linear_symbols(session)
            if not symbols:
                self.logger.error("銘柄シンボルが取得できず、データ取得をスキップします。")
                return

            tickers = await self.client.get_tickers(session)
            if not tickers:
                self.logger.warning("ティッカー情報が取得できませんでした。一部データが欠落する可能性があります。")

            await self._fetch_and_store_funding_rates(session, symbols, tickers)

        end_time = time.time()
        self.logger.info(f"====== データ取得サイクル完了 (所要時間: {end_time - start_time:.2f}秒) ======")

    async def _fetch_and_store_funding_rates(
        self, 
        session: aiohttp.ClientSession, 
        symbols: List[str],
        tickers: Dict[str, Dict[str, Any]]
    ):
        """ Funding Rateを取得し、ティッカー情報と結合してデータベースに保存する """
        self.logger.info(f"--- Funding Rateの取得を開始 (履歴: {self.config.funding_rate_history_limit}件) ---")
        all_records_to_upsert = []
        
        sem = asyncio.Semaphore(self.config.concurrency_limit)

        async def fetch_one_funding_rate(symbol: str):
            async with sem:
                return await self.client.get_funding_history(session, symbol, limit=self.config.funding_rate_history_limit)
        
        tasks = [fetch_one_funding_rate(symbol) for symbol in symbols]
        results = await asyncio.gather(*tasks)

        for history_list in results:
            if not history_list:
                continue

            symbol = history_list[0]["symbol"]
            ticker_info = tickers.get(symbol, {})
            
            # Log high funding rate for the latest record
            latest_record = history_list[0]
            if abs(latest_record["funding_rate"]) >= self.config.funding_rate_threshold:
                self.logger.info(
                    f"異常金利候補を検知: {symbol}, Rate: {latest_record['funding_rate']:+.5%}"
                )

            for i, record in enumerate(history_list):
                # Only the latest historical record gets the live next_funding_time
                next_funding_time = ticker_info.get("next_funding_time") if i == 0 else None
                
                all_records_to_upsert.append((
                    record["symbol"],
                    record["funding_rate"],
                    record["funding_rate_timestamp"],
                    next_funding_time,
                    ticker_info.get("funding_interval"),
                    ticker_info.get("funding_rate_cap"),
                    ticker_info.get("funding_rate_floor"),
                ))
        
        if all_records_to_upsert:
            self.repository.upsert_funding_rate_data(all_records_to_upsert)
            self.logger.info(f"{len(all_records_to_upsert)}件のFunding Rateレコードを保存/更新しました。")
        else:
            self.logger.info("保存対象のFunding Rateは見つかりませんでした。")
        self.logger.info("--- Funding Rateの取得が完了 ---")
