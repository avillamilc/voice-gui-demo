import sys
import streamlit as st
import pandas as pd
import json
import subprocess
from pathlib import Path

st.set_page_config(page_title="Demo", layout="centered")

st.markdown("""
<style>
section.main > div {
    max-width: 1100px;
    padding-left: 2rem;
    padding-right: 2rem;
    margin: 0 auto;
}
</style>
""", unsafe_allow_html=True)

@st.cache_data
def load_trials(path="data/trials.csv"):
    df = pd.read_csv(path)
    return df.to_dict(orient="records")

built_in_examples = load_trials()

PARAMS = ["breathiness", "creakiness", "nasality", "average_pitch", "average_range"]

def default_param():
    return {p: 0.0 for p in PARAMS}

def slider_key(ex_i, word_i, param):
    return f"ex{ex_i}_{word_i}_{param}"


# Session state initialization
if "example_index" not in st.session_state:
    st.session_state.example_index = 0

if "trial_state" not in st.session_state:
    st.session_state.trial_state = {}
    # {example_index: {"selected_words": [int,...], "word_params": {word_index: {param: value}}}}

if "status_message" not in st.session_state:
    st.session_state.status_message = "No changes applied"

if "generated_audio" not in st.session_state:
    st.session_state.generated_audio = {}
    # {ex_i: "generated/ex1_generated.wav"}

if "user_trials" not in st.session_state:
    st.session_state.user_trials = []  # list of dict trials, same schema as CSV

if "show_add_trial" not in st.session_state:
    st.session_state.show_add_trial = False

if "upload_nonce" not in st.session_state:
    st.session_state.upload_nonce = 0

Path("uploads").mkdir(exist_ok=True)
Path("requests").mkdir(exist_ok=True)
Path("generated").mkdir(exist_ok=True)

# Combine built-in + user uploaded trials
examples = built_in_examples + st.session_state.user_trials

def toggle_add_trial_ui():
    st.session_state.show_add_trial = not st.session_state.show_add_trial

def add_user_trial(baseline_file, original_file, transcript_text):
    # baseline is required, transcript required
    user_id = len(st.session_state.user_trials) + 1
    audio_id = f"user_{user_id}"

    baseline_path = f"uploads/{audio_id}_baseline.wav"
    with open(baseline_path, "wb") as f:
        f.write(baseline_file.getbuffer())

    original_path = ""
    if original_file is not None:
        original_path = f"uploads/{audio_id}_original.wav"
        with open(original_path, "wb") as f:
            f.write(original_file.getbuffer())

    new_trial = {
        "audio_id": audio_id,
        "original": original_path,  # may be ""
        "baseline": baseline_path,
        "transcript": transcript_text.strip(),
    }

    st.session_state.user_trials.append(new_trial)

    # jump to the new trial
    all_trials = built_in_examples + st.session_state.user_trials
    st.session_state.example_index = len(all_trials) - 1

    # hide form + reset widgets
    st.session_state.show_add_trial = False
    st.session_state.upload_nonce += 1

    st.session_state.status_message = f"Added new trial ({audio_id})."


def ensure_trial_state(ex_i):
    words = examples[ex_i]["transcript"].split()
    if ex_i not in st.session_state.trial_state:
        st.session_state.trial_state[ex_i] = {
            "selected_words": [0],
            "word_params": {i: default_param() for i in range(len(words))},
        }
    else:
        if "selected_words" not in st.session_state.trial_state[ex_i] or not st.session_state.trial_state[ex_i]["selected_words"]:
            st.session_state.trial_state[ex_i]["selected_words"] = [0]
    return words

def load_word_into_sliders(ex_i, word_i):
    wp = st.session_state.trial_state[ex_i]["word_params"][word_i]
    for p in PARAMS:
        st.session_state[slider_key(ex_i, word_i, p)] = float(wp[p])

def toggle_word(ex_i, word_i):
    selected = st.session_state.trial_state[ex_i]["selected_words"]

    if word_i in selected:
        if len(selected) > 1:
            selected.remove(word_i)
        else:
            st.session_state.status_message = "You must keep at least one word selected."
            return
    else:
        selected.append(word_i)
        selected.sort()

    # anchor is always the first selected word
    anchor = selected[0]
    load_word_into_sliders(ex_i, anchor)
    st.session_state.status_message = f"Selected {len(selected)} word(s)."

