from streamlit_extras.stylable_container import stylable_container
import sys
import streamlit as st
import pandas as pd
import json
import subprocess
from pathlib import Path

st.set_page_config(page_title="Demo", layout="centered")

# Page width and padding
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

def load_trials(path="data/trials.csv"):
    try:
        df = pd.read_csv(path)
        return df.to_dict(orient="records")
    except FileNotFoundError:
        print(f"Warning: {path} not found. No built-in trials will be loaded.")
        return []
    except pd.errors.EmptyDataError:
        print(f"Warning: {path} is empty. No built-in trials will be loaded.")
        return []

def is_valid_trial(trial):
    baseline_ok = Path(trial["baseline"]).exists()

    transcript_value = trial.get("transcript", "")
    transcript_ok = pd.notna(transcript_value) and bool(str(transcript_value).strip())

    return baseline_ok and transcript_ok

# Filter invalid built-in trials once and keep count
_loaded_trials = load_trials()
built_in_examples = []
invalid_trial_count = 0

for t in _loaded_trials:
    if is_valid_trial(t):
        built_in_examples.append(t)
    else:
        invalid_trial_count += 1

# Parameters controlled by sliders
PARAMS = ["breathiness", "creakiness", "nasality", "average_pitch", "average_range"]

def default_param():
    return {p: 0.0 for p in PARAMS}

def word_is_modified(ex_i, word_i):
    # Returns True if the word has parameters different from the default.
    wp = st.session_state.trial_state[ex_i]["word_params"][word_i]
    for p in PARAMS:
        if wp[p] != 0.0:
            return True
    return False

def slider_key(ex_i, word_i, param):
    return f"ex{ex_i}_{word_i}_{param}"


# Session state initialization
if "example_index" not in st.session_state:
    st.session_state.example_index = 0

if "trial_state" not in st.session_state:
    st.session_state.trial_state = {}
    # {example_index: {"selected_words": [int,...], "anchor_word": int, "word_params": {word_index: {param: value}}}}

if "status_message" not in st.session_state:
    st.session_state.status_message = "No changes applied"

if "generated_audio" not in st.session_state:
    st.session_state.generated_audio = {}
    # {ex_i: "generated/ex1_generated.wav"}

# User-uploaded trials live only for the current session
if "user_trials" not in st.session_state:
    st.session_state.user_trials = []

# Used to reset uploader widgets cleanly after saving a trial
if "upload_nonce" not in st.session_state:
    st.session_state.upload_nonce = 0

# Local folders used by the app
Path("uploads").mkdir(exist_ok=True)
Path("requests").mkdir(exist_ok=True)
Path("generated").mkdir(exist_ok=True)

# Combine built-in + user uploaded trials
examples = built_in_examples + st.session_state.user_trials

def add_user_trial(baseline_file, original_file, transcript_text):
    # baseline is required, transcript required
    user_id = len(st.session_state.user_trials) + 1
    audio_id = f"user_{user_id}"

    # Save baseline locally so the generator can read it
    baseline_path = f"uploads/{audio_id}_baseline.wav"
    with open(baseline_path, "wb") as f:
        f.write(baseline_file.getbuffer())

    # Original is optional
    original_path = ""
    if original_file is not None:
        original_path = f"uploads/{audio_id}_original.wav"
        with open(original_path, "wb") as f:
            f.write(original_file.getbuffer())

    # Trial follows the same schema as trials.csv
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

    # reset widgets
    st.session_state.upload_nonce += 1

    st.session_state.status_message = f"Added new trial ({audio_id})."

def render_add_trial_popover():
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
                st.session_state.upload_nonce += 1
                st.rerun()

def ensure_trial_state(ex_i):
    # Creates the per-trial state the first time we visit it
    words = examples[ex_i]["transcript"].split()
    if ex_i not in st.session_state.trial_state:
        st.session_state.trial_state[ex_i] = {
            "selected_words": [0],
            "anchor_word": 0,
            "word_params": {i: default_param() for i in range(len(words))},
        }
    else:
        # Keep at least one selected word at all times
        if "selected_words" not in st.session_state.trial_state[ex_i] or not st.session_state.trial_state[ex_i]["selected_words"]:
            st.session_state.trial_state[ex_i]["selected_words"] = [0]
            st.session_state.trial_state[ex_i]["anchor_word"] = 0

        # If anchor is missing or invalid, fall back to first selected
        if "anchor_word" not in st.session_state.trial_state[ex_i]:
            st.session_state.trial_state[ex_i]["anchor_word"] = st.session_state.trial_state[ex_i]["selected_words"][0]

    return words

def load_word_into_sliders(ex_i, word_i):
    # Push the stored word params into the visible slider widgets
    wp = st.session_state.trial_state[ex_i]["word_params"][word_i]
    for p in PARAMS:
        st.session_state[slider_key(ex_i, word_i, p)] = float(wp[p])

def toggle_word(ex_i, word_i):
    # Select or deselect a word in the transcript
    selected = st.session_state.trial_state[ex_i]["selected_words"]
    anchor = st.session_state.trial_state[ex_i]["anchor_word"]

    if word_i in selected:
        if len(selected) > 1:
            selected.remove(word_i)

            # If user removed the anchor, pick a new anchor
            if word_i == anchor:
                st.session_state.trial_state[ex_i]["anchor_word"] = selected[0]
        else:
            st.session_state.status_message = "You must keep at least one word selected."
            return
    else:
        selected.append(word_i)

        st.session_state.trial_state[ex_i]["word_params"][word_i] = default_param()

    anchor = st.session_state.trial_state[ex_i]["anchor_word"]
    load_word_into_sliders(ex_i, anchor)
    st.session_state.status_message = f"Selected {len(selected)} word(s)."

