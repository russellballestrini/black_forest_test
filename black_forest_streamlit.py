import streamlit as st
import os
import requests
import json
import base64
import sqlite3
import tempfile
from datetime import datetime
import http.client
import time
import re
import random


def create_slug(prompt, max_words=10):
    words = prompt.split()[:max_words]
    slug = "-".join(words)
    slug = re.sub(r"[^\w\-]", "", slug.lower())
    timestamp = int(time.time())
    return f"{slug}-{timestamp}"


def poll_for_result(conn, headers, request_id):
    """Poll the BFL server for the generation result."""
    while True:
        conn.request("GET", f"/v1/get_result?id={request_id}", headers=headers)
        res = conn.getresponse()
        data = res.read()
        response = json.loads(data.decode("utf-8"))

        if "status" in response:
            if response["status"] == "Ready":
                return response
            elif response["status"] == "Failed":
                raise Exception("Image generation failed")
            elif response["status"] == "Pending":
                # Instead of spamming top real estate, let's keep minimal text or logs here
                pass
            else:
                raise Exception(f"Unknown status: {response['status']}")
        else:
            raise Exception("Unexpected response structure from poll_for_result.")

        time.sleep(5)


def generate_image(prompt, api_key, endpoint, seed):
    """Send the generation request to the chosen BFL endpoint with the provided seed."""
    conn = http.client.HTTPSConnection("api.bfl.ml")
    headers = {"Content-Type": "application/json", "X-Key": api_key}

    payload = {
        "prompt": prompt,
        "max_tokens": 512,
        "temperature": 0.7,
        "top_p": 0.9,
        "top_k": 40,
        "repetition_penalty": 1.1,
        "stop": ["\n\n"],
        "seed": seed,
    }

    conn.request("POST", f"/v1/{endpoint}", body=json.dumps(payload), headers=headers)
    res = conn.getresponse()
    data = res.read()

    response_data = json.loads(data.decode("utf-8"))
    request_id = response_data.get("id")
    if not request_id:
        raise Exception(f"Failed to get request_id from response: {response_data}")

    result = poll_for_result(conn, headers, request_id)
    if "result" in result and "sample" in result["result"]:
        return result["result"]["sample"]
    else:
        raise Exception("No image URL found in the final response.")


# -------------------- Streamlit App --------------------
st.title("Black Forest Labs Image Generation")

# Check environment vs. secrets for API key
deployed = False
try:
    if hasattr(st, "secrets") and st.secrets:
        deployed = True
        api_key = st.secrets.get("BLACK_FOREST_LABS_API_KEY")
    else:
        api_key = os.environ.get("BLACK_FOREST_LABS_API_KEY")
except FileNotFoundError:
    api_key = os.environ.get("BLACK_FOREST_LABS_API_KEY")

if not api_key:
    st.error(
        "BLACK_FOREST_LABS_API_KEY is not set in secrets or environment variables. Please set it before running the app."
    )
    st.stop()

# -- Initialize session state --
if "generated_images" not in st.session_state:
    st.session_state.generated_images = []

# -----------------------------------------------------------------
# Load previously generated images from the local DB (if any), only if running locally.
# We ORDER BY timestamp DESC to get newest first.
# -----------------------------------------------------------------
if not deployed:
    conn = sqlite3.connect("image_metadata.db")
    cursor = conn.cursor()
    cursor.execute(
        """CREATE TABLE IF NOT EXISTS images
                      (id INTEGER PRIMARY KEY, slug TEXT, prompt TEXT, filename TEXT, base64_image TEXT, timestamp DATETIME)"""
    )
    conn.commit()

    # Only load these once, if the session is fresh (no images in session state yet)
    if len(st.session_state.generated_images) == 0:
        rows = cursor.execute(
            "SELECT slug, prompt, filename, base64_image, timestamp FROM images ORDER BY timestamp DESC"
        ).fetchall()
        conn.close()

        for slug, prompt_text, filename, base64_img_str, _ in rows:
            image_data = base64.b64decode(base64_img_str)
            temp_dir = tempfile.mkdtemp()
            filepath = os.path.join(temp_dir, filename)
            with open(filepath, "wb") as f:
                f.write(image_data)
            # Insert at the *end* of the list if we want to preserve the DESC from DB,
            # but we want the newest first in final display. We'll just append in the loop
            # and reverse the final list or insert(0). Let's keep it simple:
            st.session_state.generated_images.append((filepath, filename, prompt_text))

