import streamlit as st
import asyncio


from backend.grammar import get_annotated_fixed_essay
from backend.bert_setup import get_overall_score
from backend.mistral_model import get_feedback


st.set_page_config(
    page_title="AI-powered IELTS Writing Task 2 Evaluator",
    page_icon="📝"
    )
st.title("AI-powered IELTS Writing Task 2 Evaluator 📝"),
st.markdown("""
This application evaluates IELTS Writing Task 2 essays using advanced AI models.
- **BERT Model**: Used for assessing the overall score of the essay based on content relevance and coherence.
- **Mistral Model**: Provides detailed feedback on various aspects of writing, including grammar, vocabulary, and task response.
- **Grammar Correction**: Utilizes a T5-based model to identify and correct grammatical errors in the essay.""")
st.sidebar.header("Essay Evaluation")
st.sidebar.markdown("""
Enter your IELTS Writing Task 2 question and essay in the fields below, then click 'Evaluate' to receive feedback and an overall score.
""")
question = st.text_area("Enter the IELTS Writing Task 2 Question:", height=150)
answer = st.text_area("Enter your Essay Answer:", height=300)
async def evaluate_essay(question, answer):
    # Get overall score from BERT model
    overall_score = get_overall_score(question, answer)
    
    # Get detailed feedback from Mistral model
    detailed_feedback = await get_feedback("user_123", question, answer)
    
    # Get annotated grammar corrections
    annotated_essay = await get_annotated_fixed_essay(answer)
    
    return overall_score, detailed_feedback, annotated_essay


if st.button("Evaluate Essay"):
    if not question.strip() or not answer.strip():
        st.error("Please enter both the question and the essay answer.")
    else:
        with st.spinner("Evaluating your essay..."):
            overall_score, detailed_feedback, annotated_essay = asyncio.run(evaluate_essay(question, answer))
        
        st.subheader("Overall Score")
        st.write(f"Your essay received an overall score of: **{overall_score}**")
        
        st.subheader("Detailed Feedback")
        st.json(detailed_feedback)
        
        st.subheader("Grammar Corrections")
        st.markdown(annotated_essay, unsafe_allow_html=True)

