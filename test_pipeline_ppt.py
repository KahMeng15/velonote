import asyncio
from app.processing.unified_processor import UnifiedContentProcessor

def test():
    processor = UnifiedContentProcessor(use_polish=False)
    bundle = processor.extract('data/users/1/uploads/20261007_134049_Chapter 1_Computer System.ppt', resource_id="test_ppt")
    print("MARKDOWN OUTPUT:")
    print("----------------")
    print(bundle.markdown[:1500])
    print("----------------")
    print(f"Total lines: {len(bundle.markdown.split(chr(10)))}")
    print(f"Processing path: {bundle.processing_path}")
    print(f"Warnings: {bundle.warnings}")

if __name__ == "__main__":
    test()
