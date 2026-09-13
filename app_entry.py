import main
from panel_v5 import install_panel

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