def save_sliders_into_word(ex_i, anchor_word_i):
    selected = st.session_state.trial_state[ex_i]["selected_words"]

    # read values from anchor sliders
    new_vals = {p: float(st.session_state.get(slider_key(ex_i, anchor_word_i, p), 0.0)) for p in PARAMS}

    # apply to all selected words
    for wi in selected:
        for p in PARAMS:
            st.session_state.trial_state[ex_i]["word_params"][wi][p] = new_vals[p]
            st.session_state[slider_key(ex_i, wi, p)] = new_vals[p]

    st.session_state.status_message = f"Edit in progress: updated {len(selected)} word(s)."

def reset_word(ex_i, anchor_word_i):
    selected = st.session_state.trial_state[ex_i]["selected_words"]
    for wi in selected:
        st.session_state.trial_state[ex_i]["word_params"][wi] = default_param()
        for p in PARAMS:
            st.session_state[slider_key(ex_i, wi, p)] = 0.0

    # reload sliders from anchor
    load_word_into_sliders(ex_i, anchor_word_i)
    st.session_state.status_message = f"Parameters reset for {len(selected)} selected word(s)."

def reset_all(ex_i):
    words = examples[ex_i]["transcript"].split()
    st.session_state.trial_state[ex_i]["word_params"] = {i: default_param() for i in range(len(words))}
    st.session_state.trial_state[ex_i]["selected_words"] = [0]
    load_word_into_sliders(ex_i, 0)
    st.session_state.status_message = "Parameters reset for all words."

    # if user resets, they should regenerate to hear a new one
    if ex_i in st.session_state.generated_audio:
        del st.session_state.generated_audio[ex_i]

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

    out_path = f"generated/ex{ex_i+1}_generated.wav"

    req = {
        "audio_id": trial.get("audio_id", ex_i + 1),
        "baseline_path": trial["baseline"],
        "word_params": wp_json,
        "output_path": out_path,
    }

    req_path = f"requests/ex{ex_i+1}_request.json"
    with open(req_path, "w", encoding="utf-8") as f:
        json.dump(req, f, indent=2)

    return req_path, out_path

