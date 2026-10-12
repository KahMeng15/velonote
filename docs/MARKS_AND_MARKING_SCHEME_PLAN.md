# Marks & Marking Scheme — Master Implementation Plan

## Overview

Add hierarchical marks (points) and marking schemes to the exercise system. Each question can have sub-parts (3 levels deep), each with its own marks and marking criteria. The AI pipeline generates these during import/creation. Interactive modes show marks awarded per criterion with rationale.

---

## 1. Data Model

### 1A. Question JSON Structure (file: `uploads/{user_id}/exercises/{id}.json`)

```json
{
  "id": "1",
  "question_text": "Solve the quadratic equation",
  "answer_text": "x = 2 or x = -2",
  "question_type": "subjective",
  "max_marks": 6,
  "sub_parts": [
    {
      "id": "1a",
      "label": "a",
      "question_text": "Write the quadratic formula",
      "answer_text": "x = (-b ± sqrt(b²-4ac)) / 2a",
      "max_marks": 2,
      "question_type": "subjective",
      "sub_parts": [],
      "marking_scheme": [
        { "criterion": "Correct formula", "max_points": 1, "description": "x = (-b ± sqrt(b²-4ac)) / 2a" },
        { "criterion": "Correct notation", "max_points": 1, "description": "Uses ± and sqrt properly" }
      ]
    },
    {
      "id": "1b",
      "label": "b",
      "question_text": "Solve x² - 4 = 0 using the formula",
      "answer_text": "x = 2, x = -2",
      "max_marks": 4,
      "question_type": "subjective",
      "sub_parts": [
        {
          "id": "1bi",
          "label": "i",
          "question_text": "Identify a, b, c",
          "answer_text": "a=1, b=0, c=-4",
          "max_marks": 1,
          "sub_parts": [],
          "marking_scheme": []
        },
        {
          "id": "1bii",
          "label": "ii",
          "question_text": "Substitute and solve",
          "answer_text": "x = 2, x = -2",
          "max_marks": 3,
          "sub_parts": [],
          "marking_scheme": [
            { "criterion": "Correct substitution", "max_points": 1, "description": "Plugged in values correctly" },
            { "criterion": "Correct arithmetic", "max_points": 1, "description": "Simplified correctly" },
            { "criterion": "Both solutions found", "max_points": 1, "description": "x = 2 AND x = -2" }
          ]
        }
      ],
      "marking_scheme": []
    }
  ],
  "marking_scheme": []
}
```

- Parent `max_marks` = sum of all sub-part marks (auto-computed)
- `marking_scheme` at any level that needs it
- Sub-part nesting supports: `""` (no sub-parts), `["a", "b"]` (2-level), `["ai", "aii"]` (3-level)

### 1B. Pydantic Schemas (`app/schemas/exercise.py`)

```python
class MarkingCriterion(BaseModel):
    criterion: str
    max_points: int
    description: str = ""

class ExerciseSubPart(BaseModel):
    id: str
    label: str                                   # "a", "b", "i", "ii"
    question_text: str
    answer_text: str
    max_marks: int = 0
    question_type: str = "subjective"
    options: Any | None = None
    sub_parts: list[ExerciseSubPart] = []
    marking_scheme: list[MarkingCriterion] = []

class ExerciseQuestionBase(BaseModel):
    question_text: str
    answer_text: str
    question_type: str = "subjective"
    max_marks: int = 0
    sub_parts: list[ExerciseSubPart] = []
    marking_scheme: list[MarkingCriterion] = []
    # ... existing fields ...

class CriterionResult(BaseModel):
    criterion: str
    max_points: int
    awarded_points: int
    rationale: str

class GradeResponse(BaseModel):
    total_awarded: int
    total_max: int
    criterion_results: list[CriterionResult]
    feedback: str
    correct_answer: str

class ExerciseStateSave(BaseModel):
    userAnswers: dict = {}
    gradingResults: dict = {}                    # {qId or subPartId: GradeResponse}
    explanations: dict = {}
    revealedAnswers: dict = {}
    showExplanations: dict = {}

class BulkExerciseQuestionUpdate(BaseModel):
    # ... existing fields ...
    max_marks: int = 0
    sub_parts: list[ExerciseSubPart] = []
    marking_scheme: list[MarkingCriterion] = []
```

