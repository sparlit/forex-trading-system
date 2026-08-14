#!/usr/bin/env python3
"""
Database initialization script.
Run this after starting TimescaleDB to create the schema.
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.data.storage.timescale import TimescaleDB
from src.infra.config.settings import settings


async def init_database():
    """Initialize database schema."""
    print("Connecting to TimescaleDB...")
    db = TimescaleDB(settings.timescale_dsn)
    
    try:
        await db.connect()
        print("Connected successfully!")
        
        # Read and execute SQL script
        sql_path = Path(__file__).parent / "init-timescaledb.sql"
        if sql_path.exists():
            print(f"Executing {sql_path}...")
            with open(sql_path, 'r') as f:
                sql = f.read()
            
            # Split by semicolon and execute each statement
            statements = [s.strip() for s in sql.split(';') if s.strip()]
            
            for i, stmt in enumerate(statements):
                try:
                    await db._pool.execute(stmt)
                    print(f"  Statement {i+1}/{len(statements)} executed")
                except Exception as e:
                    # Some statements might fail if already exist (like extensions)
                    if "already exists" not in str(e).lower():
                        print(f"  Warning: Statement {i+1} failed: {e}")
                    else:
                        print(f"  Statement {i+1} skipped (already exists)")
            
            print("Database initialization complete!")
        else:
            print(f"SQL file not found: {sql_path}")
            
    except Exception as e:
        print(f"Error: {e}")
        raise
    finally:
        await db.disconnect()


if __name__ == "__main__":
    asyncio.run(init_database())