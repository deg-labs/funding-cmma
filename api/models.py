from sqlalchemy import Column, Float, Integer, String
from datetime import datetime
from database import Base

class FundingRate(Base):
    __tablename__ = "funding_rates"

    symbol = Column(String, primary_key=True, index=True)
    funding_rate = Column(Float, nullable=False)
    funding_rate_timestamp = Column(Integer, primary_key=True, index=True)
    next_funding_time = Column(Integer, nullable=True)
    funding_interval = Column(Integer, nullable=True)
    funding_rate_cap = Column(Float, nullable=True)
    funding_rate_floor = Column(Float, nullable=True)
    created_at = Column(Integer, default=lambda: int(datetime.now().timestamp()), nullable=False)
    updated_at = Column(Integer, default=lambda: int(datetime.now().timestamp()), onupdate=lambda: int(datetime.now().timestamp()), nullable=False)
