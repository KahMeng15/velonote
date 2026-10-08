import struct
import sys

def parse_ppt(filepath):
    with open(filepath, "rb") as f:
        data = f.read()

    i = 0
    texts = []
    
    # We can try to just scan for headers.
    # But scanning byte-by-byte might be slow or yield false positives.
    # A valid header is 8 bytes.
    # We can use a regex to find all instances of the recTypes.
    
    # Let's try to parse it properly if it's contiguous, but OLE streams are in sectors.
    # Actually, often the 'PowerPoint Document' stream is in contiguous sectors or we can just scan for text.
    
    # Let's do a naive scan for \xa8\x0f (4008) and \xa0\x0f (4000)
    # We need to make sure recLen is reasonable, e.g. < 100000.
    
    text_blocks = []
    pos = 0
    while pos < len(data) - 8:
        # Check for TextBytesAtom (4008) or TextCharsAtom (4000)
        rec_type = struct.unpack_from("<H", data, pos + 2)[0]
        if rec_type in (4000, 4008):
            rec_len = struct.unpack_from("<I", data, pos + 4)[0]
            if 0 < rec_len < 10000:
                try:
                    if rec_type == 4008:
                        text_bytes = data[pos+8:pos+8+rec_len]
                        text = text_bytes.decode('latin-1')
                        if len(text.strip()) > 0:
                            text_blocks.append(text)
                        pos += 8 + rec_len
                        continue
                    elif rec_type == 4000:
                        text_bytes = data[pos+8:pos+8+rec_len]
                        text = text_bytes.decode('utf-16le')
                        if len(text.strip()) > 0:
                            text_blocks.append(text)
                        pos += 8 + rec_len
                        continue
                except Exception as e:
                    pass
        pos += 1

    print(f"Found {len(text_blocks)} blocks")
    for i, b in enumerate(text_blocks[:20]):
        print(f"Block {i}: {repr(b)}")
        
parse_ppt('data/users/1/uploads/20261007_134049_Chapter 1_Computer System.ppt')