# We'll store any errors in a variable and show them later (at the bottom) to save vertical space
error_message = None

# ---------------------------------------------------------
# Sidebar UI: Model Selection, Seed selection (random or fixed)
# ---------------------------------------------------------
st.sidebar.subheader("BFL Model Settings")

model_options = [
    "flux-dev",  # default
    "flux-pro-1.1-ultra",  # more expensive
    "flux-pro-1.1",  # another variant
]
selected_model = st.sidebar.selectbox("Choose a model endpoint", model_options, index=0)

use_random_seed = st.sidebar.checkbox("Use random seed?", value=False)
if use_random_seed:
    seed_value = random.randint(1, 9999999)
    st.sidebar.write(f"Random seed chosen: {seed_value}")
else:
    seed_value = st.sidebar.number_input(
        "Set a specific seed", value=42, min_value=0, max_value=99999999, step=1
    )

# ---------------------------------------------------------
# Prompt + Generate (with Enter key to submit)
# ---------------------------------------------------------
with st.form("prompt_form", clear_on_submit=False):
    prompt = st.text_input("Enter your image prompt:")
    generate_submitted = st.form_submit_button(
        "Generate Image"
    )  # Pressing Enter or the button triggers this

if generate_submitted:
    if prompt.strip():
        try:
            image_url = generate_image(prompt, api_key, selected_model, seed_value)
            response = requests.get(image_url)
            if response.status_code == 200:
                slug = create_slug(prompt)
                filename = f"{slug}.jpg"

                if not deployed:
                    # Local environment: save file + metadata
                    os.makedirs("images", exist_ok=True)
                    filepath = os.path.join("images", filename)
                    with open(filepath, "wb") as f:
                        f.write(response.content)

                    # Store in SQLite
                    conn = sqlite3.connect("image_metadata.db")
                    cursor = conn.cursor()
                    base64_image = base64.b64encode(response.content).decode("utf-8")
                    cursor.execute(
                        "INSERT INTO images (slug, prompt, filename, base64_image, timestamp) VALUES (?, ?, ?, ?, ?)",
                        (slug, prompt, filename, base64_image, datetime.now()),
                    )
                    conn.commit()
                    conn.close()

                    # Insert at top of session state
                    st.session_state.generated_images.insert(
                        0, (filepath, filename, prompt)
                    )

                else:
                    # Deployed environment
                    temp_dir = tempfile.mkdtemp()
                    filepath = os.path.join(temp_dir, filename)
                    with open(filepath, "wb") as f:
                        f.write(response.content)
                    st.session_state.generated_images.insert(
                        0, (filepath, filename, prompt)
                    )

                st.success("Image generated successfully!")
            else:
                error_message = f"Failed to download image. HTTP status code: {response.status_code}"
        except Exception as e:
            error_message = str(e)
    else:
        error_message = "Please enter a non-empty prompt."

# --------------------------------------------------
# Display images: newest first
# --------------------------------------------------
st.subheader("Generated Images (Newest First)")
for filepath, filename, prompt_text in st.session_state.generated_images:
    st.image(filepath, caption=f"Prompt: {prompt_text}", use_column_width=True)
    with open(filepath, "rb") as file:
        st.download_button(
            label=f"Download {filename}",
            data=file,
            file_name=filename,
            mime="image/jpeg",
        )

# --------------------------------------------------
# Show any error messages at the bottom
# --------------------------------------------------
if error_message:
    st.error(error_message)

# --------------------------------------------------
# Sidebar info for local environment usage
# --------------------------------------------------
st.sidebar.info(
    "To run locally, set the BLACK_FOREST_LABS_API_KEY environment variable:\n\n"
    "export BLACK_FOREST_LABS_API_KEY='your_api_key_here'\n\n"
    "If deploying, set the API key in Streamlit secrets."
)

if deployed:
    st.write("Running in deployed environment")
else:
    st.write("Running locally")
