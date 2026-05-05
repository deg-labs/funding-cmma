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


class BitgetClient:
    def __init__(self, base_url: str, logger: logging.Logger, product_type: str = "usdt-futures"):
        self.base_url = base_url
        self.logger = logger
        self.product_type = product_type
        self.timeout = aiohttp.ClientTimeout(total=10)

    async def _get_current_funding_rates(self, session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
        """Get current funding rates for all configured Bitget futures contracts."""
        url = f"{self.base_url}/api/v2/mix/market/current-fund-rate"
        params = {"productType": self.product_type}
        try:
            async with session.get(url, params=params) as response:
                response.raise_for_status()
                data = await response.json()
                if data.get("code") != "00000":
                    self.logger.error(f"Bitget Current Funding Rate APIエラー: {data.get('msg')}")
                    return []
                return data.get("data", [])
        except aiohttp.ClientError as e:
            self.logger.error(f"Bitget Current Funding Rateリクエストエラー: {e}")
            return []

    async def get_all_linear_symbols(self, session: aiohttp.ClientSession) -> List[str]:
        """Get all symbols from Bitget current funding rate endpoint."""
        self.logger.info(f"Bitget {self.product_type} のFunding Rate対象シンボルを取得中...")
        current_rates = await self._get_current_funding_rates(session)
        symbols = [
            item["symbol"]
            for item in current_rates
            if item.get("symbol") and item.get("symbol", "").endswith("USDT")
        ]
        self.logger.info(f"合計 {len(symbols)} のBitget Funding Rate対象シンボルを発見")
        return symbols

    async def get_tickers(self, session: aiohttp.ClientSession) -> Dict[str, Dict[str, Any]]:
        """Use Bitget current funding rate data as ticker metadata."""
        self.logger.info("Bitgetの現在Funding Rate情報を取得中...")
        current_rates = await self._get_current_funding_rates(session)
        ticker_map = {}
        for item in current_rates:
            symbol = item.get("symbol")
            if not symbol:
                continue

            try:
                ticker_data = {}

                next_update = item.get("nextUpdate")
                if next_update:
                    ticker_data["next_funding_time"] = int(next_update)

                interval = item.get("fundingRateInterval")
                if interval:
                    ticker_data["funding_interval"] = int(interval)

                max_rate = item.get("maxFundingRate")
                if max_rate is not None:
                    ticker_data["funding_rate_cap"] = float(max_rate)

                min_rate = item.get("minFundingRate")
                if min_rate is not None:
                    ticker_data["funding_rate_floor"] = float(min_rate)

                if ticker_data:
                    ticker_map[symbol] = ticker_data
            except (ValueError, TypeError) as e:
                self.logger.warning(f"{symbol} のBitget Funding Rate情報のパースに失敗しました: {e}")

        self.logger.info(f"{len(ticker_map)} 件のBitget Funding Rate情報を取得しました。")
        return ticker_map

    async def get_funding_history(self, session: aiohttp.ClientSession, symbol: str, limit: int = 100) -> Optional[List[Dict[str, Any]]]:
        """指定されたBitget銘柄の資金調達率履歴を取得し、既存形式に正規化して返す。"""
        url = f"{self.base_url}/api/v2/mix/market/history-fund-rate"
        params = {
            "symbol": symbol,
            "productType": self.product_type,
            "pageSize": min(limit, 100),
        }
        try:
            async with session.get(url, params=params) as response:
                response.raise_for_status()
                data = await response.json()
                if data.get("code") == "00000":
                    history_list = data.get("data", [])
                    processed_list = []
                    for item in history_list:
                        try:
                            processed_list.append({
                                "symbol": item["symbol"],
                                "funding_rate": float(item["fundingRate"]),
                                "funding_rate_timestamp": int(item["fundingTime"]),
                            })
                        except (ValueError, TypeError, KeyError) as e:
                            self.logger.warning(f"シンボル {symbol} のBitget Funding Rateレコードのパースに失敗しました。 スキップします。 record={item}, error={e}")
                    return processed_list

                self.logger.warning(f"{symbol} のBitget Funding Rate履歴取得でAPIエラー: {data.get('msg')}")
                return None
        except aiohttp.ClientError as e:
            self.logger.warning(f"{symbol} のBitget Funding Rate履歴取得でリクエストエラー: {e}")
            return None
        except Exception as e:
            self.logger.error(f"{symbol} のBitget Funding Rate履歴処理で予期せぬエラー: {e}")
            return None
