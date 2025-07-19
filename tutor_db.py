import sqlite3
from typing import List, Dict, Any
from contextlib import contextmanager
import os

DB_PATH = "tutor.db"

def init_db():
    """Initialize the database with topics and flashcards tables."""
    # Check if tables already exist
    with get_db() as db:
        cursor = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND (name='topics' OR name='flashcards')"
        )
        existing_tables = {row['name'] for row in cursor.fetchall()}
        
        if 'topics' not in existing_tables or 'flashcards' not in existing_tables:
            # Read and execute schema file
            with open('quiz_schema.sql', 'r') as f:
                db.executescript(f.read())
            db.commit()

@contextmanager
def get_db():
    """Context manager for database connections."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def get_flashcards_by_topic_id(topic_id: int):
    """Retrieve all flashcards for a given topic.
    
    Args:
        topic_id: ID of the topic to get flashcards for
        
    Returns:
        List of flashcard dictionaries with id, topic_id, question and answer
    """
    with get_db() as db:
        cursor = db.execute(
            "SELECT id, topic_id, question, marking_criteria FROM flashcards WHERE topic_id = ?", 
            (topic_id,)
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

if __name__ == "__main__":
    print(get_flashcards_by_topic_id(1)[1]['question'])
