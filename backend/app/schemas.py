from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderSource(str, Enum):
    MANUAL = "MANUAL"
    STRATEGY = "STRATEGY"


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    email: str
    strategy_api_key: str | None = None


class OrderRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=30)
    side: Side
    quantity: int = Field(gt=0)
    confirm_live: bool = False


class SignalRequest(OrderRequest):
    strategy_name: str = Field(default="python-strategy", min_length=1, max_length=100)
    signal_id: str | None = Field(default=None, max_length=100)


class OrderResponse(BaseModel):
    id: int
    execution_mode: str = "PAPER"
    broker_order_id: str | None
    symbol: str
    instrument_key: str | None = None
    side: str
    quantity: int
    filled_quantity: int = 0
    product: str = "D"
    source: str
    strategy_name: str | None
    status: str
    average_price: float | None
    rejection_reason: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PositionResponse(BaseModel):
    execution_mode: str = "PAPER"
    symbol: str
    quantity: int
    average_price: float
    last_price: float
    market_value: float
    realized_pnl: float
    unrealized_pnl: float
    total_pnl: float


class BrokerRequest(BaseModel):
    broker: str


class StrategyCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9 _-]*$")
    description: str = Field(default="", max_length=240)


class StrategyUpdate(BaseModel):
    status: str = Field(pattern=r"^(ACTIVE|PAUSED)$")


class StrategyResponse(BaseModel):
    id: int
    name: str
    description: str
    status: str
    signal_count: int
    last_signal_at: datetime | None
    created_at: datetime


class StrategyKeyResponse(BaseModel):
    strategy_api_key: str
    message: str
