import httpx
import asyncio

def PromptMistral(band: float, question: str, essay: str) -> str: 
    PROMPT = """
    Overall Band Score: {}

    In this task, you are required to evaluate the following essay based on the official IELTS scoring criteria. 
    Please provide detailed feedback for each of the four criteria, no need to give score for each part, keeping in mind that the essay received the band score above. 

    ## Task Achievement:
    - Evaluate how well the candidate has addressed the given task.
    - Assess the clarity and coherence of the response in presenting ideas.
    - Identify if the candidate has fully covered all parts of the task and supported arguments appropriately.

    ## Coherence and Cohesion:
    - Assess the overall organization and structure of the essay.
    - Evaluate the use of linking devices to connect ideas and paragraphs.
    - Identify if there is a logical flow of information.

    ## Lexical Resource (Vocabulary):
    - Examine the range and accuracy of vocabulary used in the essay.
    - Point out specific mistakes in vocabulary, such as inaccuracies or overuse of certain words and Suggest modified versions or alternatives for the identified mistakes. [list of mistakes and rectify]
    - Assess the appropriateness of vocabulary for the given context.

    ## Grammatical Range and Accuracy:
    - Evaluate the variety and complexity of sentence structures.
    - Point out specific grammatical errors, such as incorrect verb forms or sentence construction and Suggest modified versions or corrections for the identified mistakes. [list of mistakes and rectify]
    - Examine the use of punctuation and sentence formation.

    ## Feedback and Additional Comments:
    - Provide constructive feedback highlighting specific strengths and areas for improvement.
    - Suggest strategies for enhancement in weaker areas.

    ## Prompt:
    {}

    ## Essay:
    {}

    ## Evaluation:
    {}"""

    return PROMPT.format(band, question, essay, "")

def test_local_model_httpx(model_name: str, band: float, question: str, essay: str):
    url = "http://localhost:11434/api/generate"
    prompt = PromptMistral(band, question, essay)

    payload = {
        "model": model_name,
        "prompt": prompt,
        "stream": False
    }

    with httpx.Client(timeout=300.0) as client:
        resp = client.post(url, json=payload)
        resp.raise_for_status()
        result = resp.json()

    print("\n===== MODEL RESPONSE =====\n")
    print(result["response"])
    return result["response"]

if __name__ == "__main__":
    test_local_model_httpx(
        model_name="mistral-gguf-local",
        band=6.0,
        question="In most countries, animal and plant species are declining rapidly. What are the causes and solutions?",
        essay="The species of animals and plants are rapidly decreasing due to many factors..."
    )