from tutor_db import get_db

# Example data from example_states.py
topics = [
    (1, "Computational thinking"),
    (2, "Data"),
    (3, "Computers"),
    (4, "Networks"),
    (5, "Issues and impact"),
    (6, "Problem-solving with programming")
]

flashcards = [
    (1, 2, "What do you know about: Binary representation?", 
     "Key points for full marks:\n1. Definition: Binary is a base-2 number system using only 0s and 1s\n2. Structure: Each position represents a power of 2 (e.g., 2^0, 2^1, 2^2)\n3. Conversion: Explain decimal to binary conversion using powers of 2\n4. Computing relevance: Fundamental to digital data storage and processing\n5. Examples: Show binary representation of simple numbers (e.g., 8 = 1000)"),
    (2, 2, "What do you know about: Data storage and compression?",
     "Key points for full marks:\n1. Storage types: Primary (RAM) vs Secondary (HDD, SSD)\n2. Storage units: Bits, bytes, KB, MB, GB, TB\n3. Compression types: Lossy vs Lossless with examples\n4. Compression benefits: Reduced file size, faster transmission\n5. Common formats: ZIP for lossless, JPEG/MP3 for lossy"),
    (3, 2, "What do you know about: Encryption?",
     "Key points for full marks:\n1. Definition: Process of converting data into a secure format\n2. Types: Symmetric vs Asymmetric encryption\n3. Key concepts: Public/private keys, ciphers\n4. Real-world uses: HTTPS, secure messaging, banking\n5. Importance: Data security, privacy, confidentiality"),
    (4, 1, "What is decomposition in computational thinking?",
     "Key points for full marks:\n1. Definition: Breaking complex problems into smaller parts\n2. Benefits: Makes problems more manageable and solvable\n3. Process: Identify components and their relationships\n4. Example: Breaking down a game into graphics, input, scoring\n5. Application: Show how it helps in systematic problem-solving"),
    (5, 1, "Explain pattern recognition and why it's important in problem-solving.",
     "Key points for full marks:\n1. Definition: Identifying similarities and patterns in problems\n2. Purpose: Finding common solutions to similar problems\n3. Benefits: Efficiency in problem-solving, reusable solutions\n4. Examples: Sorting algorithms, data structures patterns\n5. Application: How patterns help in predicting and solving new problems"),
    (6, 1, "What is abstraction and how is it used in computational thinking?",
     "Key points for full marks:\n1. Definition: Focusing on essential details while hiding complexity\n2. Levels: Different layers of abstraction in computing\n3. Benefits: Simplifies problem-solving and system design\n4. Examples: Functions, classes, APIs as abstractions\n5. Application: How abstraction improves code reusability and maintenance")
]

def seed_db():
    """Seed the database with example data."""
    with get_db() as db:
        db.executemany("INSERT OR REPLACE INTO topics (id, name) VALUES (?, ?)", topics)
        db.executemany(
            "INSERT OR REPLACE INTO flashcards (id, topic_id, question, marking_criteria) VALUES (?, ?, ?, ?)", 
            flashcards
        )
        db.commit()

def delete_all_tables():
    """Delete all tables (topics, flashcards) from the database."""
    with get_db() as db:
        # Drop tables in correct order due to foreign key constraints
        db.execute("DROP TABLE IF EXISTS flashcards")
        db.execute("DROP TABLE IF EXISTS topics")
        db.execute("DROP TABLE IF EXISTS flashcards_new")
        db.commit()

if __name__ == "__main__":
    seed_db()
