import struct
import sys

def parse_ppt_opt(filepath):
    with open(filepath, "rb") as f:
        data = f.read()

    text_blocks = []
    
    pos = 0
    while True:
        pos_4000 = data.find(b'\xa0\x0f', pos)
        pos_4008 = data.find(b'\xa8\x0f', pos)
        
        if pos_4000 == -1 and pos_4008 == -1:
            break
            
        if pos_4000 != -1 and (pos_4008 == -1 or pos_4000 < pos_4008):
            next_pos = pos_4000
            rec_type = 4000
        else:
            next_pos = pos_4008
            rec_type = 4008
            
        header_start = next_pos - 2
        if header_start >= 0 and header_start + 8 <= len(data):
            rec_len = struct.unpack_from("<I", data, header_start + 4)[0]
            if 0 < rec_len < 100000 and header_start + 8 + rec_len <= len(data):
                try:
                    if rec_type == 4008:
                        text_bytes = data[header_start+8:header_start+8+rec_len]
                        text = text_bytes.decode('latin-1')
                        if len(text.strip()) > 0:
                            text_blocks.append(text)
                        pos = header_start + 8 + rec_len
                        continue
                    elif rec_type == 4000:
                        text_bytes = data[header_start+8:header_start+8+rec_len]
                        text = text_bytes.decode('utf-16le')
                        if len(text.strip()) > 0:
                            text_blocks.append(text)
                        pos = header_start + 8 + rec_len
                        continue
                except Exception:
                    pass
        
        pos = next_pos + 2

    # Clean and filter
    cleaned_blocks = []
    seen = set()
    for b in text_blocks:
        b = b.replace('\r', '\n').strip()
        if not b:
            continue
        if "Click to edit Master" in b:
            continue
        if b == "*":
            continue
        
        # Avoid duplicate footers (like "SSK3207 Chapter 1")
        if b in seen and len(b) < 30 and "\n" not in b:
            continue
            
        seen.add(b)
        cleaned_blocks.append(b)

    for i, b in enumerate(cleaned_blocks):
        print(f"--- Block {i} ---")
        print(b)
        
parse_ppt_opt('data/users/1/uploads/20261007_134049_Chapter 1_Computer System.ppt')
