import asyncio
import sys
import traceback
from datetime import datetime

from config import AppConfig, setup_logging, DB_FILE
from client import BitgetClient, BybitClient
from repository import DatabaseRepository
from service import DataFetchService

async def main():
    logger = None
    repo = None
    try:
        # 1. Configuration
        config = AppConfig()
        print(f"{config.exchange} 非同期データ取得・保存バッチを開始 - {datetime.now().isoformat()}")

        # 2. Logging
        logger = setup_logging(config)

        # 3. Repository
        repo = DatabaseRepository(DB_FILE, logger)

        # 4. API Client
        if config.exchange == "bybit":
            client = BybitClient(config.base_url, logger)
        elif config.exchange == "bitget":
            client = BitgetClient(config.base_url, logger, config.bitget_product_type)
        else:
            raise ValueError("EXCHANGE must be either 'bybit' or 'bitget'")

        # 5. Service
        service = DataFetchService(client, repo, config, logger)

        while True:
            await service.fetch_and_store_data()

            sleep_seconds = config.fetch_interval_seconds
            logger.info(f"{sleep_seconds}秒後に次のサイクルを実行します。")
            await asyncio.sleep(sleep_seconds)

    except (KeyboardInterrupt, asyncio.CancelledError):
        print("プログラムが手動で停止されました。")
    except Exception as e:
        print(f"致命的なエラーが発生したため、プログラムを終了します: {e}", file=sys.stderr)
        if logger:
            logger.critical(f"致命的なエラー: {e}", exc_info=True)
        traceback.print_exc()
        sys.exit(1)
    finally:
        if repo:
            repo.close()

if __name__ == "__main__":
    asyncio.run(main())
