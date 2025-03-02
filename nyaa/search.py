import math
import re
import shlex
import threading
import time
from typing import Any, Dict, List, Optional, Tuple, Union

import flask
from nyaa.custom_pagination import CustomPagination

import sqlalchemy
from sqlalchemy import select, func, bindparam
import sqlalchemy_fulltext.modes as FullTextMode
from elasticsearch import Elasticsearch
from elasticsearch_dsl import Q, Search
from sqlalchemy_fulltext import FullTextSearch

from nyaa import models
from nyaa.extensions import db

app = flask.current_app

DEFAULT_MAX_SEARCH_RESULT = 1000
DEFAULT_PER_PAGE = 75
SERACH_PAGINATE_DISPLAY_MSG = ('Displaying results {start}-{end} out of {total} results.<br>\n'
                               'Please refine your search results if you can\'t find '
                               'what you were looking for.')

# Table-column index name cache for _get_index_name
# In format of {'table' : {'column_a':'ix_table_column_a'}}
_index_name_cache = {}


def _get_index_name(column) -> Optional[str]:
    ''' Returns an index name for a given column, or None.
        Only considers single-column indexes.
        Results are cached in memory (until app restart). '''
    column_table_name = column.class_.__table__.name
    table_indexes = _index_name_cache.get(column_table_name)
    if table_indexes is None:
        # Load the real table schema from the database
        # Fresh MetaData used to skip SQA's cache and get the real indexes on the database
        table_indexes = {}
        try:
            column_table = sqlalchemy.Table(column_table_name,
                                            sqlalchemy.MetaData(),
                                            autoload_with=db.engine)
        except sqlalchemy.exc.NoSuchTableError:
            # Trust the developer to notice this?
            pass
        else:
            for index in column_table.indexes:
                # Only consider indexes with one column
                if len(index.expressions) > 1:
                    continue

                index_column = index.expressions[0]
                table_indexes[index_column.name] = index.name
        _index_name_cache[column_table_name] = table_indexes

    return table_indexes.get(column.name)


def _generate_query_string(term: Optional[str], category: Optional[str], 
                          filter: Optional[str], user: Optional[int]) -> Dict[str, str]:
    params = {}
    if term:
        params['q'] = str(term)
    if category:
        params['c'] = str(category)
    if filter:
        params['f'] = str(filter)
    if user:
        params['u'] = str(user)
    return params


# For preprocessing ES search terms in _parse_es_search_terms
QUOTED_LITERAL_REGEX = re.compile(r'(?i)(-)?"(.+?)"')
QUOTED_LITERAL_GROUP_REGEX = re.compile(r'''
    (?i)
    (-)? # Negate entire group at once
    (
        ".+?" # First literal
        (?:
            \|    # OR
            ".+?" # Second literal
        )+        # repeating
    )
    ''', re.X)


def _es_name_exact_phrase(literal):
    ''' Returns a Query for a phrase match on the display_name for a given literal '''
    return Q({
        'match_phrase': {
            'display_name.exact': {
                'query': literal,
                'analyzer': 'exact_analyzer'
            }
        }
    })


