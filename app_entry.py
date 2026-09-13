import os
import sqlite3
import main
from panel_v5 import install_panel


def fixed_db_connect():
    url = main.DATABASE_URL
    if url.startswith(('postgres://', 'postgresql://')):
        import psycopg
        url = url.replace('postgres://', 'postgresql://', 1)
        if 'sslmode=' not in url:
            url += ('&' if '?' in url else '?') + 'sslmode=require'
        return psycopg.connect(url, autocommit=False)
    p = url.replace('sqlite:///', '', 1) if url.startswith('sqlite:///') else url
    c = sqlite3.connect(p)
    c.row_factory = sqlite3.Row
    return c

main.db_connect = fixed_db_connect

install_panel(
    main.app,
    db_connect=main.db_connect,
    execute=main.execute,
    rowd=main.rowd,
    admin_ok=main.admin_ok,
    apk_meta=main.apk_meta,
    upload_dir=main.UPLOAD_DIR,
    now_iso=main.now_iso,
    log=main.log,
)

app = main.app
