import hashlib
import secrets
from pathlib import Path

from fastapi import File, HTTPException, UploadFile
from fastapi.responses import FileResponse, RedirectResponse, Response

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


@main.app.on_event("startup")
def ensure_apk_blob_column():
    c = main.db_connect()
    try:
        main.execute(c, "ALTER TABLE apps ADD COLUMN apk_blob BYTEA")
        c.commit()
    except Exception:
        c.rollback()
    finally:
        c.close()


async def persistent_apps_upload(key: str = "", apk: UploadFile = File(...)):
    if not main.admin_ok(key):
        raise HTTPException(401, "chave administrativa inválida")
    if not apk.filename or not apk.filename.lower().endswith(".apk"):
        raise HTTPException(400, "envie um arquivo APK")

    data = await apk.read()
    if not data:
        raise HTTPException(400, "APK vazio")

    safe = f"{secrets.token_hex(8)}.apk"
    dest = Path(main.UPLOAD_DIR) / safe
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)

    meta = main.apk_meta(dest)
    sha = hashlib.sha256(data).hexdigest()
    aid = secrets.token_hex(8)

    c = main.db_connect()
    cur = main.execute(
        c,
        "SELECT id,filename FROM apps WHERE package_name=?",
        (meta.get("package_name") or "",),
    )
    old = main.rowd(cur.fetchone(), cur) if meta.get("package_name") else None

    if old:
        oldp = Path(main.UPLOAD_DIR) / old["filename"]
        main.execute(
            c,
            "UPDATE apps SET name=?,version_name=?,version_code=?,filename=?,size_bytes=?,sha256=?,created_at=?,apk_blob=? WHERE id=?",
            (
                meta["name"],
                meta.get("version_name", ""),
                meta.get("version_code", ""),
                safe,
                len(data),
                sha,
                main.now_iso(),
                data,
                old["id"],
            ),
        )
        try:
            if oldp.exists() and oldp != dest:
                oldp.unlink()
        except Exception:
            pass
    else:
        main.execute(
            c,
            "INSERT INTO apps(id,name,package_name,version_name,version_code,filename,size_bytes,sha256,created_at,apk_blob) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                aid,
                meta["name"],
                meta.get("package_name", ""),
                meta.get("version_name", ""),
                meta.get("version_code", ""),
                safe,
                len(data),
                sha,
                main.now_iso(),
                data,
            ),
        )
    c.commit()
    c.close()
    return RedirectResponse(f"/painel/apps?key={key}", 303)


def persistent_app_download(aid: str):
    c = main.db_connect()
    cur = main.execute(c, "SELECT filename,apk_blob FROM apps WHERE id=?", (aid,))
    row = main.rowd(cur.fetchone(), cur)
    c.close()
    if not row:
        raise HTTPException(404, "aplicativo não encontrado")

    blob = row.get("apk_blob")
    if blob:
        headers = {"Content-Disposition": f'attachment; filename="{row["filename"]}"'}
        return Response(
            content=bytes(blob),
            media_type="application/vnd.android.package-archive",
            headers=headers,
        )

    p = Path(main.UPLOAD_DIR) / row["filename"]
    if p.exists():
        return FileResponse(
            p,
            media_type="application/vnd.android.package-archive",
            filename=row["filename"],
        )

    raise HTTPException(404, "arquivo APK ausente no servidor; envie o APK novamente pelo painel")


def add_priority_route(path, endpoint, methods):
    main.app.add_api_route(path, endpoint, methods=methods)
    route = main.app.router.routes.pop()
    main.app.router.routes.insert(0, route)


add_priority_route("/painel/apps/upload", persistent_apps_upload, ["POST"])
add_priority_route("/admin/apps/upload", persistent_apps_upload, ["POST"])
add_priority_route("/api/apps/{aid}/download", persistent_app_download, ["GET"])

app = main.app
