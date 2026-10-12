import json

data = [
  {
    "question_text": "Two relations R1 and R2 are defined as below:\nR1 = {(2,2), (3,1), (3,5)}\nR2 = {(1,2), (2,1), (3,1)}\nCombine the relations using the following set operations.",
    "original_number": "1",
    "answer_text": "{(1,2), (2,1), (2,2), (3,1), (3,5)}",
    "question_type": "objective",
    "options": [
      "{(1,2), (2,1), (2,2), (3,1), (3,5)}",
      "{(2,2), (3,1), (3,5)}",
      "{(1,2), (2,1), (3,1)}",
      "{(2,2), (3,5)}"
    ],
    "topic": "Set Theory",
    "difficulty": "Medium",
    "max_marks": 1,
    "sub_parts": [],
    "marking_scheme": [],
    "reference_resource_id": None,
    "reference_resource_title": "Page 1",
    "reference_quote": "Combine the relations using the following set operations.",
    "order": 0,
    "id": "1"
  },
  {
    "question_text": "Let R1 and R2 be relations on set A = {a, b, c} represented by matrices.\nFind the matrix that represents R1 ∪ R2.",
    "original_number": "2",
    "answer_text": "[\n  0, 1, 0\n  1, 1, 1\n  1, 1, 1\n]",
    "question_type": "objective",
    "options": [
      "[\n  0, 1, 0\n  1, 1, 1\n  1, 1, 1\n]",
      "[\n  0, 1, 1\n  1, 1, 1\n  1, 1, 1\n]",
      "[\n  0, 1, 0\n  1, 1, 1\n  1, 0, 1\n]",
      "[\n  0, 1, 0\n  1, 1, 1\n  0, 1, 1\n]"
    ],
    "topic": "Matrix",
    "difficulty": "Medium",
    "max_marks": 2,
    "sub_parts": [],
    "marking_scheme": [],
    "reference_resource_id": None,
    "reference_resource_title": "Page 1",
    "reference_quote": "Find the matric that represent .      R1 ∪ R2",
    "order": 1,
    "id": "2"
  },
  {
    "question_text": "Use mathematical induction to prove that:\n2 + 4 + 6 + ... + 2n = n^2 + n\nfor all integers n ≥ 1.",
    "original_number": "3",
    "answer_text": "Proof by mathematical induction",
    "question_type": "subjective",
    "options": None,
    "topic": "Mathematical Induction",
    "difficulty": "Hard",
    "max_marks": 5,
    "sub_parts": [],
    "marking_scheme": [],
    "reference_resource_id": None,
    "reference_resource_title": "Page 3",
    "reference_quote": "Use mathematical induction to prove that: 2 + 4 + 6 + ... + 2n = n^2 + n for all integers n ≥ 1.",
    "order": 2,
    "id": "3"
  },
  {
    "question_text": "Given a sequence a1, a2, a3, ... is a recurrence relation defined as below:",
    "original_number": "5",
    "answer_text": "a1 = 1, a2 = 7, a3 = 15, a4 = 27, a5 = 42",
    "question_type": "objective",
    "options": [
      "a1 = 1, a2 = 7, a3 = 15, a4 = 27, a5 = 42",
      "a1 = 2, a2 = 8, a3 = 16, a4 = 28, a5 = 44",
      "a1 = 3, a2 = 9, a3 = 17, a4 = 29, a5 = 45",
      "a1 = 4, a2 = 10, a3 = 18, a4 = 30, a5 = 46"
    ],
    "topic": "Recurrence Relation",
    "difficulty": "Medium",
    "max_marks": 2,
    "sub_parts": [],
    "marking_scheme": [],
    "reference_resource_id": None,
    "reference_resource_title": "Page 5",
    "reference_quote": "Given a sequence a1, a2, a3, ... is a recurrence relation as defined below:",
    "order": 3,
    "id": "4"
  },
  {
    "question_text": "Show that 4^n is a solution to the recurrence relation a_n = 3a_{n-1} + 4a_{n-2}.",
    "original_number": "6",
    "answer_text": "Yes",
    "question_type": "objective",
    "options": [
      "Yes",
      "No",
      "Undecided",
      "Depends on n"
    ],
    "topic": "Recurrence Relation",
    "difficulty": "Medium",
    "max_marks": 1,
    "sub_parts": [],
    "marking_scheme": [],
    "reference_resource_id": None,
    "reference_resource_title": "Page 4",
    "reference_quote": "Show that 4^n is a solution to the recurrence relation a_n = 3a_{n-1} + 4a_{n-2}.",
    "order": 4,
    "id": "5"
  },
  {
    "question_text": "Write down a recurrence relation for the health policy's value after n years.",
    "original_number": "7",
    "answer_text": "a_n = (1.05)a_{n-1}, with a_0 = 1500",
    "question_type": "objective",
    "options": [
      "a_n = (1.05)a_{n-1}, with a_0 = 1500",
      "a_n = (1.05)a_{n-1}, with a_0 = 1501",
      "a_n = (1.05)a_{n-1}, with a_0 = 1502",
      "a_n = (1.05)a_{n-1}, with a_0 = 1503"
    ],
    "topic": "Compound Interest",
    "difficulty": "Medium",
    "max_marks": 1,
    "sub_parts": [],
    "marking_scheme": [],
    "reference_resource_id": None,
    "reference_resource_title": "Page 6",
    "reference_quote": "Write down a recurrence relation for the health policy's value after n years.",
    "order": 5,
    "id": "6"
  },
  {
    "question_text": "Find the close form equation for the recurrence relation in (i).",
    "original_number": "7",
    "answer_text": "a_n = 1500(1.05)^n",
    "question_type": "objective",
    "options": [
      "a_n = 1500(1.05)^n",
      "a_n = 1501(1.05)^n",
      "a_n = 1502(1.05)^n",
      "a_n = 1503(1.05)^n"
    ],
    "topic": "Compound Interest",
    "difficulty": "Medium",
    "max_marks": 1,
    "sub_parts": [],
    "marking_scheme": [],
    "reference_resource_id": None,
    "reference_resource_title": "Page 6",
    "reference_quote": "Find the close form equation for the recurrrence relation in ( i ).",
    "order": 6,
    "id": "7"
  }
]

with open('/Users/kahmeng/Documents/GitHub/velonote/data/users/unowned/exercises/ex_94101a3d.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
