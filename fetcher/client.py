import aiohttp
import asyncio
import logging
from typing import List, Any, Optional, Dict

class BybitClient:
    def __init__(self, base_url: str, logger: logging.Logger):
        self.base_url = base_url
        self.logger = logger
        self.timeout = aiohttp.ClientTimeout(total=10)

    async def get_all_linear_symbols(self, session: aiohttp.ClientSession) -> List[str]:
        """Get all tradable linear symbols (USDT perpetuals)."""
        url = f"{self.base_url}/v5/market/instruments-info"
        symbols, cursor = [], ""
        self.logger.info("全Linear銘柄(USDT無期限)のシンボルを取得中...")
        while True:
            params = {"category": "linear", "status": "Trading", "limit": 1000, "cursor": cursor}
            try:
                async with session.get(url, params={k: v for k, v in params.items() if v}) as response:
                    response.raise_for_status()
                    data = await response.json()
                    if data.get("retCode") != 0:
                        self.logger.error(f"銘柄情報取得APIエラー: {data.get('retMsg')}")
                        break
                    
                    result_list = data.get("result", {}).get("list", [])
                    symbols.extend([item["symbol"] for item in result_list if item.get("symbol", "").endswith("USDT")])
                    
                    cursor = data.get("result", {}).get("nextPageCursor", "")
                    if not cursor:
                        break
                    await asyncio.sleep(0.1)
            except aiohttp.ClientError as e:
                self.logger.error(f"銘柄シンボル取得リクエストエラー: {e}")
                return []
        self.logger.info(f"合計 {len(symbols)} の取引可能なLinear銘柄を発見")
        return symbols

    async def get_tickers(self, session: aiohttp.ClientSession) -> Dict[str, Dict[str, Any]]:
        """Get all linear tickers and return a dictionary keyed by symbol."""
        url = f"{self.base_url}/v5/market/tickers"
        params = {"category": "linear"}
        self.logger.info("全Linear銘柄のティッカー情報を取得中...")
        try:
            async with session.get(url, params=params) as response:
                response.raise_for_status()
                data = await response.json()
                if data.get("retCode") == 0:
                    ticker_list = data.get("result", {}).get("list", [])
                    ticker_map = {}
                    for item in ticker_list:
                        symbol = item.get("symbol")
                        if not symbol:
                            continue
                        
                        try:
                            ticker_data = {}
                            
                            next_funding_time_str = item.get("nextFundingTime")
                            if next_funding_time_str:
                                ticker_data["next_funding_time"] = int(next_funding_time_str)

                            funding_interval_hour_str = item.get("fundingIntervalHour")
                            if funding_interval_hour_str:
                                ticker_data["funding_interval"] = int(funding_interval_hour_str)

                            funding_cap_str = item.get("fundingCap")
                            if funding_cap_str:
                                cap = float(funding_cap_str)
                                ticker_data["funding_rate_cap"] = cap
                                ticker_data["funding_rate_floor"] = -cap
                            
                            if ticker_data:
                                ticker_map[symbol] = ticker_data
                        except (ValueError, TypeError) as e:
                             self.logger.warning(f"{symbol} のティッカー情報のパースに失敗しました: {e}")
                    self.logger.info(f"{len(ticker_map)} 件のティッカー情報を取得しました。")
                    return ticker_map
                else:
                    self.logger.error(f"ティッカー情報取得APIエラー: {data.get('retMsg')}")
                    return {}
        except aiohttp.ClientError as e:
            self.logger.error(f"ティッカー情報取得リクエストエラー: {e}")
            return {}

    async def get_funding_history(self, session: aiohttp.ClientSession, symbol: str, limit: int = 200) -> Optional[List[Dict[str, Any]]]:
        """指定された銘柄の資金調達率の履歴を取得し、パースして返す。"""
        params = {"category": "linear", "symbol": symbol, "limit": limit}
        url = f"{self.base_url}/v5/market/funding/history"
        try:
            async with session.get(url, params=params) as response:
                response.raise_for_status()
                data = await response.json()
                if data.get("retCode") == 0:
                    history_list = data.get("result", {}).get("list", [])
                    if not history_list:
                        return []
                    
                    processed_list = []
                    for item in history_list:
                        try:
                            processed_list.append({
                                "symbol": item["symbol"],
                                "funding_rate": float(item["fundingRate"]),
                                "funding_rate_timestamp": int(item["fundingRateTimestamp"]),
                            })
                        except (ValueError, TypeError, KeyError) as e:
                            self.logger.warning(f"シンボル {symbol} のFunding Rateレコードのパースに失敗しました。 スキップします。 record={item}, error={e}")
                    return processed_list
                else:
                    self.logger.warning(f"{symbol} のFunding Rate履歴取得でAPIエラー: {data.get('retMsg')}")
                    return None
        except aiohttp.ClientError as e:
            self.logger.warning(f"{symbol} のFunding Rate履歴取得でリクエストエラー: {e}")
            return None
        except Exception as e:
            self.logger.error(f"{symbol} のFunding Rate履歴処理で予期せぬエラー: {e}")
            return None
