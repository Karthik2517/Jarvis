import logging

from ..brokers import BrokerFactory
from ..database import db
from ..schemas import Side
from .execution import ExecutionEngine

logger = logging.getLogger(__name__)

ACTIVE_STATUSES = ("SUBMITTED", "OPEN", "PARTIAL")


def reconcile_orders(user_id: int) -> None:
    """Synchronize active broker orders and apply only newly confirmed fills."""
    with db.connect() as connection:
        broker_row = connection.execute(
            "SELECT broker FROM broker_connections WHERE user_id = ?", (user_id,)
        ).fetchone()
        if not broker_row or broker_row["broker"] == "PAPER":
            return
        orders = connection.execute(
            """SELECT * FROM orders WHERE user_id = ? AND execution_mode = ?
               AND status IN (?, ?, ?)
               AND broker_order_id IS NOT NULL ORDER BY id""",
            (user_id, broker_row["broker"], *ACTIVE_STATUSES),
        ).fetchall()

    broker = BrokerFactory.create(broker_row["broker"])
    for pending_order in orders:
        try:
            broker_status = broker.get_order_status(pending_order["broker_order_id"])
        except RuntimeError as exc:
            logger.warning("Could not reconcile order %s: %s", pending_order["id"], exc)
            continue

        with db.transaction() as connection:
            order = connection.execute(
                "SELECT * FROM orders WHERE id = ? AND user_id = ?",
                (pending_order["id"], user_id),
            ).fetchone()
            if not order:
                continue
            previous_filled = int(order["filled_quantity"] or 0)
            new_filled = max(previous_filled, broker_status.filled_quantity)
            fill_delta = new_filled - previous_filled
            if fill_delta > 0 and broker_status.average_price is not None:
                previous_average = float(order["average_price"] or 0)
                incremental_price = (
                    broker_status.average_price * new_filled - previous_average * previous_filled
                ) / fill_delta
                ExecutionEngine._apply_fill(
                    connection,
                    user_id,
                    order["execution_mode"],
                    order["symbol"],
                    order["instrument_key"],
                    Side(order["side"]),
                    fill_delta,
                    incremental_price,
                )
            connection.execute(
                """UPDATE orders SET status = ?, filled_quantity = ?, average_price = ?,
                   rejection_reason = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?""",
                (
                    broker_status.status,
                    new_filled,
                    broker_status.average_price if broker_status.average_price is not None else order["average_price"],
                    broker_status.rejection_reason,
                    order["id"],
                ),
            )