def _parse_es_search_terms(search, search_terms):
    ''' Parse search terms into a query with properly handled literal phrases
        (the simple_query_string is not so great with exact results).
        For example:
            foo bar "hello world" -"exclude this"
        will become a must simple_query_string for "foo bar", a must phrase_match for
        "hello world" and a must_not for "exclude this".
        Returns the search with the generated bool-query added to it. '''

    # Literal must and must-not sets
    must_set = set()
    must_not_set = set()

    must_or_groups = []
    must_not_or_groups = []

    def must_group_matcher(match):
        ''' Grabs [-]"foo"|"bar"[|"baz"...] groups from the search terms '''
        negated = bool(match.group(1))
        literal_group = match.group(2)

        literals = QUOTED_LITERAL_REGEX.findall(literal_group)
        group_query = Q(
            'bool',
            should=[_es_name_exact_phrase(lit_m[1]) for lit_m in literals]
        )

        if negated:
            must_not_or_groups.append(group_query)
        else:
            must_or_groups.append(group_query)

        # Remove the parsed group from search terms
        return ''

    def must_matcher(match):
        ''' Grabs [-]"foo" literals from the search terms '''
        negated = bool(match.group(1))
        literal = match.group(2)

        if negated:
            must_not_set.add(literal)
        else:
            must_set.add(literal)

        # Remove the parsed literal from search terms
        return ''

    # Remove quoted parts (optionally prepended with -) and store them in the sets
    parsed_search_terms = QUOTED_LITERAL_GROUP_REGEX.sub(must_group_matcher, search_terms).strip()
    parsed_search_terms = QUOTED_LITERAL_REGEX.sub(must_matcher, parsed_search_terms).strip()

    # Create phrase matches (if any)
    must_queries = [_es_name_exact_phrase(lit) for lit in must_set] + must_or_groups
    must_not_queries = [_es_name_exact_phrase(lit) for lit in must_not_set] + must_not_or_groups

    if parsed_search_terms:
        # Normal text search without the quoted parts
        must_queries.append(
            Q(
                'simple_query_string',
                # Query both fields, latter for words with >15 chars
                fields=['display_name', 'display_name.fullword'],
                analyzer='my_search_analyzer',
                default_operator="AND",
                query=parsed_search_terms
            )
        )

    if must_queries or must_not_queries:
        # Create a combined Query with the positive and negative matches
        combined_search_query = Q(
            'bool',
            must=must_queries,
            must_not=must_not_queries
        )
        search = search.query(combined_search_query)

    return search


def search_elastic(term='', user=None, sort='id', order='desc',
                   category='0_0', quality_filter='0', page=1,
                   rss=False, admin=False, logged_in_user=None,
                   per_page=75, max_search_results=1000):
    # This function can easily be memcached now
    if page > 4294967295:
        flask.abort(404)

    es_client = Elasticsearch(hosts=app.config['ES_HOSTS'])

    es_sort_keys = {
        'id': 'id',
        'size': 'filesize',
        # 'name': 'display_name',  # This is slow and buggy
        'comments': 'comment_count',
        'seeders': 'seed_count',
        'leechers': 'leech_count',
        'downloads': 'download_count'
    }

    sort_ = sort.lower()
    if sort_ not in es_sort_keys:
        flask.abort(400)

    es_sort = es_sort_keys[sort]

    order_keys = {
        'desc': 'desc',
        'asc': 'asc'
    }

    order_ = order.lower()
    if order_ not in order_keys:
        flask.abort(400)

    # Only allow ID, desc if RSS
    if rss:
        sort = es_sort_keys['id']
        order = 'desc'

    # funky, es sort is default asc, prefixed by '-' if desc
    if 'desc' == order:
        es_sort = '-' + es_sort

    # Quality filter
    quality_keys = [
        '0',  # Show all
        '1',  # No remakes
        '2',  # Only trusted
        '3'   # Only completed
    ]

    if quality_filter.lower() not in quality_keys:
        flask.abort(400)

    quality_filter = int(quality_filter)

    # Category filter
    main_category = None
    sub_category = None
    main_cat_id = 0
    sub_cat_id = 0
    if category:
        cat_match = re.match(r'^(\d+)_(\d+)$', category)
        if not cat_match:
            flask.abort(400)

        main_cat_id = int(cat_match.group(1))
        sub_cat_id = int(cat_match.group(2))

        if main_cat_id > 0:
            if sub_cat_id > 0:
                sub_category = models.SubCategory.by_category_ids(main_cat_id, sub_cat_id)
                if not sub_category:
                    flask.abort(400)
            else:
                main_category = models.MainCategory.by_id(main_cat_id)
                if not main_category:
                    flask.abort(400)

    # This might be useless since we validate users
    # before coming into this method, but just to be safe...
    if user:
        user = models.User.by_id(user)
        if not user:
            flask.abort(404)
        user = user.id

    same_user = False
    if logged_in_user:
        same_user = user == logged_in_user.id

    s = Search(using=es_client, index=app.config.get('ES_INDEX_NAME'))  # todo, sukebei prefix

    # Apply search term
    if term:
        # Do some preprocessing on the search terms for literal "" matching
        s = _parse_es_search_terms(s, term)

    # User view (/user/username)
    if user:
        s = s.filter('term', uploader_id=user)

        if not admin:
            # Hide all DELETED torrents if regular user
            s = s.filter('term', deleted=False)
            # If logged in user is not the same as the user being viewed,
            # show only torrents that aren't hidden or anonymous.
            #
            # If logged in user is the same as the user being viewed,
            # show all torrents including hidden and anonymous ones.
            #
            # On RSS pages in user view, show only torrents that
            # aren't hidden or anonymous no matter what
            if not same_user or rss:
                s = s.filter('term', hidden=False)
                s = s.filter('term', anonymous=False)
    # General view (homepage, general search view)
    else:
        if not admin:
            # Hide all DELETED torrents if regular user
            s = s.filter('term', deleted=False)
            # If logged in, show all torrents that aren't hidden unless they belong to you
            # On RSS pages, show all public torrents and nothing more.
            if logged_in_user and not rss:
                hiddenFilter = Q('term', hidden=False)
                userFilter = Q('term', uploader_id=logged_in_user.id)
                combinedFilter = hiddenFilter | userFilter
                s = s.filter('bool', filter=[combinedFilter])
            else:
                s = s.filter('term', hidden=False)

    if main_category:
        s = s.filter('term', main_category_id=main_cat_id)
    elif sub_category:
        s = s.filter('term', main_category_id=main_cat_id)
        s = s.filter('term', sub_category_id=sub_cat_id)

    if quality_filter == 0:
        pass
    elif quality_filter == 1:
        s = s.filter('term', remake=False)
    elif quality_filter == 2:
        s = s.filter('term', trusted=True)
    elif quality_filter == 3:
        s = s.filter('term', complete=True)

    # Apply sort
    s = s.sort(es_sort)

    # Only show first RESULTS_PER_PAGE items for RSS
    if rss:
        s = s[0:per_page]
    else:
        max_page = min(page, int(math.ceil(max_search_results / float(per_page))))
        from_idx = (max_page - 1) * per_page
        to_idx = min(max_search_results, max_page * per_page)
        s = s[from_idx:to_idx]

    highlight = app.config.get('ENABLE_ELASTIC_SEARCH_HIGHLIGHT')
    if highlight:
        s = s.highlight_options(tags_schema='styled')
        s = s.highlight("display_name")

    # Return query, uncomment print line to debug query
    # from pprint import pprint
    # print(json.dumps(s.to_dict()))
    return s.execute()


