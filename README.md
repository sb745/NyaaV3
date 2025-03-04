# NyaaV3 [![python](https://img.shields.io/badge/Python-3.13-3776AB.svg?style=flat&logo=python&logoColor=white)](https://www.python.org) ![Maintenance](https://img.shields.io/maintenance/yes/2025)

## Setting up for development
This project uses Python 3.13. The codebase has been updated from the original Python 3.7 version to use modern Python features and updated dependencies.
This guide assumes you are using Linux and are somewhat capable with the commandline.   
Running Nyaa on Windows may be possible, but it's currently unsupported.

### Major changes from NyaaV2
- Updated from Python 3.7 to Python 3.13
- Updated all dependencies to their latest versions
- Modernized code patterns for Flask 3.0 and SQLAlchemy 2.0
- Replaced deprecated Flask-Script, orderedset and `flask.Markup` with Flask CLI, orderly-set and markupsafe
- Implemented mail error handling

### Code Quality
- Before we get any deeper, remember to follow PEP8 style guidelines and run `python dev.py lint` before committing to see a list of warnings/problems.
    - You may also use `python dev.py fix && python dev.py isort` to automatically fix some of the issues reported by the previous command.
- Other than PEP8, try to keep your code clean and easy to understand, as well. It's only polite!

### Running tests
The `tests` folder contains tests for the the `nyaa` module and the webserver. To run the tests:
- Make sure that you are in the Python virtual environment.
- Run `python dev.py test` while in the repository directory.

