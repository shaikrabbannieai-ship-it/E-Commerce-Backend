import sqlite3
from database import SessionLocal, User, init_db
from datetime import datetime

def migrate_users():
    """Migrate users from SQLite to PostgreSQL"""
    
    # First, initialize PostgreSQL tables (this will drop and recreate)
    print("🔄 Initializing PostgreSQL database...")
    init_db()
    
    # Connect to SQLite
    print("📂 Reading data from SQLite...")
    sqlite_conn = sqlite3.connect("ecommerce.db")
    sqlite_cursor = sqlite_conn.cursor()
    
    # Check if users table exists in SQLite
    sqlite_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
    if not sqlite_cursor.fetchone():
        print("❌ No users table found in SQLite database!")
        sqlite_conn.close()
        return
    
    # Get all users from SQLite
    sqlite_cursor.execute("SELECT id, full_name, email, password_hash, password_salt, created_at, last_login, is_active, failed_attempts, locked_until FROM users")
    users = sqlite_cursor.fetchall()
    
    if not users:
        print("⚠️ No users found in SQLite database!")
        sqlite_conn.close()
        return
    
    print(f"📊 Found {len(users)} users in SQLite")
    
    # Create PostgreSQL session
    db = SessionLocal()
    
    try:
        for user in users:
            # Convert SQLite data to PostgreSQL format
            new_user = User(
                id=user[0],
                full_name=user[1],
                email=user[2],
                password_hash=user[3],
                password_salt=user[4],
                created_at=datetime.fromisoformat(user[5]) if user[5] else datetime.utcnow(),
                last_login=datetime.fromisoformat(user[6]) if user[6] else None,
                is_active=bool(user[7]) if user[7] is not None else True,
                failed_attempts=user[8] if user[8] is not None else 0,
                locked_until=datetime.fromisoformat(user[9]) if user[9] else None
            )
            db.add(new_user)
            print(f"   ✓ Added user: {user[1]} ({user[2]})")
        
        db.commit()
        print(f"\n✅ Successfully migrated {len(users)} users to PostgreSQL!")
        
        # Verify migration
        count = db.query(User).count()
        print(f"📊 Verification: {count} users now in PostgreSQL database")
        
    except Exception as e:
        print(f"❌ Error during migration: {e}")
        db.rollback()
    finally:
        db.close()
        sqlite_conn.close()

def show_users():
    """Show all users in PostgreSQL"""
    db = SessionLocal()
    try:
        users = db.query(User).all()
        print("\n📋 Users in PostgreSQL:")
        print("-" * 80)
        for user in users:
            print(f"ID: {user.id} | Name: {user.full_name} | Email: {user.email} | Created: {user.created_at}")
        print("-" * 80)
    finally:
        db.close()

if __name__ == "__main__":
    migrate_users()
    show_users()