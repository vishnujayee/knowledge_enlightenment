# fix_database.py - Run this once to fix your database

import sqlite3
import os

def fix_database():
    db_path = 'knowledge.db'
    
    # Also check in backend folder
    if not os.path.exists(db_path):
        alt_path = 'backend/knowledge.db'
        if os.path.exists(alt_path):
            db_path = alt_path
    
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        print("Creating new database...")
        # Database will be created when you run the app
        return
    
    print(f"Fixing database: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check existing columns
    cursor.execute("PRAGMA table_info(knowledge_items)")
    columns = [col[1] for col in cursor.fetchall()]
    
    print(f"Existing columns: {columns}")
    
    # Add missing columns
    if 'content_type' not in columns:
        print("Adding content_type column...")
        cursor.execute("ALTER TABLE knowledge_items ADD COLUMN content_type TEXT DEFAULT 'academic'")
    
    if 'archival_era' not in columns:
        print("Adding archival_era column...")
        cursor.execute("ALTER TABLE knowledge_items ADD COLUMN archival_era TEXT")
    
    if 'reading_time_minutes' not in columns:
        print("Adding reading_time_minutes column...")
        cursor.execute("ALTER TABLE knowledge_items ADD COLUMN reading_time_minutes INTEGER DEFAULT 5")
    
    # Update existing rows - set content_type based on source_type
    print("Updating existing rows...")
    cursor.execute("""
        UPDATE knowledge_items 
        SET content_type = CASE 
            WHEN source_type IN ('research_paper', 'news', 'wikipedia', 'book', 'patent', 'academic', 'rss') THEN 'academic'
            WHEN source_type IN ('blog', 'writing', 'blog_archive', 'personal', 'crawled') THEN 'writing'
            ELSE 'academic'
        END
        WHERE content_type IS NULL OR content_type = ''
    """)
    
    conn.commit()
    
    # Verify
    cursor.execute("PRAGMA table_info(knowledge_items)")
    updated_columns = [col[1] for col in cursor.fetchall()]
    print(f"\nUpdated columns: {updated_columns}")
    
    cursor.execute("SELECT COUNT(*) FROM knowledge_items")
    count = cursor.fetchone()[0]
    print(f"Total rows: {count}")
    
    cursor.execute("SELECT content_type, COUNT(*) FROM knowledge_items GROUP BY content_type")
    types = cursor.fetchall()
    print(f"Content type distribution: {types}")
    
    conn.close()
    print("\n✅ Database fixed successfully!")
    print("Restart your application now.")

if __name__ == "__main__":
    fix_database()