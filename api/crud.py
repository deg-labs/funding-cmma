from sqlalchemy.orm import Session
from typing import List, Optional
from models import FundingRate
from sqlalchemy import func, text, case, literal_column

def get_funding_rates(
    db: Session,
    threshold: float,
    direction: str,
    sort: str,
    limit: int,
    utilization_gte: Optional[float]
) -> List[FundingRate]:
    """
    指定された条件に基づき、最新のFunding Rateを持つ銘柄のリストを取得します。
    """
    # 各シンボルに対する最新のタイムスタンプを特定するサブクエリ
    latest_timestamps_sq = db.query(
        FundingRate.symbol,
        func.max(FundingRate.funding_rate_timestamp).label('latest_timestamp')
    ).group_by(FundingRate.symbol).subquery()

    # funding_utilizationを計算するCASE式
    utilization_expr = case(
        (FundingRate.funding_rate > 0, FundingRate.funding_rate / FundingRate.funding_rate_cap),
        (FundingRate.funding_rate < 0, FundingRate.funding_rate / func.abs(FundingRate.funding_rate_floor)),
        else_=0.0
    ).label('funding_utilization')

    # 最新のFunding Rateレコードを取得するベースクエリ
    query = db.query(FundingRate, utilization_expr).join(
        latest_timestamps_sq,
        (FundingRate.symbol == latest_timestamps_sq.c.symbol) &
        (FundingRate.funding_rate_timestamp == latest_timestamps_sq.c.latest_timestamp)
    )

    # threshold でフィルタリング (大きさ)
    query = query.filter(func.abs(FundingRate.funding_rate) >= threshold)

    # direction でフィルタリング (方向)
    if direction == "positive":
        query = query.filter(FundingRate.funding_rate > 0)
    elif direction == "negative":
        query = query.filter(FundingRate.funding_rate < 0)

    # utilization_gte でフィルタリング
    if utilization_gte is not None:
        query = query.filter(utilization_expr >= utilization_gte)

    # ソート順を決定
    sort_map = {
        "funding_rate_desc": FundingRate.funding_rate.desc(),
        "funding_rate_asc": FundingRate.funding_rate.asc(),
        "funding_abs_desc": func.abs(FundingRate.funding_rate).desc(),
        "symbol_asc": FundingRate.symbol.asc(),
        "utilization_desc": utilization_expr.desc(),
    }
    order_by_clause = sort_map.get(sort, func.abs(FundingRate.funding_rate).desc()) # デフォルトは絶対値降順
    query = query.order_by(order_by_clause)

    # 件数制限
    results = query.limit(limit).all()

    # クエリ結果 (タプル) をオブジェクトにマッピング
    funding_rates_with_utilization = []
    for rate, utilization in results:
        rate.funding_utilization = utilization
        funding_rates_with_utilization.append(rate)

    return funding_rates_with_utilization

from itertools import groupby
from statistics import mean
import schemas

def get_extreme_continuity_stats(db: Session, symbol: str, threshold: float, lookback: int, direction: str) -> (schemas.ExtremeContinuityStats, List[FundingRate]):
    """
    指定された銘柄のFunding Rate履歴を分析し、極端な状態の継続性に関する統計指標を計算します。
    """
    # 1. データ取得
    history = db.query(FundingRate).filter(
        FundingRate.symbol == symbol
    ).order_by(
        FundingRate.funding_rate_timestamp.desc()
    ).limit(lookback).all()

    if not history:
        return schemas.ExtremeContinuityStats(
            consecutive_hit_rate=0.0,
            total_hit_rate=0.0,
            average_run_length=0.0
        ), []
    
    # 履歴は新しい順なので、計算のために古い順に並べ替える
    history.reverse()
    actual_lookback = len(history)

    # 2. 統計計算
    runs = []
    total_hits = 0
    is_extreme = []

    if direction == "positive":
        is_extreme = [h.funding_rate >= threshold for h in history]
        runs = [len(list(g)) for k, g in groupby(is_extreme) if k]
        total_hits = sum(is_extreme)
    elif direction == "negative":
        is_extreme = [h.funding_rate <= -threshold for h in history]
        runs = [len(list(g)) for k, g in groupby(is_extreme) if k]
        total_hits = sum(is_extreme)
    else: # "both"
        is_positive_extreme = [h.funding_rate >= threshold for h in history]
        is_negative_extreme = [h.funding_rate <= -threshold for h in history]
        
        # total_hit_rate と consecutive_hit_rate の計算用
        is_extreme = [p or n for p, n in zip(is_positive_extreme, is_negative_extreme)]
        total_hits = sum(is_extreme)

        # average_run_length は positive と negative のランを別々に計算して結合
        positive_runs = [len(list(g)) for k, g in groupby(is_positive_extreme) if k]
        negative_runs = [len(list(g)) for k, g in groupby(is_negative_extreme) if k]
        runs = positive_runs + negative_runs

    # a. 有効区間内継続率 (Total Hit Rate)
    total_hit_rate = total_hits / actual_lookback if actual_lookback > 0 else 0.0

    # b. 連続ヒット継続率 (Consecutive Hit Rate)
    # is_extremeは古い順なので、末尾から連続するTrueの数を数える
    consecutive_hits = 0
    for flag in reversed(is_extreme):
        if flag:
            consecutive_hits += 1
        else:
            break
    consecutive_hit_rate = consecutive_hits / actual_lookback if actual_lookback > 0 else 0.0

    # c. 平均ラン長 (Average Run Length)
    average_run_length = mean(runs) if runs else 0.0
    
    stats = schemas.ExtremeContinuityStats(
        consecutive_hit_rate=consecutive_hit_rate,
        total_hit_rate=total_hit_rate,
        average_run_length=average_run_length
    )
    
    # historyを元の新しい順に戻して返す
    history.reverse()

    return stats, history
