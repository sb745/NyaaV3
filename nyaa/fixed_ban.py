from typing import Optional, Union
from sqlalchemy import or_, select
from nyaa.extensions import db
from nyaa.models import Ban

# Fix the banned method to return a query object instead of a list
@classmethod
def fixed_banned(cls, user_id: Optional[int], user_ip: Optional[bytes]):
    """Check if a user or IP is banned.
    
    Returns a query object that can be further filtered or used with .first(), .all(), etc.
    """
    if not user_id and not user_ip:
        # Return an empty query that will return no results
        return db.session.query(cls).filter(cls.id < 0)
    
    clauses = []
    if user_id:
        clauses.append(cls.user_id == user_id)
    if user_ip:
        clauses.append(cls.user_ip == user_ip)
    
    return db.session.query(cls).filter(or_(*clauses))

# Replace the original method with our fixed version
Ban.banned = fixed_banned
