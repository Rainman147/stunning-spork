import fitz  # PyMuPDF
doc = fitz.open("input.pdf")
page = doc[0]
# Define a rectangle that is sure to be in a blank area
rect = fitz.Rect(50, 50, 300, 100)
# Insert text in red, larger font, centered
page.insert_textbox(rect, "TEST", fontname="helv", fontsize=20, color=(1, 0, 0), align=1, overlay=True)
doc.save("test_output.pdf")
