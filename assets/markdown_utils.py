import re
from assets.styles import LILAC

def beautify_markdown(markdown_text: str) -> str:
    """
    Convert simplified Markdown into HTML for a QTextBrowser.
    Currently supports:
    - ### for headings
    - - or • for list items
    - **text** for bold formatting
    """
    html = ""
    in_list = False
    lines = markdown_text.split("\n")

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Headings
        if line.startswith("###"):
            if in_list:
                html += "</ul>"
                in_list = False
            html += f'<h3 style="color:{LILAC}; margin-top:20px;">{line[3:].strip()}</h3>'

        # List items
        elif line.startswith("-") or line.startswith("•"):
            if not in_list:
                html += "<ul>"
                in_list = True
            html += f'<li>{line[1:].strip()}</li>'

        # Normal paragraph with optional **bold**
        else:
            if in_list:
                html += "</ul>"
                in_list = False
            # **bold** → <b>bold</b>
            line = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", line)
            html += f"<p>{line}</p>"

    if in_list:
        html += "</ul>"

    return f"<html><body>{html}</body></html>"