def save_sliders_into_word(ex_i, anchor_word_i):
    # Applies the anchor slider values to every selected word
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
    # Resets params only for the currently selected words
    selected = st.session_state.trial_state[ex_i]["selected_words"]
    for wi in selected:
        st.session_state.trial_state[ex_i]["word_params"][wi] = default_param()
        for p in PARAMS:
            st.session_state[slider_key(ex_i, wi, p)] = 0.0

    # reload sliders from anchor
    load_word_into_sliders(ex_i, anchor_word_i)
    st.session_state.status_message = f"Parameters reset for {len(selected)} selected word(s)."

def reset_all(ex_i):
    # Resets params for the entire transcript of this trial
    words = examples[ex_i]["transcript"].split()
    st.session_state.trial_state[ex_i]["word_params"] = {i: default_param() for i in range(len(words))}
    st.session_state.trial_state[ex_i]["selected_words"] = [0]
    st.session_state.trial_state[ex_i]["anchor_word"] = 0
    load_word_into_sliders(ex_i, 0)
    st.session_state.status_message = "Parameters reset for all words."

    # if user resets, they should regenerate to hear a new one
    if ex_i in st.session_state.generated_audio:
        del st.session_state.generated_audio[ex_i]

def prev_example():
    # Go to the previous trial
    st.session_state.example_index = max(0, st.session_state.example_index - 1)
    st.session_state.status_message = f"Moved to example {st.session_state.example_index + 1}"

def next_example():
    # Go to the next trial
    st.session_state.example_index = min(len(examples) - 1, st.session_state.example_index + 1)
    st.session_state.status_message = f"Moved to example {st.session_state.example_index + 1}"

def write_request_json(ex_i):
    # Writes a request file that the backend script can consume
    trial = examples[ex_i]
    words = trial["transcript"].split()
    wp = st.session_state.trial_state[ex_i]["word_params"]

    # Convert indices to strings to keep JSON simple
    wp_json = {str(i): {k: float(v) for k, v in wp[i].items()} for i in range(len(words))}

    # Output is overwritten per example for now
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
    # Runs the generator as a separate process
    result = subprocess.run(
        [sys.executable, "scripts/generate_audio.py", "--request", request_path],
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout, result.stderr

def submit_all_changes(ex_i):
    # Generates a new modified audio for the current trial
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

# Show a simple warning if some predefined trials were skipped
if invalid_trial_count > 0:
    st.warning("Some trials were skipped because their files or transcript were missing.")

# Empty state when there are no trials
if len(examples) == 0:
    top_left, top_right = st.columns([7, 1])

    with top_left:
        st.title("No trials available")

    with top_right:
        render_add_trial_popover()

    st.info("Click the ➕ button to add a trial before starting.")
    st.stop()

# clamp example index just in case
st.session_state.example_index = max(0, min(st.session_state.example_index, len(examples) - 1))
ex_i = st.session_state.example_index

transcript_words = ensure_trial_state(ex_i)

selected_words = st.session_state.trial_state[ex_i]["selected_words"]
if not selected_words:
    selected_words = [0]
    st.session_state.trial_state[ex_i]["selected_words"] = selected_words

# anchor word comes from explicit state now
anchor_idx = st.session_state.trial_state[ex_i]["anchor_word"]

# Clamp anchor just in case
anchor_idx = max(0, min(anchor_idx, len(transcript_words) - 1))
st.session_state.trial_state[ex_i]["anchor_word"] = anchor_idx

# Load slider values the first time we land on this anchor
if slider_key(ex_i, anchor_idx, "breathiness") not in st.session_state:
    load_word_into_sliders(ex_i, anchor_idx)


# --- UI STARTS HERE ---
top_left, top_right = st.columns([7, 1])
with top_left:
    st.title(f"Audio {ex_i + 1} of {len(examples)}")

with top_right:
    render_add_trial_popover()

st.header("Original Audio:")
original_path = examples[ex_i].get("original", "")

if original_path and Path(original_path).exists():
    st.audio(original_path)
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
            is_selected = i in selected_words
            is_modified = word_is_modified(ex_i, i)

            if is_selected:
                button_css = """
                button {
                    background-color: #1f77ff;
                    color: white;
                    border: 1px solid #1f77ff;
                }
                """
            elif is_modified:
                button_css = """
                button {
                    background-color: #22c55e;
                    color: white;
                    border: 1px solid #22c55e;
                }
                """
            else:
                button_css = """
                button {
                    background-color: #f0f2f6;
                    color: black;
                    border: 1px solid #ddd;
                }
                """

            with stylable_container(
                key=f"word_container_{ex_i}_{i}",
                css_styles=button_css
            ):
                st.button(
                    word,
                    key=f"word_ex{ex_i}_{i}",
                    on_click=toggle_word,
                    args=(ex_i, i),
                    use_container_width=True,
                )

st.write("")
st.write("")
st.write("")

# Sliders reflect the anchor word but apply to all selected words
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
    st.button("Reset word(s)", on_click=reset_word, args=(ex_i, anchor_idx), use_container_width=True)
with c3:
    st.button("Reset all", on_click=reset_all, args=(ex_i,), use_container_width=True)

st.divider()

st.header("Modified Audio:")
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