import main
from render_db_fix import prefer_private_render_postgres

main.DATABASE_URL = prefer_private_render_postgres(main.DATABASE_URL)

from app_entry import app
