import dspy
from files.few_shot_demos import demos
from config.prompts_dspy import get_comparison_prompt


def init_dspy():
    lm = dspy.LM(
        'ollama_chat/mistral',
        api_base='http://127.0.0.1:11434',
        api_key='',
        drop_params=True,
        cache=False,
        temperature=0.5
    )
    dspy.configure(lm=lm)

def get_compare_module(num_thoughts=1):
    return CompareStandardsModule(CompareStandards, num_thoughts)

class CompareStandards(dspy.Signature):
    question = dspy.InputField()
    answer = dspy.OutputField(desc="Optimized comparison answer of the two standards.") # Translated from "Optimierte Vergleichsantwort der beiden Standards."

examples = demos

class CompareStandardsModule(dspy.Module):
    def __init__(self, signature, num_thoughts=1):
        super().__init__()
        self.num_thoughts = num_thoughts
        self.generate_thoughts = dspy.ChainOfThought(signature, demos=examples)
        self.compare_thoughts = dspy.MultiChainComparison(signature, M=num_thoughts)

    def forward(self, question):
        thoughts = [
            self.generate_thoughts(question=question).completions[0]
            for _ in range(self.num_thoughts)
        ]
        return self.compare_thoughts(question=question, completions=thoughts)

def run_comparison(standard_a, standard_b):
    init_dspy()

    prompt = get_comparison_prompt(standard_a, standard_b)

    module = get_compare_module()
    result = module(question=prompt)
    raw = getattr(result, "answer", str(result)).strip()

    return raw or "No response from model."