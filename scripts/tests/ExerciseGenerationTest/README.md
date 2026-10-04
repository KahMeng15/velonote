# Exercise Generation Test

This folder contains a test script to evaluate the AI exercise generation prompt without having to run the full FastAPI server and frontend. It mimics the same background worker logic found in `app.processing.exercise_processor.generate_exercise_task`.

## Usage

1. Place your target file(s) into the `input` directory. Supported formats:
   - `.pdf`
   - `.pptx`
   - `.md`
   - `.txt`
2. Run the test script from the project root:
   ```bash
   python scripts/ExerciseGenerationTest/run_generation.py
   ```
3. Check the `output` directory for the results:
   - `debug_log.txt`: Detailed log of what was processed.
   - `raw_ai_response.txt`: The exact raw text output from the AI.
   - `parsed_exercise.json`: The successfully parsed JSON array of questions.

## Customizing Parameters
If you want to test different combinations of difficulty, question types, lengths, or the number of questions, open `run_generation.py` and modify the parameters defined around line 76:

```python
    question_types = "Short answer, Long answer, Objective, Fill in the blank"
    lengths = "Short, Medium, Long"
    difficulties = "Easy, Medium, Hard"
    num_questions = 5
```
