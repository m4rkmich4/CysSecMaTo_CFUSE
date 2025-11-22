# config/prompts_dspy.py

def get_comparison_prompt(standard_a: str, standard_b: str) -> str:
    return (
        f"Compare the cybersecurity standards '{standard_a}' and '{standard_b}' in detail, "
        f"focusing on the following categories:\n\n"
        "1. Origin (Country, Organization, Year, Versioning)\n"
        "2. Objective (What is the core purpose of the standard?)\n"
        "3. Scope of Application (Who uses it and where is it applicable?)\n"
        "4. Structure / Composition (Sections, principles, domains, or categories used)\n"
        "5. Unique Features and Distinctive Characteristics (Key differences and innovations)\n"
        "6. Certifiability and Practical Relevance (Is certification possible? Real-world adoption?)\n\n"
        "Respond **strictly in ENGLISH**, and use clean, consistent Markdown formatting:\n"
        "- Each category must start with a heading using '###'.\n"
        "- Use bullet points (•) for individual facts or descriptions.\n"
        "- Bold important terms and emphasize differences clearly.\n\n"
        "Be as detailed and specific as possible in each section. Avoid generalizations. "
        "Ensure that the response helps the reader directly compare both standards and understand their key similarities and differences."
    )
