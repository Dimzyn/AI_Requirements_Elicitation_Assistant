"""Promote a user to requirements_engineer role.

Usage (inside backend container):
    python -m scripts.promote_user <email>

Example:
    python -m scripts.promote_user sre@example.com
"""
import asyncio
import sys

from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URI = "mongodb://mongo:27017"
DB_NAME = "probing"


async def main():
    if len(sys.argv) < 2:
        print("Usage: python -m scripts.promote_user <email>")
        sys.exit(1)
    email = sys.argv[1]
    client = AsyncIOMotorClient(MONGO_URI)
    db = client[DB_NAME]
    result = await db.users.update_one(
        {"email": email},
        {"$set": {"role": "requirements_engineer"}},
    )
    if result.matched_count == 0:
        print(f"No user found with email: {email}")
        sys.exit(1)
    print(f"Promoted {email} to requirements_engineer")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
