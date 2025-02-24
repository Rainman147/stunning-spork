#!/usr/bin/env python3
import fitz  # PyMuPDF
import re
import sys
import os
import logging
from datetime import datetime

# Add this near the top of the file, after the imports
def setup_logging():
    """Setup logging to file only"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = f'conversion_log_{timestamp}.txt'
    
    # Configure logging to file only
    logging.basicConfig(
        level=logging.INFO,
        format='%(message)s',
        handlers=[
            logging.FileHandler(log_file)
        ]
    )
    return log_file

def convert_value(value_str, unit="mm", precision=4):
    """Convert a metric value (mm or cm) to inches with the given precision."""
    try:
        value = float(value_str)
    except ValueError:
        logging.info(f"convert_value: Failed to convert {value_str}")
        return value_str
    factor = 25.4 if unit.lower() == "mm" else 2.54
    converted = value / factor
    logging.info(f"convert_value: {value_str} {unit} -> {converted:.{precision}f} in")
    return f"{converted:.{precision}f}"

def replacement_function(text):
    if "°" in text:
        logging.info(f"replacement_function: Skipping conversion due to degree symbol in '{text}'")
        return text
    if re.search(r'\d[xX]\d', text):
        logging.info(f"replacement_function: Skipping conversion due to GD&T callout in '{text}'")
        return text

    # Separate any tolerance part (assume tolerance follows a '+' or '-' after the base number)
    split_plus = text.split('+')
    split_minus = text.split('-')
    if len(split_plus) > 1:
        base_number = split_plus[0]
        tolerance = '+' + '+'.join(split_plus[1:])
    elif len(split_minus) > 1:
        base_number = split_minus[0]
        tolerance = '-' + '-'.join(split_minus[1:])
    else:
        base_number = text
        tolerance = ""
    
    # Determine precision from the base number
    parts = base_number.split('.')
    if len(parts) > 1:
        prec = len(parts[1])
    else:
        prec = 4  # default precision if no decimal found
    
    try:
        converted = convert_value(base_number, "mm", prec)
        result = converted + tolerance
        logging.info(f"replacement_function: Converted '{text}' to '{result}'")
        return result
    except ValueError:
        logging.info(f"replacement_function: ValueError for '{text}', returning original")
        return text

def group_numeric_spans(spans, gap_threshold=3.0):
    """
    Groups adjacent spans if they consist solely of numeric characters
    (digits, '.', '+', or '-') and are close together horizontally.
    Returns a list of groups; each group is a dict with:
      - "text": concatenated text
      - "bbox": union bounding box [x0, y0, x1, y1]
      - "font", "size", "color": taken from the first span in the group.
    """
    groups = []
    current = None

    def is_numeric_text(t):
        return bool(re.match(r'^[0-9\.\+\-]+$', t.strip()))

    for span in spans:
        txt = span.get("text", "").strip()
        if not txt:
            continue
        if is_numeric_text(txt):
            if current is not None:
                prev_bbox = current["bbox"]
                cur_bbox = span["bbox"]
                gap = cur_bbox[0] - prev_bbox[2]
                if gap < gap_threshold:
                    current["text"] += txt
                    # Expand the bounding box to include the current span
                    current["bbox"][2] = cur_bbox[2]
                    current["bbox"][3] = max(current["bbox"][3], cur_bbox[3])
                    continue
            current = {
                "text": txt,
                "bbox": list(span["bbox"]),
                "font": span["font"],
                "size": span["size"],
                "color": span.get("color", (0, 0, 0))
            }
            groups.append(current)
        else:
            current = None
    return groups

def process_pdf(input_file, output_file):
    log_file = setup_logging()
    logging.info(f"process_pdf: Opening PDF file: {input_file}")
    doc = fitz.open(input_file)
    logging.info(f"process_pdf: PDF opened. Total pages: {doc.page_count}")
    
    # Replace all print statements with logging.info
    # For example:
    # print(f"some message") becomes logging.info(f"some message")
    
    # Regex to match a complete numeric value (including optional tolerance)
    number_pattern = re.compile(r'^[+-]?\d*\.?\d+(?:[+-]\d*\.?\d+)?$', re.IGNORECASE)
    
    for page in doc:
        logging.info(f"process_pdf: Processing page {page.number + 1}")
        replacements = []
        page_dict = page.get_text("dict")
        for block in page_dict.get("blocks", []):
            if "lines" not in block:
                continue
            for line in block["lines"]:
                groups = group_numeric_spans(line["spans"])
                for group in groups:
                    group_text = group["text"]
                    logging.info(f"process_pdf: Grouped numeric text: '{group_text}' with bbox {group['bbox']}")
                    if number_pattern.match(group_text):
                        converted = replacement_function(group_text)
                        if converted != group_text:
                            logging.info(f"process_pdf: Replacing '{group_text}' with '{converted}'")
                            replacements.append((group["bbox"], converted, group["font"], group["size"], group["color"]))
        if replacements:
            logging.info("process_pdf: Applying redactions for replacements")
            for rep in replacements:
                rect = fitz.Rect(rep[0])
                page.add_redact_annot(rect, fill=(1, 1, 1))
            page.apply_redactions()
            logging.info("process_pdf: Reinserting converted text...")
            for rep in replacements:
                rect = fitz.Rect(rep[0])
                try:
                    page.insert_textbox(rect, rep[1],
                                        fontname=rep[2],
                                        fontsize=rep[3],
                                        color=rep[4],
                                        align=0,
                                        overlay=True)
                    logging.info(f"process_pdf: Inserted '{rep[1]}' at {rect}")
                except Exception as e:
                    logging.info(f"process_pdf: Font insertion failed with '{rep[2]}'; falling back to default. Error: {e}")
                    page.insert_textbox(rect, rep[1],
                                        fontname="helv",
                                        fontsize=rep[3],
                                        color=rep[4],
                                        align=0,
                                        overlay=True)
                    logging.info(f"process_pdf: Inserted '{rep[1]}' at {rect} with fallback font 'helv'")
    doc.save(output_file)
    logging.info(f"process_pdf: Conversion complete. Output saved as '{output_file}'.")
    
    try:
        os.startfile(output_file)
        logging.info("process_pdf: Opening converted PDF...")
    except Exception as e:
        logging.info(f"process_pdf: PDF saved but could not be opened automatically: {e}")

if __name__ == "__main__":
    input_file = sys.argv[1] if len(sys.argv) > 1 else "input.pdf"
    output_file = sys.argv[2] if len(sys.argv) > 2 else "output_converted.pdf"
    process_pdf(input_file, output_file)