### Setting up Pyenv
pyenv eases the use of different Python versions, and as not all Linux distros offer 3.13 packages, it's right up our alley.
- Install [dependencies](https://github.com/pyenv/pyenv/wiki/Common-build-problems)
- Install [pyenv](https://github.com/pyenv/pyenv/blob/master/README.md#installation)
- Install [pyenv-virtualenv](https://github.com/pyenv/pyenv-virtualenv/blob/master/README.md)
- Install Python 3.13 with `pyenv` and create a virtualenv for the project:
    - `pyenv install 3.13.2`
    - `pyenv virtualenv 3.13.2 nyaa`
    - `pyenv activate nyaa`
- Install dependencies with `pip install -r requirements.txt`
- Copy `config.example.py` into `config.py`
    - Change `SITE_FLAVOR` in your `config.py` depending on which instance you want to host

### Setting up MySQL/MariaDB database
> [!WARNING]
> You *may* use SQLite but it is currently untested and unsupported.
- Enable `USE_MYSQL` flag in config.py
- Install MariaDB by following instructions [here](https://downloads.mariadb.org/mariadb/repositories/)
- Run the following commands logged in as your root db user (substitute for your own `config.py` values if desired):
    - `CREATE USER 'nyaauser'@'localhost' IDENTIFIED BY 'nyaapass';`
    - `CREATE DATABASE nyaav3 DEFAULT CHARACTER SET utf8 COLLATE utf8_bin;`
    - `GRANT ALL PRIVILEGES ON nyaav3.* TO 'nyaauser'@'localhost';`
    - `FLUSH PRIVILEGES;`

### Finishing up
- Run `python db_create.py` to create the database and import categories
    - ~~Follow the advice of `db_create.py` and run `python db_migrate.py stamp head` to mark the database version for Alembic~~
- Start the dev server with `python run.py`
- When you are finished developing, deactivate your virtualenv with `pyenv deactivate` or `source deactivate` (or just close your shell session)

You're now ready for simple testing and development!   
Continue below to learn about database migrations and enabling the advanced search engine, Elasticsearch.


## Database migrations
> [!WARNING]
> The database migration feature has been updated but will no longer be supported in NyaaV3. 
- Database migrations are done with [Flask-Migrate](https://flask-migrate.readthedocs.io/), a wrapper around [Alembic](http://alembic.zzzcomputing.com/en/latest/).
- The migration system has been updated to use Flask CLI instead of the deprecated Flask-Script.
- If someone has made changes in the database schema and included a new migration script:
    - If your database has never been marked by Alembic (you're on a database from before the migrations), run `python db_migrate.py db stamp head` before pulling the new migration script(s).
        - If you already have the new scripts, check the output of `python db_migrate.py db history` instead and choose a hash that matches your current database state, then run `python db_migrate.py db stamp <hash>`.
    - Update your branch (eg. `git fetch && git rebase origin/master`)
    - Run `python db_migrate.py db upgrade head` to run the migration. Done!
- If *you* have made a change in the database schema:
    - Save your changes in `models.py` and ensure the database schema matches the previous version (ie. your new tables/columns are not added to the live database)
    - Run `python db_migrate.py db migrate -m "Short description of changes"` to automatically generate a migration script for the changes
      - Check the script (`migrations/versions/...`) and make sure it works! Alembic may not able to notice all changes.
    - Run `python db_migrate.py db upgrade` to run the migration and verify the upgrade works.
       - (Run `python db_migrate.py db downgrade` to verify the downgrade works as well, then upgrade again)


## Setting up and enabling Elasticsearch

### Installing Elasticsearch
- Install JDK with `sudo apt-get install openjdk-8-jdk`
- Install Elasticsearch
    - [From packages](https://www.elastic.co/guide/en/elasticsearch/reference/current/deb.html)
        - Enable the service:
            - `sudo systemctl enable elasticsearch.service`
            - `sudo systemctl start elasticsearch.service`
    - or [simply extracting the archives and running the files](https://www.elastic.co/guide/en/elasticsearch/reference/current/_installation.html), if you don't feel like permanently installing ES
- Run `curl -XGET 'localhost:9200'` and make sure ES is running
- Install [Kibana](https://www.elastic.co/products/kibana) as a search debug frontend for ES (*optional*)

### Enabling MySQL Binlogging
- Edit your MariaDB/MySQL server configuration and add the following under `[mariadb]`:
    ```
    log-bin
    server_id=1
    log-basename=master1
    binlog-format=row
    ```
- Restart MariaDB/MySQL (`sudo service mysql restart`)
- Copy the example configuration (`es_sync_config.example.json`) as `es_sync_config.json` and adjust options in it to your liking (verify the connection options!)
- Connect to mysql as root
    - Verify that the result of `SHOW VARIABLES LIKE 'binlog_format';` is `ROW`
    - Execute `GRANT REPLICATION SLAVE ON *.* TO 'username'@'localhost';` to allow your configured user access to the binlog

### Setting up ES
- Run `./create_es.sh` to create the indices for the torrents: `nyaa` and `sukebei`
    - The output should show `acknowledged: true` twice
- Stop the Nyaa app if you haven't already
- Run `python import_to_es.py` to import all the torrents (on nyaa and sukebei) into the ES indices.
    - This may take some time to run if you have plenty of torrents in your database.

Enable the `USE_ELASTIC_SEARCH` flag in `config.py` and (re)start the application.   
Elasticsearch should now be functional! The ES indices won't be updated "live" with the current setup, continue below for instructions on how to hook Elasticsearch up to MySQL binlog.   

However, take note that binglog is not necessary for simple ES testing and development; you can simply run `import_to_es.py` from time to time to reindex all the torrents.


### Setting up sync_es.py
`sync_es.py` keeps the Elasticsearch indices updated by reading the binlog and pushing the changes to the ES indices.
- Make sure `es_sync_config.json` is configured with the user you grated the `REPLICATION` permissions
- Run `import_to_es.py` and copy the outputted JSON into the file specified by `save_loc` in your `es_sync_config.json`
- Run `sync_es.py` as-is *or*, for actual deployment, set it up as a service and run it, preferably as the system/root
    - Make sure `sync_es.py` runs within the venv with the right dependencies!

You're done! The script should now be feeding updates from the database to Elasticsearch.   
Take note, however, that the specified ES index refresh interval is 30 seconds, which may feel like a long time on local development. Feel free to adjust it or [poke Elasticsearch yourself!](https://www.elastic.co/guide/en/elasticsearch/reference/current/indices-refresh.html)

## License
This project is licensed under the GNU General Public License v3.0 (GPL-3.0). See the [LICENSE](LICENSE) file for more details.

## Disclaimer
> [!CAUTION]
> **This project was created as a learning experience, and while it's a torrent tracker, I can't control how people choose to use it.**

By using this software, you're agreeing to a few things:
- I'm not responsible for any legal issues that might come up from using this tracker, especially if it's used to share copyrighted content without permission.
- It's your responsibility to make sure you're following the laws in your area when using this software.

**Please use this project wisely and stay on the right side of the law.** Happy coding!
