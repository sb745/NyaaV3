from typing import Any, List, Optional, Sequence, TypeVar, Union

T = TypeVar('T')

class CustomPagination:
    """
    A custom pagination class that mimics the interface of Flask-SQLAlchemy's Pagination
    but doesn't rely on the _query_items method.
    """
    
    def __init__(self, query: Any, page: int, per_page: int, total: int, items: List[T]):
        """
        Initialize a new CustomPagination object.
        
        Args:
            query: The query object (not used, but kept for compatibility)
            page: The current page number (1-indexed)
            per_page: The number of items per page
            total: The total number of items
            items: The items on the current page
        """
        self.query = query
        self.page = page
        self.per_page = per_page
        self.total = total
        self.items = items
        
        # For compatibility with LimitedPagination
        self.actual_count = total
    
    @property
    def has_prev(self) -> bool:
        """Return True if there is a previous page."""
        return self.page > 1
    
    @property
    def has_next(self) -> bool:
        """Return True if there is a next page."""
        return self.page < self.pages
    
    @property
    def pages(self) -> int:
        """The total number of pages."""
        if self.per_page == 0 or self.total == 0:
            return 0
        return max(1, (self.total + self.per_page - 1) // self.per_page)
    
    @property
    def prev_num(self) -> Optional[int]:
        """The previous page number, or None if this is the first page."""
        if self.has_prev:
            return self.page - 1
        return None
    
    @property
    def next_num(self) -> Optional[int]:
        """The next page number, or None if this is the last page."""
        if self.has_next:
            return self.page + 1
        return None
    
    @property
    def first(self) -> int:
        """The number of the first item on the page, starting from 1, or 0 if there are no items."""
        if not self.items:
            return 0
        return (self.page - 1) * self.per_page + 1
    
    @property
    def last(self) -> int:
        """The number of the last item on the page, starting from 1, inclusive, or 0 if there are no items."""
        if not self.items:
            return 0
        return min(self.total, self.page * self.per_page)
    
    def iter_pages(self, left_edge: int = 2, left_current: int = 2,
                  right_current: int = 5, right_edge: int = 2) -> Sequence[Optional[int]]:
        """
        Yield page numbers for a pagination widget.
        
        Skipped pages between the edges and middle are represented by a None.
        """
        last = 0
        for num in range(1, self.pages + 1):
            if (num <= left_edge or
                (num > self.page - left_current - 1 and num < self.page + right_current) or
                num > self.pages - right_edge):
                if last + 1 != num:
                    yield None
                yield num
                last = num
    
    def __iter__(self):
        """Iterate over the items on the current page."""
        return iter(self.items)
    
    def __len__(self):
        """Return the number of items on the current page."""
        return len(self.items)