class QueryPairCaller(object):
    ''' Simple stupid class to filter one or more queries with the same args '''

    def __init__(self, *items):
        self.items = list(items)

    def __getattr__(self, name):
        # Create and return a wrapper that will call item.foobar(*args, **kwargs) for all items
        def wrapper(*args, **kwargs):
            for i in range(len(self.items)):
                method = getattr(self.items[i], name)
                if not callable(method):
                    raise Exception('Attribute %r is not callable' % method)
                self.items[i] = method(*args, **kwargs)
            return self

        return wrapper


def search_db(term: str = '', user: Optional[int] = None, sort: str = 'id', 
              order: str = 'desc', category: str = '0_0',
              quality_filter: str = '0', page: int = 1, rss: bool = False, 
              admin: bool = False, logged_in_user: Optional[models.User] = None, 
              per_page: int = 75) -> Union[CustomPagination, List[models.Torrent]]:
    """
    Search the database for torrents matching the given criteria.
    
    This is the SQLAlchemy 2.0 compatible version of the search function.
    """
    if page > 4294967295:
        flask.abort(404)

    MAX_PAGES = app.config.get("MAX_PAGES", 0)

    same_user = False
    if logged_in_user and user:
        same_user = logged_in_user.id == user

    # Logged in users should always be able to view their full listing.
    if same_user or admin:
        MAX_PAGES = 0

    if MAX_PAGES and page > MAX_PAGES:
        flask.abort(flask.Response("You've exceeded the maximum number of pages. Please "
                                   "make your search query less broad.", 403))

    sort_keys = {
        'id': models.Torrent.id,
        'size': models.Torrent.filesize,
        # Disable this because we disabled this in search_elastic, for the sake of consistency:
        # 'name': models.Torrent.display_name,
        'comments': models.Torrent.comment_count,
        'seeders': models.Statistic.seed_count,
        'leechers': models.Statistic.leech_count,
        'downloads': models.Statistic.download_count
    }

    sort_column = sort_keys.get(sort.lower())
    if sort_column is None:
        flask.abort(400)

    order_keys = {
        'desc': 'desc',
        'asc': 'asc'
    }

    order_ = order.lower()
    if order_ not in order_keys:
        flask.abort(400)

    filter_keys = {
        '0': None,
        '1': (models.TorrentFlags.REMAKE, False),
        '2': (models.TorrentFlags.TRUSTED, True),
        '3': (models.TorrentFlags.COMPLETE, True)
    }

    sentinel = object()
    filter_tuple = filter_keys.get(quality_filter.lower(), sentinel)
    if filter_tuple is sentinel:
        flask.abort(400)

    if user:
        user_obj = models.User.by_id(user)
        if not user_obj:
            flask.abort(404)
        user = user_obj.id

    main_category = None
    sub_category = None
    main_cat_id = 0
    sub_cat_id = 0
    if category:
        cat_match = re.match(r'^(\d+)_(\d+)$', category)
        if not cat_match:
            flask.abort(400)

        main_cat_id = int(cat_match.group(1))
        sub_cat_id = int(cat_match.group(2))

        if main_cat_id > 0:
            if sub_cat_id > 0:
                sub_category = models.SubCategory.by_category_ids(main_cat_id, sub_cat_id)
            else:
                main_category = models.MainCategory.by_id(main_cat_id)

            if not category:
                flask.abort(400)

    # Force sort by id desc if rss
    if rss:
        sort_column = sort_keys['id']
        order = 'desc'

    model_class = models.TorrentNameSearch if term else models.Torrent

    # Create the base query
    query = select(model_class)
    count_query = select(func.count(model_class.id))

    # User view (/user/username)
    if user:
        query = query.where(models.Torrent.uploader_id == user)
        count_query = count_query.where(models.Torrent.uploader_id == user)

        if not admin:
            # Hide all DELETED torrents if regular user
            deleted_filter = models.Torrent.flags.op('&')(
                int(models.TorrentFlags.DELETED)).is_(False)
            query = query.where(deleted_filter)
            count_query = count_query.where(deleted_filter)
            
            # If logged in user is not the same as the user being viewed,
            # show only torrents that aren't hidden or anonymous
            #
            # If logged in user is the same as the user being viewed,
            # show all torrents including hidden and anonymous ones
            #
            # On RSS pages in user view,
            # show only torrents that aren't hidden or anonymous no matter what
            if not same_user or rss:
                hidden_anon_filter = models.Torrent.flags.op('&')(
                    int(models.TorrentFlags.HIDDEN | models.TorrentFlags.ANONYMOUS)).is_(False)
                query = query.where(hidden_anon_filter)
                count_query = count_query.where(hidden_anon_filter)
    # General view (homepage, general search view)
    else:
        if not admin:
            # Hide all DELETED torrents if regular user
            deleted_filter = models.Torrent.flags.op('&')(
                int(models.TorrentFlags.DELETED)).is_(False)
            query = query.where(deleted_filter)
            count_query = count_query.where(deleted_filter)
            
            # If logged in, show all torrents that aren't hidden unless they belong to you
            # On RSS pages, show all public torrents and nothing more.
            if logged_in_user and not rss:
                hidden_or_user_filter = (
                    (models.Torrent.flags.op('&')(int(models.TorrentFlags.HIDDEN)).is_(False)) |
                    (models.Torrent.uploader_id == logged_in_user.id)
                )
                query = query.where(hidden_or_user_filter)
                count_query = count_query.where(hidden_or_user_filter)
            # Otherwise, show all torrents that aren't hidden
            else:
                hidden_filter = models.Torrent.flags.op('&')(
                    int(models.TorrentFlags.HIDDEN)).is_(False)
                query = query.where(hidden_filter)
                count_query = count_query.where(hidden_filter)

    if main_category:
        main_cat_filter = models.Torrent.main_category_id == main_cat_id
        query = query.where(main_cat_filter)
        count_query = count_query.where(main_cat_filter)
    elif sub_category:
        sub_cat_filter = (
            (models.Torrent.main_category_id == main_cat_id) &
            (models.Torrent.sub_category_id == sub_cat_id)
        )
        query = query.where(sub_cat_filter)
        count_query = count_query.where(sub_cat_filter)

    if filter_tuple:
        filter_condition = models.Torrent.flags.op('&')(
            int(filter_tuple[0])).is_(filter_tuple[1])
        query = query.where(filter_condition)
        count_query = count_query.where(filter_condition)

    if term:
        for item in shlex.split(term, posix=False):
            if len(item) >= 2:
                fulltext_filter = FullTextSearch(
                    item, models.TorrentNameSearch, FullTextMode.NATURAL)
                query = query.where(fulltext_filter)
                count_query = count_query.where(fulltext_filter)

    # Sort and order
    if sort_column.class_ != models.Torrent:
        index_name = _get_index_name(sort_column)
        query = query.join(sort_column.class_)
        
        # Add index hint for MySQL if available
        if index_name and hasattr(db.engine.dialect, 'name') and db.engine.dialect.name == 'mysql':
            # In SQLAlchemy 2.0, we use execution_options instead of with_hint
            # This is MySQL specific - for other databases, different approaches would be needed
            query = query.execution_options(
                mysql_hint=f"USE INDEX ({index_name})"
            )
        
    if order_ == 'desc':
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())

    if rss:
        query = query.limit(per_page)
        return db.session.execute(query).scalars().all()
    else:
        # Get the total count
        total_count = db.session.execute(count_query).scalar_one()
        
        # Apply pagination
        query = query.limit(per_page).offset((page - 1) * per_page)
        items = db.session.execute(query).scalars().all()
        
        if not items and page != 1:
            flask.abort(404)
            
        # Create a pagination object
        return CustomPagination(query, page, per_page, total_count, items)


