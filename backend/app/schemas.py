from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from .scanner.conditions import ComparisonOperator, ConditionField
from .scanner.scanners import RankDirection


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


class UserResponse(BaseModel):
    email: str
    name: str
    created_at: datetime


class ProfileUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=80)
    current_password: str | None = None
    new_password: str | None = Field(default=None, min_length=8, max_length=128)

    @model_validator(mode="after")
    def validate_payload(self):
        if self.new_password and not self.current_password:
            raise ValueError("current_password is required to set a new password")
        if self.name is None and not self.new_password:
            raise ValueError("Provide at least one of name or new_password to update")
        return self


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


class ScannerOperandRequest(BaseModel):
    value: float | None = None
    field: ConditionField | None = None
    multiplier: float = 1.0

    @model_validator(mode="after")
    def validate_operand(self):
        if (self.value is None) == (self.field is None):
            raise ValueError("Provide exactly one of value or field")
        if self.field is None and self.multiplier != 1.0:
            raise ValueError("A literal operand cannot have a multiplier")
        return self


class ScannerConditionRequest(BaseModel):
    left: ConditionField
    operator: ComparisonOperator
    right: ScannerOperandRequest


class ScannerRunRequest(BaseModel):
    preset_key: str | None = Field(default=None, pattern=r"^[a-z0-9_]+$")
    conditions: list[ScannerConditionRequest] = Field(default_factory=list, max_length=10)
    rank_field: ConditionField = ConditionField.PRICE
    rank_direction: RankDirection = RankDirection.DESCENDING
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=10, ge=1, le=100)
    refresh: bool = False
    symbols: list[str] | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def validate_scanner_selection(self):
        if bool(self.preset_key) == bool(self.conditions):
            raise ValueError("Provide either preset_key or custom conditions")
        return self


class SavedScannerCreate(BaseModel):
    name: str = Field(min_length=2, max_length=80, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9 _-]*$")
    preset_key: str | None = Field(default=None, pattern=r"^[a-z0-9_]+$")
    conditions: list[ScannerConditionRequest] = Field(default_factory=list, max_length=10)
    rank_field: ConditionField = ConditionField.PRICE
    rank_direction: RankDirection = RankDirection.DESCENDING

    @model_validator(mode="after")
    def validate_definition(self):
        if bool(self.preset_key) == bool(self.conditions):
            raise ValueError("Provide either preset_key or custom conditions")
        return self


class ScannerAlertCreate(BaseModel):
    saved_scanner_id: int = Field(gt=0)
    name: str = Field(min_length=2, max_length=80, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9 _-]*$")
    minimum_matches: int = Field(default=1, ge=1, le=10000)


class ScannerAlertUpdate(BaseModel):
    enabled: bool | None = None
    minimum_matches: int | None = Field(default=None, ge=1, le=10000)
