from pydantic import BaseModel, Field
from typing import List, Optional

class FundingInfo(BaseModel):
    """資金調達率に関する情報"""
    rate: float = Field(..., description="資金調達率")
    direction: str = Field(..., description="資金調達率の方向 (positive, negative, neutral)")
    utilization: Optional[float] = Field(None, description="資金調達率の利用率 (rate / cap|floor)。rateが0の場合は0。")

class ConstraintsInfo(BaseModel):
    """資金調達の制約に関する情報"""
    interval_hours: Optional[int] = Field(None, description="資金調達間隔 (時間単位)")
    cap: Optional[float] = Field(None, description="資金調達率の上限")
    floor: Optional[float] = Field(None, description="資金調達率の下限")

class FundingRateData(BaseModel):
    """Funding Rateデータ本体"""
    symbol: str = Field(..., description="銘柄シンボル")
    funding_ts: int = Field(..., description="資金調達率のタイムスタンプ (ミリ秒)")
    next_funding_ts: Optional[int] = Field(None, description="次の資金調達時刻 (ミリ秒)")
    funding: FundingInfo
    constraints: ConstraintsInfo

    class Config:
        from_attributes = True
        populate_by_name = True # Allow population by field name or alias

class FundingRateResponse(BaseModel):
    """Funding Rate APIレスポンス全体"""
    count: int = Field(..., description="返されたデータ件数")
    data: List[FundingRateData]

class ExtremeContinuityStats(BaseModel):
    """極端なFunding Rateの継続性に関する統計指標"""
    consecutive_hit_rate: float = Field(..., description="連続ヒット継続率: 直近N回のうち、閾値超えが連続した回数の割合。")
    total_hit_rate: float = Field(..., description="有効区間内継続率: 直近N回のうち、閾値超えが発生した全回数の割合。")
    average_run_length: float = Field(..., description="平均ラン長: 閾値超え状態が連続した期間（ラン）の平均長。")

class ExtremeContinuityResponse(BaseModel):
    """極端なFunding Rateの継続性分析APIのレスポンス"""
    symbol: str = Field(..., description="分析対象の銘柄シンボル")
    threshold: float = Field(..., description="分析に使用した閾値")
    lookback: int = Field(..., description="分析対象の履歴件数")
    stats: ExtremeContinuityStats = Field(..., description="継続性に関する統計指標")
    history: List[FundingRateData] = Field(..., description="分析に使用されたFunding Rateの履歴データ")

class ErrorDetail(BaseModel):
    code: str
    message: str

class ErrorResponse(BaseModel):
    error: ErrorDetail
