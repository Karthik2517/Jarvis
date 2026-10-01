import sqlite3

from ..brokers.base import BrokerAdapter
from ..instruments import find_instrument, normalize_symbol
from ..schemas import OrderSource, Side
from .risk import RiskEngine


class ExecutionEngine:
    def __init__(self, broker: BrokerAdapter, risk: RiskEngine | None = None):
        self.broker = broker
        self.risk = risk or RiskEngine()

    def execute(
        self,
        connection: sqlite3.Connection,
        *,
        user_id: int,
        symbol: str,
        side: Side,
        quantity: int,
        source: OrderSource,
        strategy_name: str | None = None,
        signal_id: str | None = None,
    ) -> sqlite3.Row:
        symbol = normalize_symbol(symbol)
        execution_mode = self.broker.name
        instrument = find_instrument(symbol)
        instrument_key = instrument.get("instrument_key") if instrument else None
        position = connection.execute(
            """SELECT * FROM positions
               WHERE user_id = ? AND execution_mode = ? AND symbol = ?""",
            (user_id, execution_mode, symbol),
        ).fetchone()
        current_quantity = int(position["quantity"]) if position else 0

        try:
            price = self.broker.quote(symbol)
        except (ValueError, RuntimeError) as exc:
            return self._rejected(
                connection, user_id, execution_mode, symbol, instrument_key, side, quantity,
                source, strategy_name, signal_id, str(exc)
            )

        decision = self.risk.check(
            side=side, quantity=quantity, price=price, current_quantity=current_quantity
        )
        if not decision.approved:
            return self._rejected(
                connection, user_id, execution_mode, symbol, instrument_key, side, quantity,
                source, strategy_name, signal_id, decision.reason or "Rejected"
            )

        try:
            result = self.broker.place_market_order(symbol, side, quantity)
        except RuntimeError as exc:
            return self._rejected(
                connection, user_id, execution_mode, symbol, instrument_key, side, quantity,
                source, strategy_name, signal_id, str(exc)
            )

        cursor = connection.execute(
            """INSERT INTO orders
               (user_id, execution_mode, broker_order_id, symbol, instrument_key, side, quantity, filled_quantity,
                product, source, strategy_name, signal_id, status, requested_price, average_price)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'D', ?, ?, ?, ?, ?, ?)""",
            (user_id, execution_mode, result.broker_order_id, symbol, instrument_key, side.value, quantity,
             result.filled_quantity, source.value, strategy_name, signal_id, result.status,
             price, result.average_price),
        )
        if result.filled_quantity > 0 and result.average_price is not None:
            self._apply_fill(
                connection, user_id, execution_mode, symbol, instrument_key, side,
                result.filled_quantity, result.average_price, position
            )
        return connection.execute("SELECT * FROM orders WHERE id = ?", (cursor.lastrowid,)).fetchone()

    @staticmethod
    def _rejected(
        connection, user_id, execution_mode, symbol, instrument_key, side, quantity,
        source, strategy_name, signal_id, reason
    ):
        cursor = connection.execute(
            """INSERT INTO orders
               (user_id, execution_mode, symbol, instrument_key, side, quantity, source, strategy_name,
                signal_id, status, rejection_reason)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'REJECTED', ?)""",
            (user_id, execution_mode, symbol, instrument_key, side.value, quantity, source.value,
             strategy_name, signal_id, reason),
        )
        return connection.execute("SELECT * FROM orders WHERE id = ?", (cursor.lastrowid,)).fetchone()

    @staticmethod
    def _apply_fill(
        connection, user_id, execution_mode, symbol, instrument_key,
        side, quantity, price, position=None
    ):
        if position is None:
            position = connection.execute(
                """SELECT * FROM positions
                   WHERE user_id = ? AND execution_mode = ? AND symbol = ?""",
                (user_id, execution_mode, symbol),
            ).fetchone()
        signed_fill = quantity if side == Side.BUY else -quantity
        old_quantity = int(position["quantity"]) if position else 0
        old_average = float(position["average_price"]) if position else 0.0
        realized = float(position["realized_pnl"]) if position else 0.0
        new_quantity = old_quantity + signed_fill

        if old_quantity == 0 or (old_quantity > 0) == (signed_fill > 0):
            new_average = (
                (abs(old_quantity) * old_average + abs(signed_fill) * price) / abs(new_quantity)
                if new_quantity else 0.0
            )
        else:
            closing_quantity = min(abs(old_quantity), abs(signed_fill))
            realized += (price - old_average) * closing_quantity * (1 if old_quantity > 0 else -1)
            if new_quantity == 0:
                new_average = 0.0
            elif (new_quantity > 0) == (old_quantity > 0):
                new_average = old_average
            else:
                new_average = price

        connection.execute(
            """INSERT INTO positions
               (user_id, execution_mode, symbol, instrument_key, quantity, average_price, realized_pnl)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(user_id, execution_mode, symbol) DO UPDATE SET
                 instrument_key = COALESCE(excluded.instrument_key, positions.instrument_key),
                 quantity = excluded.quantity,
                 average_price = excluded.average_price,
                 realized_pnl = excluded.realized_pnl,
                 updated_at = CURRENT_TIMESTAMP""",
            (user_id, execution_mode, symbol, instrument_key, new_quantity, new_average, realized),
        )
