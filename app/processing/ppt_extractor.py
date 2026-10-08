import struct
import re

class PPTExtractor:
    """
    A pure Python extractor for legacy MS PowerPoint (.ppt) files.
    Parses OLE document binaries directly to extract TextBytesAtom and TextCharsAtom.
    """
    
    # Common master slide placeholder texts to ignore
    IGNORED_TEXTS = {
        "click to edit master title style",
        "click to edit master text styles",
        "second level",
        "third level",
        "fourth level",
        "fifth level",
        "click to edit master subtitle style",
        "click to add title",
        "click to add subtitle",
        "click to add text",
        "title text",
        "subtitle text",
        "title area for autorayouts",
        "object area for autorayouts",
        "subtitle area for autorayouts",
        "<date/time>",
        "<footer>",
        "<header>",
        "<#>"
    }

    @classmethod
    def extract_text(cls, filepath: str) -> str:
        """
        Extracts text from a .ppt file and returns it as a basic Markdown string.
        """
        try:
            with open(filepath, "rb") as f:
                data = f.read()
        except Exception as e:
            return f"Error reading PPT file: {e}"

        strings = []
        
        # TextBytesAtom (4008 -> \xA8\x0F)
        idx = 0
        while True:
            idx = data.find(b'\xA8\x0F', idx)
            if idx == -1: break
            
            if idx >= 2 and idx + 6 <= len(data):
                rec_len = struct.unpack_from("<I", data, idx + 2)[0]
                if 0 < rec_len < 100000 and idx + 6 + rec_len <= len(data):
                    text_data = data[idx+6 : idx+6+rec_len]
                    try:
                        text = text_data.decode("latin-1")
                        cls._process_extracted_string(idx, text, strings)
                    except Exception:
                        pass
            idx += 2

        # TextCharsAtom (4000 -> \xA0\x0F)
        idx = 0
        while True:
            idx = data.find(b'\xA0\x0F', idx)
            if idx == -1: break
            
            if idx >= 2 and idx + 6 <= len(data):
                rec_len = struct.unpack_from("<I", data, idx + 2)[0]
                if 0 < rec_len < 100000 and idx + 6 + rec_len <= len(data):
                    text_data = data[idx+6 : idx+6+rec_len]
                    try:
                        text = text_data.decode("utf-16le")
                        cls._process_extracted_string(idx, text, strings)
                    except Exception:
                        pass
            idx += 2

        # Sort based on appearance in binary (generally chronological)
        strings.sort(key=lambda x: x[0])
        
        markdown_lines = []
        seen = set()
        
        for _, text in strings:
            # Basic cleanup
            clean_text = text.strip()
            
            # Avoid consecutive duplicates
            if clean_text in seen:
                continue
                
            seen.add(clean_text)
            
            # Formatting as Markdown
            # We'll just output them as paragraphs, separated by double newline
            # PPT text often has internal \r or \n
            # Replace internal carriage returns with newlines if mixed
            clean_text = clean_text.replace('\r\n', '\n').replace('\r', '\n')
            
            # Clean up excessive spaces
            clean_text = re.sub(r' {2,}', ' ', clean_text)
            
            # Add to markdown lines
            if clean_text:
                markdown_lines.append(clean_text)
                
        return cls._format_markdown(markdown_lines)

    @classmethod
    def _format_markdown(cls, lines: list[str]) -> str:
        formatted = []
        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Check if line starts with a number or bullet
            is_list = bool(re.match(r'^([0-9]+\.?[0-9]*[\)\.]|[-•*])\s*', line))
                
            # Basic heuristic for headings:
            # Short length, mostly title case or uppercase, no trailing period.
            is_heading = False
            if not is_list and len(line) < 80 and '\n' not in line:
                if line.isupper() and len(line) > 3:
                    is_heading = True
                elif line.istitle() and not line.endswith(('.', ',', ';')):
                    is_heading = True
                elif len(line) < 60 and not line.endswith(('.', ',', ';', ':', '?')):
                    is_heading = True
                    
            if is_heading:
                formatted.append(f"## {line}")
            elif is_list:
                line = re.sub(r'\t+', ' ', line)
                if line.startswith('•'):
                    line = '- ' + line[1:].strip()
                formatted.append(line)
            else:
                # Multi-line text boxes usually represent bullet points in PPT
                internal_lines = line.split('\n')
                if len(internal_lines) > 1:
                    bulleted = []
                    for i, il in enumerate(internal_lines):
                        il = il.strip()
                        if not il: continue
                        if i == 0 and il.endswith(':'):
                            bulleted.append(il)
                        else:
                            if il.startswith('•') or il.startswith('-'):
                                bulleted.append(il)
                            else:
                                bulleted.append(f"- {il}")
                    formatted.append("\n".join(bulleted))
                else:
                    formatted.append(line)
                
        return "\n\n".join(formatted)

    @classmethod
    def _process_extracted_string(cls, idx: int, text: str, strings: list):
        clean_text = text.strip()
        if len(clean_text) < 2:
            return
            
        # Check against ignored template strings (case insensitive)
        lower_text = clean_text.lower()
        if any(ignored in lower_text for ignored in cls.IGNORED_TEXTS):
            return
            
        # Simple heuristical filtering for garbage binary that decoded validly
        if clean_text.count('\x00') > len(clean_text) * 0.1:
            return
            
        strings.append((idx, text))

# For quick test execution if run directly
if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        print(PPTExtractor.extract_text(sys.argv[1]))
