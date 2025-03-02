#!/usr/bin/env python3
"""
Database creation script for Nyaa.
Compatible with Python 3.13 and SQLAlchemy 2.0.
"""
from typing import List, Tuple, Type

import sqlalchemy
from sqlalchemy import select

from nyaa import create_app, models
from nyaa.extensions import db

app = create_app('config')

NYAA_CATEGORIES: List[Tuple[str, List[str]]] = [
    ('Anime', ['Anime Music Video', 'English-translated', 'Non-English-translated', 'Raw']),
    ('Audio', ['Lossless', 'Lossy']),
    ('Literature', ['English-translated', 'Non-English-translated', 'Raw']),
    ('Live Action', ['English-translated', 'Idol/Promotional Video', 'Non-English-translated', 'Raw']),
    ('Pictures', ['Graphics', 'Photos']),
    ('Software', ['Applications', 'Games']),
]


SUKEBEI_CATEGORIES: List[Tuple[str, List[str]]] = [
    ('Art', ['Anime', 'Doujinshi', 'Games', 'Manga', 'Pictures']),
    ('Real Life', ['Photobooks / Pictures', 'Videos']),
]


def add_categories(categories: List[Tuple[str, List[str]]], 
                  main_class: Type[models.MainCategoryBase], 
                  sub_class: Type[models.SubCategoryBase]) -> None:
    """
    Add categories to the database.
    
    Args:
        categories: List of tuples containing main category name and list of subcategory names
        main_class: Main category model class
        sub_class: Subcategory model class
    """
    for main_cat_name, sub_cat_names in categories:
        main_cat = main_class(name=main_cat_name)
        for i, sub_cat_name in enumerate(sub_cat_names):
            # Composite keys can't autoincrement, set sub_cat id manually (1-index)
            sub_cat = sub_class(id=i+1, name=sub_cat_name, main_category=main_cat)
        db.session.add(main_cat)


if __name__ == '__main__':
    with app.app_context():
        # Test for the user table, assume db is empty if it's not created
        database_empty = False
        try:
            stmt = select(models.User).limit(1)
            db.session.execute(stmt).scalar_one_or_none()
        except (sqlalchemy.exc.ProgrammingError, sqlalchemy.exc.OperationalError):
            database_empty = True

        print('Creating all tables...')
        db.create_all()

        # Check if Nyaa categories exist
        stmt = select(models.NyaaMainCategory).limit(1)
        nyaa_category_test = db.session.execute(stmt).scalar_one_or_none()
        if not nyaa_category_test:
            print('Adding Nyaa categories...')
            add_categories(NYAA_CATEGORIES, models.NyaaMainCategory, models.NyaaSubCategory)

        # Check if Sukebei categories exist
        stmt = select(models.SukebeiMainCategory).limit(1)
        sukebei_category_test = db.session.execute(stmt).scalar_one_or_none()
        if not sukebei_category_test:
            print('Adding Sukebei categories...')
            add_categories(SUKEBEI_CATEGORIES, models.SukebeiMainCategory, models.SukebeiSubCategory)

        db.session.commit()

        if database_empty:
            print('Remember to run the following to mark the database up-to-date for Alembic:')
            print('./db_migrate.py stamp head')
            # Technically we should be able to do this here, but when you have
            # Flask-Migrate and Flask-SQA and everything... I didn't get it working.
