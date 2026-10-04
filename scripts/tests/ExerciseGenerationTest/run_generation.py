import sys, os, secrets
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(dotenv_path=_PROJECT_ROOT / ".env")

from app.utils.db import SessionLocal
from app.models.db import Exercise
from app.processing.exercise_processor import process_exercise_task

db = SessionLocal()
file_id = f"ex_{secrets.token_hex(4)}"
original_ex_id = "ex_c6212e8d"

file_path = "/Users/kahmeng/Documents/GitHub/velonote/app/data/user_2/ex_c6212e8d.pdf"

exercise = Exercise(
    id=file_id,
    user_id=2,
    subject_id="sj_01f26870",
    title=os.path.splitext("1.pdf")[0],
    file_path=file_path,
    file_name="1.pdf",
)
db.add(exercise)
db.commit()
print(f"Created exercise: {file_id}")
print(f"  File: {file_path}")
print(f"  Initial title: {exercise.title}")

print("Processing file to extract questions and title...")
process_exercise_task(
    exercise_id=file_id,
    user_id=2,
    task_id=f"test_extract_{file_id}"
)

db.refresh(exercise)
print(f"\nFinal title: {exercise.title}")
db.close()