### 1C. Database Changes (`app/models/db.py`)

**StudySession** — add mark tracking columns:

```python
class StudySession(Base):
    # ... existing fields ...
    total_marks = Column(Integer, default=0)       # max possible marks
    awarded_marks = Column(Integer, default=0)     # marks scored
    question_scores = Column(JSON, nullable=True)  # {qId: {awarded, max, criteria: [...]}}
```

**Migration** (`app/utils/db.py`):

```python
def apply_marks_migration():
    """ALTER TABLE study_sessions ADD COLUMN total_marks INTEGER DEFAULT 0;
       ALTER TABLE study_sessions ADD COLUMN awarded_marks INTEGER DEFAULT 0;
       ALTER TABLE study_sessions ADD COLUMN question_scores JSON;"""
```

Add call in `init_db()`.

---

## 2. Pipeline Changes (`app/processing/exercise_processor.py`)

### 2A. Import Extraction Prompt Update

**`process_exercise_task` — line ~300-333**: Update the system prompt to extract marks, sub-parts, and marking schemes:

```
For each question, extract:
- "max_marks": Total marks available (integer). Detect from patterns like "(4 marks)", "[4]", "4 points" in the text. Default 1 if not found.
- "sub_parts": Array of sub-questions if the question has labeled parts (a, b, c or i, ii, iii). Each with:
    - "label": "a", "b", "i", "ii" (the letter/number prefix)
    - "question_text": The sub-part question text
    - "answer_text": The sub-part answer
    - "max_marks": Marks for this sub-part
    - "sub_parts": Nested sub-parts (for 3-level like 1a(i))
    - "question_type": Same classification as parent
    - "options": For objective sub-parts
- "marking_scheme": Array of marking criteria, each with:
    - "criterion": Short name (e.g., "Correct formula")
    - "max_points": Points for this criterion
    - "description": What constitutes meeting this criterion
```

If the source text has sub-parts (detected by `a)`, `(b)`, `i.` patterns after question text), the AI splits them. Otherwise `sub_parts` is empty.

### 2B. AI Generation Prompt Update

**`generate_exercise_task` — line ~703-749**: Add to the output format specification:

```json
{
  "question_text": "...",
  "answer_text": "...",
  "question_type": "...",
  "max_marks": 5,
  "sub_parts": [
    {
      "label": "a",
      "question_text": "...",
      "answer_text": "...",
      "max_marks": 2,
      "sub_parts": [],
      "marking_scheme": [
        { "criterion": "...", "max_points": 2, "description": "..." }
      ]
    }
  ],
  "marking_scheme": [...]
}
```

Add instruction: *"For complex questions, break them into sub-parts (max 3 levels deep). Assign marks proportionally based on difficulty/complexity."*

### 2C. Normalization & Validation

Add `_normalize_question_structure()` function (called after AI parsing):

```python
def _normalize_question_structure(q: dict) -> dict:
    """Validate and normalize marks, sub_parts, marking_scheme."""
    # 1. Ensure max_marks is int >= 0, default 1
    # 2. If sub_parts exist, compute parent max_marks = sum of children
    # 3. Validate sub_part nesting (max 3 levels)
    # 4. Assign defaults to marking_scheme if missing
    # 5. Flatten to ensure every question/sub_part has id
    return q
```

### 2D. AI Grading Update (`grade_answer()`)

Replace simple `ExerciseCheckResponse` with per-criterion grading:

