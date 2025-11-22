def build_rag_prompt(query: str, contexts: list[str]) -> str:
    context_block = "\n\n".join([f"- {c}" for c in contexts])

    prompt = f"""You are an expert in international cybersecurity regulations.

You are given the following context snippets retrieved from cybersecurity standards:

{context_block}

Based on this information, answer the following question:

{query}

Only use the information provided above. If the information is insufficient, state that clearly.
Respond in clear, professional English."""

    return prompt



RAG_MAPPING_PROMPT_TEMPLATE = """
Compare the following two descriptions of cybersecurity controls.
Analyze the relationship between Control A (source) and Control B (target).
Classify the relationship into one of the following categories:
- EQUAL: Both controls essentially describe the same goal and scope.
- SUBSET: Control A is a more specific subset of Control B (B covers everything in A and more).
- SUPERSET: Control A is a broader superset of Control B (A covers everything in B and more).
- RELATED: The controls address related topics, but neither is a subset or superset of the other.
- UNRELATED: The controls are thematically largely or entirely unrelated.

Provide your answer in the following format:
Classification: [EQUAL|SUBSET|SUPERSET|RELATED|UNRELATED]
Explanation: [Your detailed reasoning for the classification, why they (do not) relate and how.]

Control A (source):
{source_prose}

Control B (target):
{target_prose}

Answer:
"""
