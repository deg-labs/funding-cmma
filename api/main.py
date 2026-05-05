from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy.orm import Session
from typing import List, Optional
from enum import Enum

import crud
import schemas
from database import engine, get_db, init_db # init_dbをインポート

app = FastAPI(
    title="CMMA Funding Rate API",
    description="取引所の異常なFunding Rateを取得するAPI",
    version="3.0.0",
    docs_url="/funding-rates/docs",
    openapi_url="/funding-rates/openapi.json"
)

@app.on_event("startup")
def on_startup():
    init_db() # 起動時にデータベースを初期化

# --- エラーハンドリング ---
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content=schemas.ErrorResponse(
            error=schemas.ErrorDetail(
                code=exc.headers.get("X-Error-Code", "HTTP_EXCEPTION"),
                message=exc.detail
            )
        ).model_dump(),
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    # バリデーションエラーのメッセージを整形
    error_messages = []
    for error in exc.errors():
        field = "->".join(map(str, error['loc']))
        message = error['msg']
        error_messages.append(f"[{field}]: {message}")
    
    return JSONResponse(
        status_code=422,
        content=schemas.ErrorResponse(
            error=schemas.ErrorDetail(
                code="INVALID_INPUT",
                message=", ".join(error_messages)
            )
        ).model_dump(),
    )

# --- パラメータ用Enum ---
class Direction(str, Enum):
    positive = "positive"
    negative = "negative"
    both = "both"

class SortBy(str, Enum):
    funding_rate_desc = "funding_rate_desc"
    funding_rate_asc = "funding_rate_asc"
    funding_abs_desc = "funding_abs_desc"
    symbol_asc = "symbol_asc"
    utilization_desc = "utilization_desc"


# --- エンドポイント ---
@app.get(
    "/funding-rates",
    response_model=schemas.FundingRateResponse,
    summary="条件に基づき資金調達率データを取得",
    response_description="条件に一致した銘柄の資金調達率データ"
)
def get_funding_rates(
    db: Session = Depends(get_db),
    threshold: float = Query(..., gt=0, description="Funding Rateの閾値(絶対値)。この値以上の|rate|を持つ銘柄が対象。"),
    direction: Direction = Query(Direction.both, description="Funding Rateの方向 (`positive` or `negative`) でフィルタします。"),
    sort: SortBy = Query(SortBy.funding_abs_desc, description="結果のソート順。デフォルトは絶対値の降順。"),
    limit: int = Query(100, gt=0, le=500, description="取得する最大件数。"),
    utilization_gte: Optional[float] = Query(None, ge=0, description="Funding Rateの利用率（派生値）の最小値。例: 0.5 (50%以上)"),
):
    """
    **大きさ(`threshold`)と方向(`direction`)でFunding Rateをフィルタリングします。**

    - **threshold**: Funding Rateの「大きさ」を指定します (常に正の値)。
    - **direction**: `positive` (Rate > 0) または `negative` (Rate < 0) で方向を指定します。
    - **sort**: 多様な基準でソートします。`funding_abs_desc` (絶対値降順) がデフォルトです。
    - **utilization_gte**: Funding Rateが取引所の上限/下限に対してどれだけ使われているか（0.0〜1.0）でフィルタします。
    """
    results = crud.get_funding_rates(
        db=db,
        threshold=threshold,
        direction=direction.value,
        sort=sort.value,
        limit=limit,
        utilization_gte=utilization_gte
    )

    funding_rate_data = [
        schemas.FundingRateData(
            symbol=rate.symbol,
            funding_ts=rate.funding_rate_timestamp,
            next_funding_ts=rate.next_funding_time,
            funding=schemas.FundingInfo(
                rate=rate.funding_rate,
                direction="positive" if rate.funding_rate > 0 else "negative" if rate.funding_rate < 0 else "neutral",
                utilization=round(utilization, 7) if (utilization := getattr(rate, 'funding_utilization', None)) is not None else None
            ),
            constraints=schemas.ConstraintsInfo(
                interval_hours=rate.funding_interval,
                cap=rate.funding_rate_cap,
                floor=rate.funding_rate_floor
            )
        ) for rate in results
    ]
    return schemas.FundingRateResponse(count=len(funding_rate_data), data=funding_rate_data)


@app.get(
    "/funding-rates/extreme-continuity",
    response_model=schemas.ExtremeContinuityResponse,
    summary="極端な資金調達率の継続性を分析",
    response_description="指定した銘柄のFunding Rateが閾値を超えた状態の継続性に関する統計データ"
)
def get_extreme_continuity(
    db: Session = Depends(get_db),
    symbol: str = Query(..., description="分析対象の銘柄シンボル (例: BTCUSDT)"),
    threshold: float = Query(..., gt=0, description="「極端」と判断するためのFunding Rateの閾値 (絶対値)。例: 0.0002"),
    lookback: int = Query(..., gt=1, le=200, description="分析対象とする最新の履歴件数。"),
    direction: Direction = Query(Direction.both, description="分析対象とするFunding Rateの方向 (`positive` or `negative`)。")
):
    """
    指定された銘柄のFunding Rate履歴を分析し、**極端な状態の継続性**に関する指標を返します。

    - **symbol**: 分析したい銘柄のシンボル。
    - **threshold**: `|Funding Rate| >= threshold` となる状態を「極端」と定義します。
    - **lookback**: 最新の履歴から何件を分析対象とするか。
    - **direction**: `positive` または `negative` を指定して、分析対象を特定の方向のFRに限定します。

    返される統計指標:
    - **連続ヒット継続率**: 直近で極端な状態が連続した回数の割合。
    - **有効区間内継続率**: 期間全体で極端な状態が発生した回数の割合。
    - **平均ラン長**: 極端な状態が連続した期間の平均的な長さ。
    """
    stats, history = crud.get_extreme_continuity_stats(
        db=db,
        symbol=symbol,
        threshold=threshold,
        lookback=lookback,
        direction=direction.value
    )

    if not history:
        raise HTTPException(status_code=404, detail=f"No funding rate history found for symbol '{symbol}' with lookback={lookback}.")

    history_data = [
        schemas.FundingRateData(
            symbol=item.symbol,
            funding_ts=item.funding_rate_timestamp,
            next_funding_ts=item.next_funding_time,
            funding=schemas.FundingInfo(
                rate=item.funding_rate,
                direction="positive" if item.funding_rate > 0 else "negative" if item.funding_rate < 0 else "neutral",
                utilization=None # このAPIでは計算しない
            ),
            constraints=schemas.ConstraintsInfo(
                interval_hours=item.funding_interval,
                cap=item.funding_rate_cap,
                floor=item.funding_rate_floor
            )
        ) for item in history
    ]

    return schemas.ExtremeContinuityResponse(
        symbol=symbol,
        threshold=threshold,
        lookback=lookback,
        stats=stats,
        history=history_data
    )


@app.get("/", include_in_schema=False)
def read_root():
    return {"message": "Welcome to CMMA Funding Rate API v3. See /docs for details."}