def run_generate_script(request_path):
    result = subprocess.run(
        [sys.executable, "scripts/generate_audio.py", "--request", request_path],
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout, result.stderr


def submit_all_changes(ex_i):
    st.session_state.status_message = "Submitting changes..."

    req_path, out_path = write_request_json(ex_i)

    code, out, err = run_generate_script(req_path)

    if code != 0:
        st.session_state.status_message = f"Error running generate_audio.py: {err or out}"
        return

    # After script runs, we expect the wav to exist in /generated
    if Path(out_path).exists():
        st.session_state.generated_audio[ex_i] = out_path
        st.session_state.status_message = "Generated new modified audio successfully."
    else:
        st.session_state.status_message = f"Script ran but output was not found: {out_path}"


# Current example context
# refresh examples after potential upload
examples = built_in_examples + st.session_state.user_trials

# clamp example index just in case
st.session_state.example_index = max(0, min(st.session_state.example_index, len(examples) - 1))
ex_i = st.session_state.example_index

transcript_words = ensure_trial_state(ex_i)

selected_words = st.session_state.trial_state[ex_i]["selected_words"]
if not selected_words:
    selected_words = [0]
    st.session_state.trial_state[ex_i]["selected_words"] = selected_words

# anchor word = first selected
anchor_idx = selected_words[0]

if slider_key(ex_i, anchor_idx, "breathiness") not in st.session_state:
    load_word_into_sliders(ex_i, anchor_idx)


# --- UI STARTS HERE ---

top_left, top_right = st.columns([7, 2])
with top_left:
    st.title(f"Audio {ex_i + 1} of {len(examples)}")

with top_right:
    # Minimal button that opens a clean popover (does not push the layout)
    with st.popover("➕"):
        st.markdown("**Add new trial**")
        st.caption("User-added trials are temporary. They reset when the session resets.")

        up_col1, up_col2 = st.columns(2)

        with up_col1:
            uploaded_baseline = st.file_uploader(
                "Baseline WAV (required)",
                type=["wav"],
                key=f"upload_baseline_{st.session_state.upload_nonce}"
            )

        with up_col2:
            uploaded_original = st.file_uploader(
                "Original WAV (optional)",
                type=["wav"],
                key=f"upload_original_{st.session_state.upload_nonce}"
            )

        uploaded_transcript = st.text_area(
            "Transcript (required)",
            key=f"upload_transcript_{st.session_state.upload_nonce}",
            placeholder="Type the transcript here..."
        )

        save_clicked = st.button("Save trial", type="primary", use_container_width=True)

        if save_clicked:
            if uploaded_baseline is None:
                st.session_state.status_message = "Please upload a baseline WAV."
            elif not uploaded_transcript.strip():
                st.session_state.status_message = "Please type the transcript."
            else:
                add_user_trial(uploaded_baseline, uploaded_original, uploaded_transcript)
                # NEW: reset uploader/text_area keys so the next add is clean
                st.session_state.upload_nonce += 1
                st.rerun()


st.header("Original Audio:")
if examples[ex_i].get("original"):
    st.audio(examples[ex_i]["original"])
else:
    st.info("No original audio provided for this trial.")
st.divider()

st.header("Baseline Audio:")
st.audio(examples[ex_i]["baseline"])

# chunk words per row so it doesn't collapse on small widths
words_per_row = 6

for start in range(0, len(transcript_words), words_per_row):
    row_words = transcript_words[start:start + words_per_row]
    cols = st.columns(words_per_row)
    for j, word in enumerate(row_words):
        i = start + j
        with cols[j]:
            st.button(
                word,
                key=f"word_ex{ex_i}_{i}",
                on_click=toggle_word,
                args=(ex_i, i),
                use_container_width=True,
                type="primary" if (i in selected_words) else "secondary",
            )

st.write("")
st.write("")
st.write("")

st.slider(
    "Average Pitch",
    -2.0,
    2.0,
    step=0.1,
    key=slider_key(ex_i, anchor_idx, "average_pitch"),
    on_change=save_sliders_into_word,
    args=(ex_i, anchor_idx),
)

st.slider(
    "Average Range",
    -2.0,
    2.0,
    step=0.1,
    key=slider_key(ex_i, anchor_idx, "average_range"),
    on_change=save_sliders_into_word,
    args=(ex_i, anchor_idx),
)

st.slider(
    "Breathiness",
    0.0,
    2.0,
    step=0.1,
    key=slider_key(ex_i, anchor_idx, "breathiness"),
    on_change=save_sliders_into_word,
    args=(ex_i, anchor_idx),
)

st.slider(
    "Creakiness",
    0.0,
    2.0,
    step=0.1,
    key=slider_key(ex_i, anchor_idx, "creakiness"),
    on_change=save_sliders_into_word,
    args=(ex_i, anchor_idx),
)

st.slider(
    "Nasality",
    0.0,
    2.0,
    step=0.1,
    key=slider_key(ex_i, anchor_idx, "nasality"),
    on_change=save_sliders_into_word,
    args=(ex_i, anchor_idx),
)

st.write("")
st.write("")

c1, c2, c3 = st.columns(3)
with c1:
    st.button("Submit changes", on_click=submit_all_changes, args=(ex_i,), use_container_width=True)
with c2:
    # reset selected words (not just one)
    st.button("Reset word(s)", on_click=reset_word, args=(ex_i, anchor_idx), use_container_width=True)
with c3:
    st.button("Reset all", on_click=reset_all, args=(ex_i,), use_container_width=True)

st.divider()

st.header("Modified Audio:")
# Only playable after user submits (generated exists). Otherwise show a message.
if ex_i in st.session_state.generated_audio:
    st.audio(st.session_state.generated_audio[ex_i])
else:
    st.info("No generated audio yet. Click **Submit changes** to create the modified audio.")
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

st.divider()

with st.expander("Word parameters (current example)"):
    wp = st.session_state.trial_state[ex_i]["word_params"]
    for i, w in enumerate(transcript_words):
        st.write(f"{i} ({w}): {wp[i]}")