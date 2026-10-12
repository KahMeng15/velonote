# Resource Processing Test Suite

Comprehensive pipeline for processing, testing, and improving document extraction from PDF, PPTX, DOCX, TXT, and images. Drop a file in `input/` and run one command.

## One Command

```bash
# From project root — process everything in input/
python scripts/resource_processing_test/process_all.py

# Process a specific file from anywhere
python scripts/resource_processing_test/process_all.py ~/Downloads/lecture.pdf

# Auto-fix: process + open correction tool for low-scoring files
python scripts/resource_processing_test/process_all.py --correct
```

**`process_all.py` is the only command you need.** It does all of this automatically:

1. Finds all files in `input/` (PDF, PPTX, DOCX, TXT, images)
2. Routes each to the right extractor — native text, scanned OCR, image extraction
3. Extracts images inline next to their related text (not dumped at the bottom)
4. Filters out logos, backgrounds, decorative elements
5. Computes quality metrics and a letter grade (A/B/C/D)
6. Saves markdown output + JSON report
7. Optionally opens the correction tool for files scoring below 90%
8. Analyzes all accumulated corrections and suggests pipeline improvements

## Quick Start

```bash
cd scripts/resource_processing_test

# One-command workflow (recommended)
python process_all.py

# With correction tool for low scores
python process_all.py --correct

# Step through each file with prompts
python process_all.py --interactive

# Run the detailed test suite with expected output comparison
python run_test.py --expected-dir expected/

# Run a specific format
python run_test.py --format pdf
python run_test.py --format pptx
python run_test.py --format image

# Compare against historical quality reports
python run_test.py --historical

# Run with AI polish (requires Ollama)
python run_test.py --polish
```

## Directory Structure

```
resource_processing_test/
├── process_all.py           # ★ One-command entry point (start here)
├── run_test.py              # Advanced test harness with expected output comparison
├── correction_tool.py       # Interactive correction CLI
├── analyze_corrections.py   # Self-improvement pattern analyzer
├── README.md                # This file
├── test_harness/
│   ├── __init__.py
│   ├── diff_engine.py       # Structural/content comparison
│   ├── metrics.py           # Quality scoring
│   └── reporter.py          # Report generation + trends
├── input/
│   ├── pdf/                 # PDF test files
│   ├── pptx/                # PPTX test files
│   ├── docx/                # DOCX test files
│   ├── txt/                 # Text test files
│   └── images/              # Image files (scanned docs, photos)
├── expected/                # Expected .md outputs for validation
│   └── *.md
├── output/
│   ├── reports/             # Generated markdown + JSON run reports
│   └── debug/               # Debug logs
├── corrections/             # User correction datasets (auto-created)
│   └── *.json
└── quality_reports/         # Historical metrics for trend tracking
    └── *.json
```

## Workflow

```
1. PLACE: Drop any file into input/ (any subdirectory)
       │
2. RUN:  python process_all.py
       │
       ├── text extraction ──→ SmartPipeline (PDF/PPTX/DOCX)
       ├── OR OCR ───────────→ ScannedDocHandler (scanned PDFs, images)
       ├── image extraction ─→ ImageExtractorV2 → inline in markdown
       │
3. REVIEW: Quality grade printed (A/B/C/D)
       │
       ├── Score ≥ 0.9 ──────→ Done — output saved
       ├── Score < 0.9 ──────→ process_all.py --correct opens correction tool
       │
4. FIX (if needed): Interactive CLI
       │
       ├── promote/demote headings
       ├── mark lists, fix numbering
       ├── ignore/include images
       └── fix OCR transcription
              │
5. SAVE: Corrections → corrections/*.json
              │
6. IMPROVE: analyze_corrections.py detects patterns
            └── Suggests pipeline parameter tweaks
```

### Example Session

```bash
$ python process_all.py ~/Downloads/exam_scan.pdf

============================================================
  Processing: exam_scan.pdf
  Format: .PDF
============================================================

  Results:
  Processing path:     scanned_ocr
  Time:                3.42s
  Lines:               187
  Headings:            12
  List items:          8
  Images extracted:    3
  Decorative filtered: 1

  Score                Value      Grade
  ────────────────────────────────────────
  Overall              0.7234     C
  Structural validity  0.65
  Consistency          0.80

  Output: output/reports/OUTPUT_exam_scan.md

  Score 0.72 is below threshold. Open correction tool? [Y/n]: y

  Opening correction tool...
>> fix-ocr 45 "The answer is 4"
>> promote 12
>> mark-list 34
>> save
```

## Format Support

| Input Type | Format | Text Extraction | Image Extraction | Handles |
|-----------|--------|----------------|-----------------|---------|
| Native PDF | `.pdf` | Font-aware (pdfplumber) | Embedded images (PyMuPDF) + contour detection (OpenCV) | Typed docs with selectable text |
| Scanned PDF | `.pdf` | OCR (Tesseract) | Same as above | Phone photos of books/exams |
| PowerPoint | `.pptx` | Shape-level (python-pptx) | Pictures, Charts, SmartArt shapes | Lectures, slides |
| Word | `.docx` | Style-based (python-docx) | Inline images | Handouts, reports |
| Text | `.txt`, `.md` | Direct read | — | Plain text notes |
| Images | `.png`, `.jpg` | OCR (Tesseract) | Source image + sub-figure detection | Scanned pages, photos |

## Quality Metrics

