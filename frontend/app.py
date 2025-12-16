import streamlit as st
import requests
from typing import Optional, Dict, Any

# ===========================
# Constants and Configuration
# ===========================
BACKEND_URL = "http://localhost:8000"

CRITERIA_MAPPING = {
    "Task Achievement": 
    {
        "score_key": "Task Achievement",
        "feedback_key": "task_achievement",
        "constructive_key": "task_response",
    },
    "Coherence and Cohesion": 
    {
        "score_key": "Coherence and Cohesion",
        "feedback_key": "coherence_and_cohesion",
        "constructive_key": "coherence_and_cohesion",
    },
    "Lexical Resource": 
    {
        "score_key": "Lexical Resource",
        "feedback_key": "lexical_resource",
        "constructive_key": "lexical_resource",
    },
    "Grammatical Range and Accuracy": 
    {
        "score_key": "Grammatical Range and Accuracy",
        "feedback_key": "grammatical_range_and_accuracy",
        "constructive_key": "grammatical_range_and_accuracy",
    },
}

# Display labels for backend keys
CRITERIA_DISPLAY_NAMES = {
    "task_response": "Task Achievement",
    "coherence_and_cohesion": "Coherence and Cohesion",
    "lexical_resource": "Lexical Resource",
    "grammatical_range_and_accuracy": "Grammatical Range and Accuracy",
}


# ===========================
# CSS Styling
# ===========================
CUSTOM_CSS = """
<style>
    .score-card {
        background: #ffffff;
        padding: 20px;
        border-radius: 12px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.05);
        text-align: center;
    }
    .overall-score {
        background: #16a34a;
        color: white;
        font-size: 36px; 
        font-weight: bold;
        border-radius: 12px;
        padding: 30px 0;
    }
    .criteria-box {
        background: #f9fafb;
        padding: 15px;
        border-radius: 10px;
        text-align: center;
        font-weight: 600;
        border-top: 4px solid #3b82f6;
    }
    .feedback-box {
        padding: 16px;
        border-radius: 12px;
        font-size: 14px;
        line-height: 1.6;
    }
    .strengths {
        background: #ecfdf5;
        border-left: 6px solid #22c55e;
    }
    .evaluation {
        background: #eff6ff;
        border-left: 6px solid #3b82f6;
    }
    .improvement {
        background: #fffbeb;
        border-left: 6px solid #f59e0b;
    }
    .input-container {
        background: #f8f9fa;
        padding: 20px;
        border-radius: 10px;
        margin-bottom: 20px;
    }
    
    /* Grammar Correction Styles */
    .grammar-container {
        background: #ffffff;
        padding: 25px;
        border-radius: 12px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.08);
        line-height: 1.8;
        font-size: 16px;
    }
    
    .error-block {
        background-color: #fee2e2;
        border-bottom: 2px solid #dc2626;
        padding: 2px 4px;
        border-radius: 3px;
        cursor: pointer;
        position: relative;
        transition: all 0.2s ease;
    }
    
    .error-block:hover {
        background-color: #fecaca;
        border-bottom: 2px solid #991b1b;
    }
    
    .suggestion {
        background-color: #d1fae5;
        border-bottom: 2px solid #10b981;
        padding: 2px 4px;
        border-radius: 3px;
        font-weight: 500;
    }
    
    .word {
        cursor: pointer;
        padding: 1px 2px;
    }
    
    .word:hover {
        background-color: #f3f4f6;
        border-radius: 2px;
    }
    
    /* Tooltip for suggestions */
    .tooltip {
        visibility: hidden;
        background-color: #1f2937;
        color: #fff;
        text-align: center;
        border-radius: 6px;
        padding: 8px 12px;
        position: absolute;
        z-index: 1000;
        bottom: 125%;
        left: 50%;
        transform: translateX(-50%);
        white-space: nowrap;
        font-size: 14px;
        opacity: 0;
        transition: opacity 0.3s;
    }
    
    .tooltip::after {
        content: "";
        position: absolute;
        top: 100%;
        left: 50%;
        margin-left: -5px;
        border-width: 5px;
        border-style: solid;
        border-color: #1f2937 transparent transparent transparent;
    }
    
    .error-block:hover .tooltip {
        visibility: visible;
        opacity: 1;
    }
</style>

<script>
    function showSuggestion(element) {
        const suggestion = element.getAttribute('data-suggestion');
        if (suggestion && suggestion.trim()) {
            // Create or update tooltip
            let tooltip = element.querySelector('.tooltip');
            if (!tooltip) {
                tooltip = document.createElement('span');
                tooltip.className = 'tooltip';
                element.appendChild(tooltip);
            }
            tooltip.textContent = '✓ Suggestion: ' + suggestion;
            
            // Optional: Copy suggestion to clipboard
            navigator.clipboard.writeText(suggestion).then(() => {
                console.log('Suggestion copied to clipboard');
            }).catch(err => {
                console.error('Failed to copy suggestion:', err);
            });
        }
    }
    
    function scrollToWord(index) {
        const element = document.getElementById('suggestion-word-' + index);
        if (element) {
            element.scrollIntoView({ behavior: 'smooth', block: 'center' });
            element.style.backgroundColor = '#fef3c7';
            setTimeout(() => {
                element.style.backgroundColor = '';
            }, 2000);
        }
    }
</script>
"""