```python
def grade_answer(user, question, user_answer, sub_part_id=None) -> GradeResponse:
    if question.get("question_type") == "objective":
        # Full marks or zero, single criterion
        is_correct = exact_match_logic()
        return GradeResponse(
            total_awarded=question["max_marks"] if is_correct else 0,
            total_max=question["max_marks"],
            criterion_results=[CriterionResult(
                criterion="Correct answer",
                max_points=question["max_marks"],
                awarded_points=question["max_marks"] if is_correct else 0,
                rationale="Answer matches" if is_correct else "Answer does not match"
            )],
            feedback="Correct!" if is_correct else "Incorrect.",
            correct_answer=question["answer_text"]
        )

    # Subjective — use AI with marking scheme context
    marking_scheme = question.get("marking_scheme", [])
    prompt = f"""
Question: {question.get("question_text")}
Max Marks: {question.get("max_marks")}
Marking Scheme: {json.dumps(marking_scheme)}
Sub-parts: {json.dumps(question.get("sub_parts", []))}
User's Answer: {user_answer}

Grade against EACH criterion in the marking scheme. Return strict JSON:
{{
  "total_awarded": int,
  "total_max": int,
  "criterion_results": [
    {{"criterion": str, "max_points": int, "awarded_points": int, "rationale": str}}
  ],
  "feedback": str (brief summary)
}}
"""
    # Parse response, return GradeResponse
```

For questions with sub-parts, the frontend calls `/grade` per sub-part (each sub-part has its own `id`). Or a single call grades all sub-parts and returns aggregated results.

### 2E. Submission Session Save

New helper to persist graded session:

```python
def save_graded_session(db, user, exercise_id, awarded_marks, total_marks,
                         question_scores, duration_minutes=None):
    """Create/update StudySession with mark breakdown."""
```

---

## 3. API Endpoint Changes (`app/routers/exercises.py`)

### 3A. Grade Endpoint Update

**`POST /exercises/{id}/questions/{qId}/grade`** — now returns `GradeResponse`:

```python
@router.post("/{exercise_id}/questions/{question_id}/grade", response_model=GradeResponse)
def grade_exercise_answer(...):
    question = find_question(questions, question_id)
    if question.get("options") and question["question_type"] == "objective":
        return GradeResponse(full_marks_or_zero)
    return grade_answer(current_user, question, req.user_answer)
```

If `question_id` is a sub-part id (e.g., `"1a"`), find it recursively via `_find_sub_part()`.

### 3B. Submission Endpoint

```python
@router.post("/{exercise_id}/submit")
def submit_exercise_session(exercise_id, payload: ExerciseSessionSubmit, ...):
    """Save graded session to study_sessions."""
    session = StudySession(
        user_id=current_user.id,
        resource_id=exercise.resource_id,
        session_type="exercise",
        total_marks=payload.total_marks,
        awarded_marks=payload.awarded_marks,
        question_scores=payload.question_scores,
        duration_minutes=payload.duration_minutes,
    )
    db.add(session)
    db.commit()
    return {"message": "Session saved", "session_id": session.id}
```

New schema:

```python
class ExerciseSessionSubmit(BaseModel):
    awarded_marks: int
    total_marks: int
    question_scores: dict
    duration_minutes: int = 0
```

### 3C. Historical Sessions Endpoint

```python
@router.get("/{exercise_id}/sessions")
def get_exercise_sessions(exercise_id, ...):
    """Return past study sessions for this exercise."""
```

---

## 4. Frontend Changes (`frontend/src/pages/ExerciseView.jsx`)

### 4A. Type Updates

All question mapping functions need to handle `max_marks`, `sub_parts`, `marking_scheme`. The `gradingResults` state now stores `GradeResponse` objects instead of `{is_correct, feedback, correct_answer}`.

### 4B. Marks Badge (All Modes)

In each question `Card` header (line ~1149), after the difficulty/topic row:

```jsx
<Group gap={8} wrap="nowrap">
  {q.max_marks > 0 && (
    <Badge size="sm" variant="light" color="blue" radius="sm">
      {q.max_marks} {q.max_marks === 1 ? 'mark' : 'marks'}
    </Badge>
  )}
  {/* existing difficulty/topic badges */}
</Group>
```

