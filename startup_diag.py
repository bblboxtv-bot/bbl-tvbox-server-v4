def report(main):
    c = main.db_connect()
    try:
        cur = main.execute(c, "SELECT COUNT(*) AS total, COUNT(apk_blob) AS saved FROM apps")
        row = main.rowd(cur.fetchone(), cur) or {}
        print(f"APK_STORAGE total={row.get('total', 0)} saved={row.get('saved', 0)}", flush=True)
    finally:
        c.close()