# ===========================
# UI Components
# ===========================
def render_overall_score(evaluation: Dict[str, Any]) -> None:
    """Render the overall IELTS score."""
    overall_criteria_scores = evaluation.get("overall_criteria_scores")

    # Derive scores if the backend returns the new format without overall_criteria_scores
    if not overall_criteria_scores:
        constructive = evaluation.get("constructive_feedback", {}).get("criteria", {})
        criteria_scores = {}
        for key, detail in constructive.items():
            score_val = detail.get("score")
            if score_val is not None:
                criteria_scores[key] = score_val
        overall_criteria_scores = {
            "overall_score": evaluation.get("overall_score"),
            "criteria_scores": criteria_scores
        }

    overall_score = overall_criteria_scores.get("overall_score")
    criteria_scores = overall_criteria_scores.get("criteria_scores")

    if not criteria_scores:
        st.warning("No criteria scores available.")
        return

    st.markdown("## 📊 Your IELTS Score")
    
    _, col, _ = st.columns([1, 1, 1])
    with col:
        st.markdown(
            f"""
            <div class="score-card overall-score">
                OVERALL BAND<br>{overall_score if overall_score is not None else '-'}
            </div>
            """,
            unsafe_allow_html=True,
        )
    
    st.markdown("---")
    st.markdown("### Criteria Breakdown")
    cols = st.columns(4)
    for col, (backend_key, score) in zip(cols, criteria_scores.items()):
        display_name = CRITERIA_DISPLAY_NAMES.get(backend_key, backend_key)
        col.markdown(
            f"""
            <div class="criteria-box">
                <b>{display_name}</b><br><br>
                <span style="font-size:28px; font-weight: bold; color: #3b82f6;">{score}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_feedback_box(title: str, items: list, css_class: str) -> None:
    """Render a single feedback box."""
    if not items:
        return
    
    content = "<br>• ".join(items)
    st.markdown(
        f"""
        <div class="feedback-box {css_class}">
            <b>{title}</b><br><br>
            • {content}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_criterion(
    title: str,
    score_criteria: Dict[str, Any],
    feedback: Dict[str, Any],
    criteria_config: Dict[str, str]
) -> None:
    """Render a single criterion with score, evaluation, and feedback."""
    st.markdown(f"### {title}")
    
    # Resolve scores supporting both old and new payload shapes
    overall_criteria_scores = score_criteria.get("overall_criteria_scores")
    if not overall_criteria_scores:
        constructive = score_criteria.get("constructive_feedback", {}).get("criteria", {})
        criteria_scores = {k: v.get("score") for k, v in constructive.items() if v.get("score") is not None}
        overall_criteria_scores = {
            "overall_score": score_criteria.get("overall_score"),
            "criteria_scores": criteria_scores
        }

    score = overall_criteria_scores["criteria_scores"][criteria_config["constructive_key"]]
    
    # Score display with progress bar
    col1, col2 = st.columns([1, 3])
    with col1:
        st.metric(label="Score", value=f"{score}")
    with col2:
        st.progress(min(int(score * 10), 100) / 100)
    
    st.markdown("---")
    
    # Extract feedback components
    try:
        strengths = feedback["constructive_feedback"]["criteria"][
            criteria_config["constructive_key"]
        ].get("strengths", [])
        
        # evaluation_feedback may be keyed by display names in new payload
        evaluation_block = feedback.get("evaluation_feedback", {})
        eval_key = criteria_config["feedback_key"]
        display_key = CRITERIA_DISPLAY_NAMES.get(criteria_config["constructive_key"], eval_key)
        evaluation_entry = evaluation_block.get(eval_key) or evaluation_block.get(display_key) or {}
        evaluation = evaluation_entry.get("feedback", "")
        
        improvements = feedback["constructive_feedback"]["criteria"][
            criteria_config["constructive_key"]
        ].get("areas_for_improvement", [])
    except (KeyError, TypeError):
        st.warning(f"Unable to parse feedback for {title}")
        return
    
    # Display feedback in columns
    c1, c2, c3 = st.columns(3)
    
    with c1:
        render_feedback_box("✅ Strengths", strengths, "strengths")
    
    with c2:
        render_feedback_box("📝 Evaluation", [evaluation] if evaluation else [], "evaluation")
    
    with c3:
        render_feedback_box("⚠️ Areas for Improvement", improvements, "improvement")


# ===========================
# API Functions
# ===========================
def fetch_essay_evaluation(question: str, answer: str) -> Optional[Dict[str, Any]]:
    """Fetch essay evaluation from backend."""
    if not question.strip() or not answer.strip():
        st.warning("Please enter both question and essay before evaluation.")
        return None
    
    try:
        payload = {"question": question, "answer": answer}
        response = requests.post(
            f"{BACKEND_URL}/evaluate_essay",
            json=payload,
            timeout=600
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.ConnectionError:
        st.error("❌ Unable to connect to backend. Is the server running?")
    except requests.exceptions.Timeout:
        st.error("❌ Request timeout. Backend took too long to respond.")
    except requests.exceptions.HTTPError as e:
        st.error(f"❌ Backend error: {e}")
    except Exception as e:
        st.error(f"❌ Error: {str(e)}")
    return None


def fetch_grammar_correction(answer: str) -> Optional[Dict[str, Any]]:
    """Fetch grammar corrections from backend."""
    if not answer.strip():
        st.warning("Please enter an essay before grammar correction.")
        return None
    
    try:
        # Backend expects 'answer' as a query parameter, not JSON body
        response = requests.post(
            f"{BACKEND_URL}/grammar_correction",
            params={"answer": answer},
            timeout=300
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.ConnectionError:
        st.error("❌ Unable to connect to backend. Is the server running?")
    except requests.exceptions.Timeout:
        st.error("❌ Request timeout. Backend took too long to respond.")
    except requests.exceptions.HTTPError as e:
        st.error(f"❌ Backend error: {e}")
    except Exception as e:
        st.error(f"❌ Error: {str(e)}")
    return None


def fetch_combined_evaluation(question: str, answer: str) -> Optional[Dict[str, Any]]:
    """Fetch combined evaluation and grammar correction from backend."""
    if not question.strip() or not answer.strip():
        st.warning("Please enter both question and essay before evaluation.")
        return None
    
    try:
        payload = {"question": question, "answer": answer}
        response = requests.post(
            f"{BACKEND_URL}/essay_process",
            json=payload,
            timeout=900
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.ConnectionError:
        st.error("❌ Unable to connect to backend. Is the server running?")
    except requests.exceptions.Timeout:
        st.error("❌ Request timeout. Backend took too long to respond.")
    except requests.exceptions.HTTPError as e:
        st.error(f"❌ Backend error: {e}")
    except Exception as e:
        st.error(f"❌ Error: {str(e)}")
    return None


# ===========================
# Page Configuration
# ===========================
st.set_page_config(
    page_title="IELTS Writing Task 2 Evaluation",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# ===========================
# Main App
# ===========================
st.title("🎯 IELTS Writing Task 2 Evaluation & Grammar Correction")
st.markdown("*Get detailed feedback on your IELTS Writing Task 2 essays*")

# Sidebar
st.sidebar.title("📋 Navigation")
page = st.sidebar.radio(
    "Select an option:",
    ["Essay Evaluation", "Grammar Correction", "Combined Evaluation & Correction"]
)

st.sidebar.markdown("---")
st.sidebar.markdown("### ℹ️ About")
st.sidebar.info(
    "This tool provides:\n\n"
    "• **Essay Evaluation**: Detailed feedback on IELTS criteria.\n\n"
    "• **Grammar Correction**: Annotated essay with corrections.\n\n"
    "• **Combined**: Both evaluation and corrections together."
    )
st.sidebar.markdown("---")
# Input Section
st.markdown("## 📝 Input Your Essay")
question = st.text_area(
    "Enter the Essay Question:",
    height=100,
    placeholder="Write your essay question here...",
    key="question_input"
)
answer = st.text_area(
    "Enter your Essay Answer:",
    height=300,
    placeholder="Write your essay here...",
    key="essay_input"
)

st.markdown("---")

# Initialize session state
if 'result_data' not in st.session_state:
    st.session_state.result_data = None

# Page logic
if page == "Essay Evaluation":
    st.markdown("### 📊 Essay Evaluation")
    st.markdown("Get comprehensive feedback based on IELTS criteria.")
    
    if st.button("🔍 Evaluate Essay", use_container_width=True):
        with st.spinner("⏳ Evaluating your essay..."):
            st.session_state.result_data = fetch_essay_evaluation(question, answer)
    
    if st.session_state.result_data:
        render_overall_score(st.session_state.result_data)
        
        st.markdown("---")
        
        for title, cfg in CRITERIA_MAPPING.items():
            render_criterion(title, st.session_state.result_data, st.session_state.result_data["detailed_feedback"], cfg)
            st.markdown("---")


elif page == "Grammar Correction":
    st.markdown("### ✏️ Grammar Correction")
    st.markdown("Get an annotated version of your essay with grammar corrections.")
    
    st.markdown("---")
    
    if st.button("🔧 Get Grammar Corrections", use_container_width=True):
        with st.spinner("⏳ Analyzing grammar..."):
            st.session_state.result_data = fetch_grammar_correction(answer)
    
    if st.session_state.result_data:
        st.markdown("### ✅ Grammar Correction Results")
        
        # Create tabs for different views
        tab1, tab2, tab3 = st.tabs(["📊 Errors & Fixes", "✅ Fixed Text", "📋 Plain Text"])
        
        with tab1:
            st.markdown("**View showing original errors (red) with corrections (green)**")
            with_errors = st.session_state.result_data.get("with_errors", "")
            if with_errors:
                st.markdown(
                    f"<div class='grammar-container'>{with_errors}</div>",
                    unsafe_allow_html=True
                )
            else:
                st.info("No corrections needed.")
        
        with tab2:
            st.markdown("**Corrected essay with green highlight**")
            fixed_only = st.session_state.result_data.get("fixed_only", "")
            if fixed_only:
                st.markdown(
                    f"<div class='grammar-container'>{fixed_only}</div>",
                    unsafe_allow_html=True
                )
            else:
                st.info("No corrections available.")
        
        with tab3:
            st.markdown("**Plain corrected text (no styling)**")
            corrected_text = st.session_state.result_data.get("corrected_text", "")
            if corrected_text:
                st.text_area(
                    "Corrected Text:",
                    value=corrected_text,
                    height=300,
                    disabled=True,
                    key="corrected_text_area"
                )
                # Copy button
                if st.button("📋 Copy to Clipboard", key="copy_button"):
                    st.success("✅ Copied! (Use browser's copy function)")
            else:
                st.info("No corrections available.")


elif page == "Combined Evaluation & Correction":
    st.markdown("### 🚀 Combined Evaluation & Correction")
    st.markdown("Get both evaluation and grammar corrections in one go.")
    
    if st.button("🎯 Evaluate and Correct Essay", use_container_width=True):
        with st.spinner("⏳ Processing your essay..."):
            st.session_state.result_data = fetch_combined_evaluation(question, answer)
    
    if st.session_state.result_data:
        # Overall score
        render_overall_score(st.session_state.result_data)
        
        st.markdown("---")
        
        for title, cfg in CRITERIA_MAPPING.items():
            render_criterion(title, st.session_state.result_data, st.session_state.result_data["detailed_feedback"], cfg)
            st.markdown("---")
        
        # Grammar corrections
        st.markdown("## ✏️ Grammar Corrections")
        
        # Create tabs for different views
        tab1, tab2, tab3 = st.tabs(["📊 Errors & Fixes", "✅ Fixed Text", "📋 Plain Text"])
        
        with tab1:
            st.markdown("**View showing original errors (red) with corrections (green)**")
            with_errors = st.session_state.result_data.get("with_errors", "")
            if with_errors:
                st.markdown(
                    f"<div class='grammar-container'>{with_errors}</div>",
                    unsafe_allow_html=True
                )
            else:
                st.info("No corrections needed.")
        
        with tab2:
            st.markdown("**Corrected essay with green highlight**")
            fixed_only = st.session_state.result_data.get("fixed_only", "")
            if fixed_only:
                st.markdown(
                    f"<div class='grammar-container'>{fixed_only}</div>",
                    unsafe_allow_html=True
                )
            else:
                st.info("No corrections available.")
        
        with tab3:
            st.markdown("**Plain corrected text (no styling)**")
            corrected_text = st.session_state.result_data.get("corrected_text", "")
            if corrected_text:
                st.text_area(
                    "Corrected Text:",
                    value=corrected_text,
                    height=300,
                    disabled=True,
                    key="combined_corrected_text"
                )
            else:
                st.info("No corrections available.")

# Footer
st.markdown("---")
st.markdown(
    "**Note**: Backend server must be running at `http://localhost:8000` for this app to work. "
    "For issues, check the backend logs."
)