# Alias for backward compatibility
search_db_baked = search_db


class ShoddyLRU(object):
    def __init__(self, max_entries=128, expiry=60):
        self.max_entries = max_entries
        self.expiry = expiry

        # Contains [value, last_used, expires_at]
        self.entries = {}
        self._lock = threading.Lock()

        self._sentinel = object()

    def get(self, key, default=None):
        entry = self.entries.get(key)
        if entry is None:
            return default

        now = time.time()
        if now > entry[2]:
            with self._lock:
                del self.entries[key]
            return default

        entry[1] = now
        return entry[0]

    def put(self, key, value, expiry=None):
        with self._lock:
            overflow = len(self.entries) - self.max_entries
            if overflow > 0:
                # Pick the least recently used keys
                removed_keys = [key for key, value in sorted(
                    self.entries.items(), key=lambda t:t[1][1])][:overflow]
                for key in removed_keys:
                    del self.entries[key]

            now = time.time()
            self.entries[key] = [value, now, now + (expiry or self.expiry)]


LRU_CACHE = ShoddyLRU(256, 60)


def paginate_query(query, count_query, page=1, per_page=50, max_page=None):
    """
    Paginate a SQLAlchemy 2.0 query.
    
    This is a replacement for the baked_paginate function that uses SQLAlchemy 2.0 style.
    """
    if page < 1:
        flask.abort(404)

    if max_page and page > max_page:
        flask.abort(404)

    # Count all items, use cache
    if app.config.get('COUNT_CACHE_DURATION'):
        # Create a cache key based on the query and parameters
        # This is a simplified version compared to the bakery's _effective_key
        query_key = str(count_query)
        total_query_count = LRU_CACHE.get(query_key)
        if total_query_count is None:
            total_query_count = db.session.execute(count_query).scalar_one()
            LRU_CACHE.put(query_key, total_query_count, expiry=app.config['COUNT_CACHE_DURATION'])
    else:
        total_query_count = db.session.execute(count_query).scalar_one()

    # Apply pagination
    paginated_query = query.limit(per_page).offset((page - 1) * per_page)
    items = db.session.execute(paginated_query).scalars().all()

    if max_page:
        total_query_count = min(total_query_count, max_page * per_page)

    # Handle case where we've had no results but then have some while in cache
    total_query_count = max(total_query_count, len(items))

    if not items and page != 1:
        flask.abort(404)

    return CustomPagination(None, page, per_page, total_query_count, items)


# Alias for backward compatibility
baked_paginate = paginate_query