For sub-parts, show marks inline with sub-part label.

### 4C. Sub-Part Rendering (All Modes)

After question text (line ~1155), recursively render sub-parts:

```
<Box ml="lg" mt="md" style={{borderLeft: '2px solid #eee', paddingLeft: 16}}>
  {q.sub_parts.map(sp => <SubPartRenderer key={sp.id} part={sp} />)}
</Box>
```

`SubPartRenderer` component:
- Shows `(a)` label with `[2 marks]` badge
- Renders `question_text`
- If `sub_parts.length > 0`, recurses
- For **interactive/exam mode**: renders input (Textarea or Radio) for this sub-part
- For **show/hide mode**: renders answer with blur/reveal
- Has its own grade state if interactive

### 4D. Interactive Mode — Grading Display

Replace the current simple Alert (line ~1218) with marks-aware display:

```jsx
{hasGraded && (
  <Box mt="md">
    <Alert
      color={grade.total_awarded === grade.total_max ? 'green' :
             grade.total_awarded > 0 ? 'yellow' : 'red'}
    >
      <Group justify="space-between" wrap="nowrap">
        <Box>
          <Text fw={600} size="md">
            Score: {grade.total_awarded}/{grade.total_max}
          </Text>
          {grade.total_awarded < grade.total_max && (
            <Text size="sm" mt={2}>{grade.feedback}</Text>
          )}
        </Box>
        <Badge size="lg" color={
          grade.total_awarded === grade.total_max ? 'green' :
          grade.total_awarded > 0 ? 'yellow' : 'red'
        }>
          {grade.total_awarded === grade.total_max ? 'Perfect!' :
           grade.total_awarded > 0 ? 'Partial' : 'Incorrect'}
        </Badge>
      </Group>
    </Alert>

    {/* Per-criterion breakdown */}
    {grade.criterion_results?.length > 0 && (
      <Paper mt="sm" p="sm" withBorder radius="md">
        <Text size="sm" fw={600} mb="xs" c="dimmed">Marking Breakdown</Text>
        {grade.criterion_results.map((cr, i) => (
          <Group key={i} justify="space-between" wrap="nowrap" py={6}
            style={{borderBottom: i < grade.criterion_results.length - 1 ? '1px solid #f0f0f0' : 'none'}}>
            <Box style={{flex: 1}}>
              <Text size="sm" fw={500}>{cr.criterion}</Text>
              <Text size="xs" c="dimmed">{cr.rationale}</Text>
            </Box>
            <Badge size="sm" variant="light" color={
              cr.awarded_points === cr.max_points ? 'green' :
              cr.awarded_points > 0 ? 'yellow' : 'red'
            }>
              {cr.awarded_points}/{cr.max_points}
            </Badge>
          </Group>
        ))}
      </Paper>
    )}
  </Box>
)}
```

### 4E. Check All / Submit Exam — Score Summary

After all questions graded, show a summary banner above the buttons:

```jsx
{(() => {
  const entries = Object.entries(gradingResults);
  if (entries.length === 0) return null;
  const totalMax = entries.reduce((s, [, g]) => s + (g.total_max || 0), 0);
  const totalAwarded = entries.reduce((s, [, g]) => s + (g.total_awarded || 0), 0);
  return (
    <Paper p="lg" withBorder mb="xl" radius="md" bg="gray.0">
      <Group justify="space-between" wrap="nowrap">
        <Box>
          <Title order={4}>Score Summary</Title>
          <Text size="xl" fw={700} mt={4}>
            {totalAwarded} / {totalMax}
          </Text>
          <Text size="sm" c="dimmed">{exercise.questions?.length || 0} questions</Text>
        </Box>
        <RingProgress
          size={90}
          thickness={10}
          sections={[{ value: totalMax > 0 ? (totalAwarded/totalMax)*100 : 0, color: totalAwarded === totalMax ? 'green' : 'blue' }]}
          label={<Text ta="center" size="sm" fw={700}>{totalMax > 0 ? Math.round((totalAwarded/totalMax)*100) : 0}%</Text>}
        />
      </Group>
    </Paper>
  );
})()}
```

