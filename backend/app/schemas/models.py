from typing import Literal, List, Optional
from pydantic import BaseModel, Field


class StockSymbol(BaseModel):
    symbol: str
    company_name: Optional[str] = None
    sector: Optional[str] = None


class HistoryRow(BaseModel):
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int


class FeatureRow(BaseModel):
    date: str
    close: Optional[float] = None
    sma_10: Optional[float] = None
    ema_10: Optional[float] = None
    rsi: Optional[float] = None
    macd: Optional[float] = None
    next_day_direction: Optional[int] = None


class UploadRequest(BaseModel):
    symbol: str = Field(..., min_length=1)


class TrainRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=30, pattern=r"^[A-Za-z0-9][A-Za-z0-9&._-]{0,29}$")
    model: Literal["ann", "ffnn", "cnn", "rnn", "lstm", "transformer"]
    lookback: int = Field(default=30, ge=10, le=180)
    optimizer: Literal["adam", "sgd", "rmsprop"] = "adam"
    learning_rate: float = Field(default=0.001, gt=0, le=0.1)
    batch_size: int = Field(default=32, ge=8, le=512)
    epochs: int = Field(default=10, ge=1, le=50)
    hidden_units: int = Field(default=64, ge=8, le=512)
    dropout: float = Field(default=0.1, ge=0, lt=1)


class PredictionRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=30, pattern=r"^[A-Za-z0-9][A-Za-z0-9&._-]{0,29}$")
    model: Literal["ann", "ffnn", "cnn", "rnn", "lstm", "transformer"] = "lstm"
    lookback: int = Field(default=30, ge=10, le=180)


class ExperimentRecord(BaseModel):
    id: Optional[int] = None
    model_name: Optional[str] = None
    symbol: Optional[str] = None
    task: Optional[str] = None
    lookback: Optional[int] = None
    optimizer: Optional[str] = None
    learning_rate: Optional[float] = None
    batch_size: Optional[int] = None
    epochs: Optional[int] = None
    training_accuracy: Optional[float] = None
    validation_accuracy: Optional[float] = None
    test_accuracy: Optional[float] = None
    precision: Optional[float] = None
    recall: Optional[float] = None
    f1: Optional[float] = None
    mae: Optional[float] = None
    rmse: Optional[float] = None
    training_time: Optional[float] = None
    parameter_count: Optional[int] = None
