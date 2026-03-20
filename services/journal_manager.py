from models.database import get_connection


def record_action(signal_id: int, action: str, notes: str = ""):
    """Record an ACTED or SKIPPED decision for a signal."""
    conn = get_connection()
    # Upsert: delete existing then insert
    conn.execute("DELETE FROM journal WHERE signal_id = ?", (signal_id,))
    conn.execute(
        "INSERT INTO journal (signal_id, action, notes) VALUES (?, ?, ?)",
        (signal_id, action, notes)
    )
    conn.commit()
    conn.close()


def update_outcome(signal_id: int, outcome_pct: float):
    """Update the outcome percentage for a journal entry."""
    conn = get_connection()
    conn.execute(
        "UPDATE journal SET outcome_pct = ? WHERE signal_id = ?",
        (outcome_pct, signal_id)
    )
    conn.commit()
    conn.close()


def get_journal_entries(limit: int = 100) -> list[dict]:
    conn = get_connection()
    rows = conn.execute("""
        SELECT j.*, s.ticker, s.signal_type, s.price, s.date as signal_date,
               st.name as strategy_name
        FROM journal j
        JOIN signals s ON j.signal_id = s.id
        LEFT JOIN strategies st ON s.strategy_id = st.id
        ORDER BY j.recorded_at DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_unreviewed_signals() -> list[dict]:
    """Get signals that haven't been acted on or skipped yet."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT s.id, s.ticker, s.signal_type, s.price, s.date,
               st.name as strategy_name
        FROM signals s
        LEFT JOIN strategies st ON s.strategy_id = st.id
        LEFT JOIN journal j ON j.signal_id = s.id
        WHERE j.id IS NULL
        ORDER BY s.date DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]