### 4F. Sidebar — Session Score

After grading, update Exercise Info sidebar panel (line ~1724) to show session score:

```jsx
{Object.keys(gradingResults).length > 0 && (
  <>
    <Divider my={4} />
    <Group justify="space-between" wrap="nowrap">
      <Text size="xs" fw={600} c="dimmed">Session Score</Text>
      <Text size="xs" fw={700}>
        {sessionAwarded}/{sessionTotal}
      </Text>
    </Group>
    <Group justify="space-between" wrap="nowrap">
      <Text size="xs" fw={600} c="dimmed">Percentage</Text>
      <Text size="xs" fw={700} c={pct >= 80 ? 'green' : pct >= 50 ? 'yellow' : 'red'}>
        {pct}%
      </Text>
    </Group>
  </>
)}
```

### 4G. Recent Activity — Show Marks

Replace binary correct/wrong badges with score badges (line ~1937):

```jsx
<Badge size="xs" color={statusColor} variant="light">
  {grade ? `${grade.total_awarded}/${grade.total_max}` : statusLabel}
</Badge>
```

### 4H. History Modal — Marking Rationale

In the History Modal (line ~2076), replace simple Alert with full breakdown:

```jsx
{historyModalQuestion.grade && (
  <Box>
    <Alert color={...} icon={...}>
      Score: {grade.total_awarded}/{grade.total_max}
    </Alert>
    {grade.criterion_results?.length > 0 && (
      <Paper mt="sm" p="sm" withBorder>
        <Text fw={600} size="sm" mb="xs">Marking Breakdown</Text>
        {grade.criterion_results.map((cr, i) => (
          <Group key={i} justify="space-between" py={4}>
            <Text size="sm">{cr.criterion}: <i>{cr.rationale}</i></Text>
            <Badge size="sm">{cr.awarded_points}/{cr.max_points}</Badge>
          </Group>
        ))}
      </Paper>
    )}
  </Box>
)}
```

### 4I. Edit Mode — Marks + Sub-Parts + Marking Scheme Editor

In edit mode (line ~940), add per-question:

```
<NumberInput label="Max Marks" value={q.max_marks} onChange={...} min={0} />

{/* Sub-part editor */}
<Box mt="sm">
  <Text size="sm" fw={500}>Sub-parts</Text>
  {q.sub_parts.map((sp, spIdx) => (
    <SubPartEditor key={sp.id} part={sp} onChange={...} onRemove={...} depth={1} />
  ))}
  <Button variant="light" size="xs" onClick={addSubPart}>+ Add Sub-part</Button>
</Box>

{/* Marking scheme editor */}
<Box mt="sm">
  <Text size="sm" fw={500}>Marking Scheme</Text>
  {q.marking_scheme.map((mc, mcIdx) => (
    <Group key={mcIdx}>
      <TextInput value={mc.criterion} onChange={...} placeholder="Criterion" />
      <NumberInput value={mc.max_points} onChange={...} min={0} />
      <TextInput value={mc.description} onChange={...} placeholder="Description" />
      <ActionIcon color="red" onClick={removeCriterion}><IconX /></ActionIcon>
    </Group>
  ))}
  <Button variant="light" size="xs" onClick={addCriterion}>+ Add Criterion</Button>
</Box>
```

`SubPartEditor` is recursive with depth limit of 3. Each sub-part has its own marking scheme editor.

### 4J. Auto-Save Session on Exam Submit / Check All

After `handleSubmitExam()` or `handleCheckAll()`, call:

```js
await fetchApi(`/exercises/${id}/submit`, {
  method: 'POST',
  body: JSON.stringify({
    awarded_marks: totalAwarded,
    total_marks: totalMax,
    question_scores: gradingResults, // {qId: GradeResponse}
    duration_minutes: examTimerMinutes - Math.floor(examTimeRemaining / 60)
  })
});
```

