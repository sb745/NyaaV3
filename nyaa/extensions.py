import os.path
from typing import Any, Optional, Sequence, TypeVar, Union

from flask import abort
from flask.config import Config
from flask_assets import Environment
from flask_caching import Cache
from flask_debugtoolbar import DebugToolbarExtension
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_sqlalchemy import SQLAlchemy
from flask_sqlalchemy.pagination import Pagination
from sqlalchemy.orm import Query

assets = Environment()
db = SQLAlchemy()
toolbar = DebugToolbarExtension()
cache = Cache()
limiter = Limiter(key_func=get_remote_address)

# Type variable for query results
T = TypeVar('T')


class LimitedPagination(Pagination):
    def __init__(self, actual_count: int, *args: Any, **kwargs: Any) -> None:
        self.actual_count = actual_count
        super().__init__(*args, **kwargs)


def fix_paginate() -> None:
    """Add custom pagination method to SQLAlchemy Query."""
    
    def paginate_faste(
        self: Query[T], 
        page: int = 1, 
        per_page: int = 50, 
        max_page: Optional[int] = None, 
        step: int = 5, 
        count_query: Optional[Query[int]] = None
    ) -> LimitedPagination:
        """Custom pagination that supports max_page and count_query."""
        if page < 1:
            abort(404)

        if max_page and page > max_page:
            abort(404)

        # Count all items
        if count_query is not None:
            total_query_count = count_query.scalar()
        else:
            total_query_count = self.count()
            
        if total_query_count is None:
            total_query_count = 0
            
        actual_query_count = total_query_count
        if max_page:
            total_query_count = min(total_query_count, max_page * per_page)

        # Grab items on current page
        items = self.limit(per_page).offset((page - 1) * per_page).all()

        if not items and page != 1:
            abort(404)

        return LimitedPagination(actual_query_count, self, page, per_page, total_query_count,
                                 items)

    # Monkey patch the Query class
    setattr(Query, 'paginate_faste', paginate_faste)


def _get_config() -> Config:
    """
    Workaround to get an available config object before the app is initialized.
    Only needed/used in top-level and class statements.
    https://stackoverflow.com/a/18138250/7597273
    """
    root_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    config_obj = Config(root_path)
    config_obj.from_object('config')
    return config_obj


config = _get_config()
