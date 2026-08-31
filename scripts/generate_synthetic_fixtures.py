# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "fpdf2",
# ]
# ///

from fpdf import FPDF
import os

def generate_synthetic_tclog():
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Courier", size=10)
    
    # Write a synthetic Scripte TCLog that mimics the DEMO_TCLog parser expectations
    content = """
DEMO PRODUCTION - TCLog Day 031

SLATE   TAKE    TC IN       TC OUT      CAMERA ROLL   SOUND ROLL   NOTES
--------------------------------------------------------------------------------
117A/1  1       10:00:00:00 10:01:00:00 A120          SR031        False Start
117A/1  2       10:02:00:00 10:03:30:00 B039          SR031        Good take, nice dolly
27B/2   1       11:00:00:00 11:01:30:00 C005          SR031        Print
    """
    
    for line in content.split("\n"):
        pdf.cell(200, 5, txt=line, ln=1, align="L")
        
    out_dir = os.path.join(os.path.dirname(__file__), "..", "data", "examples")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "DEMO_TCLog_Synthetic.pdf")
    pdf.output(out_path)
    print(f"Generated {out_path}")

if __name__ == "__main__":
    generate_synthetic_tclog()