---

## 5. Implementation Order

| # | Task | Key Files | Est. |
|---|------|-----------|------|
| 1 | DB migration: add mark columns to study_sessions | `app/utils/db.py`, `app/models/db.py` | S |
| 2 | Pydantic schemas: `MarkingCriterion`, `ExerciseSubPart`, `GradeResponse`, `ExerciseSessionSubmit` | `app/schemas/exercise.py` | M |
| 3 | Update `grade_answer()` → per-criterion grading with marks | `app/processing/exercise_processor.py` | L |
| 4 | Update grade API endpoint → return `GradeResponse` | `app/routers/exercises.py` | S |
| 5 | Add `_normalize_question_structure()` to validate marks/sub-parts | `app/processing/exercise_processor.py` | M |
| 6 | Update AI extraction prompt for marks/sub-parts/marking-scheme | `app/processing/exercise_processor.py` | M |
| 7 | Update AI generation prompt for marks/sub-parts/marking-scheme | `app/processing/exercise_processor.py` | M |
| 8 | Add submit session endpoint | `app/routers/exercises.py` | S |
| 9 | Backward-compat: handle old questions without `max_marks` | `app/processing/exercise_processor.py`, `app/routers/exercises.py` | S |
| 10 | Frontend: update types + add marks badge to all views | `ExerciseView.jsx` | M |
| 11 | Frontend: recursive sub-part renderer + inputs | `ExerciseView.jsx` | L |
| 12 | Frontend: per-criterion grading display with rationale | `ExerciseView.jsx` | L |
| 13 | Frontend: score summary (Check All / Submit Exam) | `ExerciseView.jsx` | M |
| 14 | Frontend: sidebar session score + recent activity marks | `ExerciseView.jsx` | M |
| 15 | Frontend: history modal marking breakdown | `ExerciseView.jsx` | M |
| 16 | Frontend: edit mode for marks/sub-parts/marking-scheme | `ExerciseView.jsx` | XL |
| 17 | Frontend: auto-save session on submit | `ExerciseView.jsx` | S |
| 18 | Update PDF/DOCX export to include marks + marking scheme | `app/routers/exercises.py` | M |
| 19 | Update StudySession analytics to use mark-based scoring | `app/routers/analytics.py` | S |
| 20 | Update SubjectView exercise cards to show total marks | `SubjectView.jsx` | S |

**S** = small (~30min), **M** = medium (~1-2hr), **L** = large (~3-4hr), **XL** = very large (~6-8hr)

---

## 6. Backward Compatibility

- Existing questions without `max_marks` → default to `0`, hide marks badge
- Existing questions without `sub_parts` → treat as flat, empty array
- Existing questions without `marking_scheme` → AI grading falls back to generic (no per-criterion breakdown)
- Old `ExerciseCheckResponse` format → frontend normalizes: if `is_correct` and no `total_awarded`, treat as max_marks=1, awarded=1 or 0
- Migration for `study_sessions`: nullable new columns, existing rows get `NULL`

---

## 7. Edge Cases

| Scenario | Handling |
|----------|----------|
| Sub-part max_marks sum ≠ parent max_marks | Auto-set parent max_marks = sum on save |
| Mix of sub-questions and no sub-questions in same exercise | Each question independent; no cross-question constraints |
| User edits marks mid-session | Re-grade uses updated marking scheme |
| Sub-part grading of wrong type (e.g., objective inside subjective parent) | Each sub-part graded independently by its own `question_type` |
| AI fails to generate marking scheme | `marking_scheme` = empty; grading falls to single criterion "Correct answer" |
| Sub-part label collisions | IDs are unique (e.g., "1a", "1b", "1bi") — no collisions |
| Very large sub-part trees | 3-level limit enforced in `_normalize_question_structure()`; deeper nesting flattened |
