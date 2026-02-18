
import streamlit as st
import pandas as pd
import json


st.set_page_config(page_title="Demo", layout="wide")

st.markdown(
    """
    <style>
    .block-container {
        max-width: 1100px;
        padding-left: 2rem;
        padding-right: 2rem;
    }

    .word-pill {
        display: inline-block;
        padding: 0.45rem 0.6rem;
        border-radius: 10px;
        text-align: center;
        width: 100%;
        font-weight: 600;
        border: 1px solid #d1d5db;
        background: #f3f4f6;
    }
    .word-pill.selected {
        background: #2563EB;
        color: white;
        border: 1px solid #2563EB;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

@st.cache_data
def load_trials(path="data/trials.csv"):
    df = pd.read_csv(path)
    return df.to_dict(orient="records")

examples = load_trials()

PARAMS = ["breathiness", "creakiness", "nasality", "average_pitch", "average_range"]

def default_param():
    return {p: 0.0 for p in PARAMS}

def slider_key(ex_i, word_i, param):
    return f"ex{ex_i}_{word_i}_{param}"

# Session state init

if "example_index" not in st.session_state:
    st.session_state.example_index = 0

if "trial_state" not in st.session_state:
    st.session_state.trial_state = {}
    # {example_index: {"selected_index": int, "word_params": {word_index: {param: value, ...}, ...}}, ...}

if "status_message" not in st.session_state:
    st.session_state.status_message = "No changes applied"


def ensure_trial_state(ex_i):
    words = examples[ex_i]["transcript"].split()
    if ex_i not in st.session_state.trial_state:
        st.session_state.trial_state[ex_i] = {
            "selected_index": 0,
            "word_params": {i: default_param() for i in range(len(words))},
        }
    return words

def load_word_into_sliders(ex_i, word_i):
    wp = st.session_state.trial_state[ex_i]["word_params"][word_i]
    for p in PARAMS:
        st.session_state[slider_key(ex_i, word_i, p)] = float(wp[p])

def save_sliders_into_word(ex_i, word_i):
    wp = st.session_state.trial_state[ex_i]["word_params"][word_i]
    for p in PARAMS:
        wp[p] = float(st.session_state.get(slider_key(ex_i, word_i, p), 0.0))
    words = examples[ex_i]["transcript"].split()
    st.session_state.status_message = f"Edit in progress: '{words[word_i]}'"

def select_word(ex_i, word_i):
    st.session_state.trial_state[ex_i]["selected_index"] = word_i
    load_word_into_sliders(ex_i, word_i)
    words = examples[ex_i]["transcript"].split()
    st.session_state.status_message = f"Edit in progress: '{words[word_i]}'"

def reset_word(ex_i, word_i):
    st.session_state.trial_state[ex_i]["word_params"][word_i] = default_param()
    load_word_into_sliders(ex_i, word_i)
    words = examples[ex_i]["transcript"].split()
    st.session_state.status_message = f"Parameters reset for '{words[word_i]}'"

def reset_all(ex_i):
    words = examples[ex_i]["transcript"].split()
    st.session_state.trial_state[ex_i]["word_params"] = {i: default_param() for i in range(len(words))}
    st.session_state.trial_state[ex_i]["selected_index"] = 0
    load_word_into_sliders(ex_i, 0)
    st.session_state.status_message = "Parameters reset for all words."

def submit_all_changes(ex_i):
    st.session_state.status_message = f"Changes submitted successfully for example {ex_i + 1} (global)."
    write_request_json(ex_i)

def prev_example():
    st.session_state.example_index = max(0, st.session_state.example_index - 1)
    st.session_state.status_message = f"Moved to example {st.session_state.example_index + 1}"

def next_example():
    st.session_state.example_index = min(len(examples) - 1, st.session_state.example_index + 1)
    st.session_state.status_message = f"Moved to example {st.session_state.example_index + 1}"

def write_request_json(ex_i):
    trial = examples[ex_i]
    words = trial["transcript"].split()

    wp = st.session_state.trial_state[ex_i]["word_params"]

    wp_json = {str(i): {k: float(v) for k, v in wp[i].items()} for i in range(len(words))}

    req = {
        "audio_id": ex_i + 1,
        "original_path": trial["original"],
        "baseline_path": trial["baseline"],
        "transcript": trial["transcript"],
        "words": words,
        "word_params": wp_json,
    }

    req_path = f"requests/ex{ex_i+1}_request.json"
    with open(req_path, "w", encoding="utf-8") as f:
        json.dump(req, f, indent=2)

    return req_path


# Current example context
ex_i = st.session_state.example_index
transcript_words = ensure_trial_state(ex_i)

selected_idx = st.session_state.trial_state[ex_i]["selected_index"]
selected_idx = max(0, min(selected_idx, len(transcript_words) - 1))
st.session_state.trial_state[ex_i]["selected_index"] = selected_idx

if slider_key(ex_i, selected_idx, "breathiness") not in st.session_state:
    load_word_into_sliders(ex_i, selected_idx)


st.title(f"Audio {ex_i + 1} of {len(examples)}")

st.header("Original Audio:")
st.audio(examples[ex_i]["original"])
st.divider()

st.header("Baseline Audio:")
st.audio(examples[ex_i]["baseline"])

cols = st.columns(len(transcript_words))
for i, word in enumerate(transcript_words):
    with cols[i]:
        if selected_idx == i:
            st.markdown(f'<div class="word-pill selected">{word}</div>', unsafe_allow_html=True)
        else:
            st.button(
                word,
                key=f"word_ex{ex_i}_{i}",  
                on_click=select_word,
                args=(ex_i, i),
                use_container_width=True,
            )

st.write("")
st.write("")
st.write("")

st.slider(
    "Breathiness",
    0.0,
    2.0,
    step=0.1,
    key=slider_key(ex_i, selected_idx, "breathiness"),
    on_change=save_sliders_into_word,
    args=(ex_i, selected_idx),
)

st.slider(
    "Creakiness",
    0.0,
    2.0,
    step=0.1,
    key=slider_key(ex_i, selected_idx, "creakiness"),
    on_change=save_sliders_into_word,
    args=(ex_i, selected_idx),
)

st.slider(
    "Nasality",
    0.0,
    2.0,
    step=0.1,
    key=slider_key(ex_i, selected_idx, "nasality"),
    on_change=save_sliders_into_word,
    args=(ex_i, selected_idx),
)

st.slider(
    "Average Pitch",
    -2.0,
    2.0,
    step=0.1,
    key=slider_key(ex_i, selected_idx, "average_pitch"),
    on_change=save_sliders_into_word,
    args=(ex_i, selected_idx),
)

st.slider(
    "Average Range",
    -2.0,
    2.0,
    step=0.1,
    key=slider_key(ex_i, selected_idx, "average_range"),
    on_change=save_sliders_into_word,
    args=(ex_i, selected_idx),
)

st.write("")
st.write("")

c1, c2, c3 = st.columns(3)
with c1:
    st.button("Submit changes", on_click=submit_all_changes, args=(ex_i,), use_container_width=True)
with c2:
    st.button("Reset word", on_click=reset_word, args=(ex_i, selected_idx), use_container_width=True)
with c3:
    st.button("Reset all", on_click=reset_all, args=(ex_i,), use_container_width=True)

st.divider()

st.header("Modified Audio:")
st.audio(examples[ex_i]["modified"])
st.divider()

prev, nxt = st.columns(2)
with prev:
    st.button(
        "<< Previous",
        on_click=prev_example,
        use_container_width=True,
        disabled=(st.session_state.example_index == 0),
    )
with nxt:
    st.button(
        "Next >>",
        on_click=next_example,
        use_container_width=True,
        disabled=(st.session_state.example_index == len(examples) - 1),
    )

st.info(f"Status: {st.session_state.status_message}")

with st.expander("Word parameters (current example)"):
    wp = st.session_state.trial_state[ex_i]["word_params"]
    for i, w in enumerate(transcript_words):
        st.write(f"{i} ({w}): {wp[i]}")