| Metric | Range | Description |
|--------|-------|-------------|
| `overall_score` | 0-1 | Weighted combination of all sub-metrics |
| `structural_validity` | 0-1 | Heading hierarchy valid? Single H1? No orphan subs? |
| `content_preservation` | 0-1 | Body text retained vs expected output |
| `consistency_score` | 0-1 | Consistent heading/list style across the document |
| `image_recall` | 0-1 | % of expected images successfully extracted |
| `image_noise` | 0-1 | Decorative/logo images incorrectly included |
| `image_placement` | 0-1 | Images positioned near their related text |
| `ocr_confidence` | 0-1 | Tesseract confidence for scanned documents |

Grade: **A** ≥ 0.90 | **B** ≥ 0.75 | **C** ≥ 0.50 | **D** < 0.50

## Correction CLI

```bash
# Interactive correction
python correction_tool.py output/reports/OUTPUT_lecture.md

# Compare against expected/correct output
python correction_tool.py output/reports/OUTPUT_lecture.md --expected expected/lecture.md

# Analyze all accumulated corrections
python correction_tool.py --analyze
```

### Commands

| Command | Description |
|---------|-------------|
| `promote N` | Promote heading (H3→H2, H2→H1) |
| `demote N` | Demote heading (H2→H3) |
| `mark-body N` | Change heading/list to body text |
| `mark-heading N <level>` | Change line to specific heading (1-6) |
| `mark-list N` | Change body to bullet list item |
| `mark-olist N` | Change to ordered list item |
| `fix-numbering` | Normalize all ordered list numbering |
| `fix-bullets` | Normalize all list markers to `- ` |
| `ignore-image <path>` | Mark image as decorative (adds to filter) |
| `include-image <path>` | Mark image as important (overrides filter) |
| `move-image <path> after "text"` | Reposition image after an anchor text |
| `caption-image <path> "text"` | Set image alt text |
| `fix-ocr N "correction"` | Correct OCR transcription at line N |
| `diff` | Show side-by-side diff vs expected |
| `line N` | Show content of line N |
| `save` | Save all corrections to `corrections/` |
| `exit / q` | Quit without saving |

## Self-Improvement Engine

```bash
# Analyze all accumulated corrections
python analyze_corrections.py

# Show suggested pipeline parameter changes
python analyze_corrections.py --suggest-tweaks
```

The analyzer scans `corrections/*.json` and identifies:
- **Most common correction types** — heading errors? list errors? OCR errors?
- **Patterns by source format** — PDF vs PPTX vs scanned
- **Suggested parameter tweaks** — e.g., "raise H3 threshold from 16pt to 17pt" with confidence scores

## Pipeline Architecture

```
UnifiedContentProcessor (app/processing/unified_processor.py)
  │
  ├── TXT/MD ──────────→ Direct text read
  ├── Native PDF ──────→ SmartPipeline + ImageExtractorV2
  ├── Scanned PDF ─────→ pdf2image → ScannedDocHandler + ImageExtractorV2
  ├── PPTX ────────────→ SmartPipeline + ImageExtractorV2
  ├── DOCX ────────────→ SmartPipeline + ImageExtractorV2
  └── Images ──────────→ ScannedDocHandler + ImageExtractorV2
                            │
                            ▼
                     ContentBundle
               { markdown, images[], image_map[] }
                            │
                    ┌───────┴───────┐
                    │               │
              process_resource  process_exercise
```

### Key Source Files

| File | Role |
|------|------|
| `app/processing/unified_processor.py` | Single entry point for all formats |
| `app/processing/smart_pipeline.py` | Text extraction engine (PDF/PPTX/DOCX) |
| `app/processing/image_extractor_v2.py` | Multi-format image extraction + classifier |
| `app/processing/image_text_mapper.py` | Places images inline near their corresponding text |
| `app/processing/image_preprocessor.py` | Deskew, enhance, denoise for scanned docs |
| `app/processing/scanned_doc_handler.py` | Scanned PDF detection + Tesseract OCR |
| `app/processing/note_processor.py` | Resource processing task |
| `app/processing/exercise_processor.py` | Exercise processing task |

## Adding Test Cases

1. **Drop** your input file in `input/{format}/`
2. **Run** `python process_all.py`
3. **Review** the score and output in `output/reports/`
4. **Fix** with `--correct` if score is low — corrections are saved automatically
5. **Iterate** — each correction feeds the self-improvement engine

To add expected output for comparison:
1. Place a `.md` file with the expected content in `expected/{filename}.md`
2. Run `python run_test.py --expected-dir expected/`
3. The diff engine will report structural differences, missing headings, etc.

## Automation

```bash
# Full benchmark suite
./scripts/run_benchmark.sh

# Pre-commit hook (auto-tests when pipeline code changes)
ln -sf ../../.githooks/pre-commit .git/hooks/pre-commit
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| No images extracted from PPTX | Check if images are Picture shapes (not SmartArt/Charts). SmartArt needs rendering |
| Scanned PDF not detected | Run `python -c "from app.processing.scanned_doc_handler import ScannedDocHandler; print(ScannedDocHandler().is_scanned_pdf('path.pdf'))"` |
| Correction tool not opening | `process_all.py --correct` only opens for files scoring < 0.9. Use `--interactive` to force per-file prompts |
| All headings scored as H1 | Run `correction_tool.py` and use `demote N` on each. Save corrections — analyzer will suggest threshold tweaks |

## Dependencies

All processing is **100% local** — no external API required.

```
Python:    pdfplumber, python-pptx, python-docx, pytesseract, pdf2image, opencv-python, Pillow
System:    tesseract-ocr, poppler (for pdf2image)
Optional:  ollama (for AI polish pass)
```
