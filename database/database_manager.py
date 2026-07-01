
import sqlite3
import pandas as pd
from datetime import datetime

DATABASE_FILE = "fall_events.db"


def create_connection():
    """Create a database connection to the SQLite database."""
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        return conn
    except sqlite3.Error as e:
        print(f"[DB] Error connecting to database: {e}")
        return None


def create_table():
    """Create the fall_events table."""
    conn = create_connection()
    if conn:
        sql_create_table = """
        CREATE TABLE IF NOT EXISTS fall_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            device_id TEXT,
            fall_detected INTEGER,
            latitude REAL,
            longitude REAL,
            has_gps_fix INTEGER,
            status TEXT NOT NULL
        );
        """
        try:
            conn.execute(sql_create_table)
            conn.commit()
            print("[DB] Database and table created successfully.")
        except sqlite3.Error as e:
            print(f"[DB] Error creating table: {e}")
        finally:
            conn.close()


def insert_fall_event(json_data):
    """Insert a new fall event from a JSON object using pandas."""
    conn = create_connection()
    if conn:
        try:
            df = pd.DataFrame([{
                "timestamp": datetime.fromtimestamp(json_data.get("timestamp", 0)).isoformat(),
                "device_id": json_data.get("device_id"),
                "fall_detected": int(json_data.get("fall_detected", False)),
                "latitude": json_data.get("latitude"),
                "longitude": json_data.get("longitude"),
                "has_gps_fix": int(json_data.get("has_gps_fix", False)),
                "status": "pending"
            }])
            df.to_sql("fall_events", conn, if_exists="append", index=False)
            # Get last inserted row id
            last_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            print(f"[DB] Fall event recorded with ID: {last_id}")
            return last_id
        except Exception as e:
            print(f"[DB] Error inserting data: {e}")
            return None
        finally:
            conn.close()


def update_alert_status(event_id, new_status):
    """Update the status of a fall alert by its ID."""
    conn = create_connection()
    if conn:
        try:
            conn.execute(
                "UPDATE fall_events SET status = ? WHERE id = ?;",
                (new_status, event_id)
            )
            conn.commit()
            print(f"[DB] Alert ID {event_id} status updated to '{new_status}'.")
        except sqlite3.Error as e:
            print(f"[DB] Error updating status: {e}")
        finally:
            conn.close()


def get_all_alerts():
    """Retrieve all fall alerts as a pandas DataFrame."""
    conn = create_connection()
    if conn:
        try:
            df = pd.read_sql(
                "SELECT id, timestamp, device_id, fall_detected, latitude, longitude, has_gps_fix, status "
                "FROM fall_events ORDER BY timestamp DESC;",
                conn
            )
            return df
        except Exception as e:
            print(f"[DB] Error retrieving alerts: {e}")
            return pd.DataFrame()
        finally:
            conn.close()
    return pd.DataFrame()
