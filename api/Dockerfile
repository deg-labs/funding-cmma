FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir pip --upgrade
RUN pip install --no-cache-dir -r requirements.txt
RUN apt-get update && apt-get install -y --no-install-recommends patch && rm -rf /var/lib/apt/lists/*

COPY . .

# TODO(temporary): EXCLUDE_TICKERS 対応は build 時 patch 適用で暫定実装。
# 理由: 将来の複数取引所対応で実装競合が起きる可能性があるため、統合実装までの一時対応とする。
RUN patch -p1 < patches/exclude_tickers_todo.patch

EXPOSE 8000

# コンテナ起動時にUvicornサーバーを起動
# --host 0.0.0.0: コンテナ外部からアクセスできるようにする
# --port 8000: EXPOSEで公開したポートでリッスン
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
