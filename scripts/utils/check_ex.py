import json
from sqlalchemy import create_engine, text

engine = create_engine('postgresql://mysmartnotes:mysmartnotespassword@localhost:5432/mysmartnotes')
with engine.connect() as conn:
    res = conn.execute(text("SELECT id, content_path FROM exercises WHERE id='ex_94101a3d'"))
    row = res.fetchone()
    if row:
        print(f"ID: {row[0]}")
        print(f"Content Path: {row[1]}")
    else:
        print("Exercise not found.")
