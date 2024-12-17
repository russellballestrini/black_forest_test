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
                st.text("Still processing...")
            else:
                st.text(f"Unknown status: {response['status']}")
        else:
            st.text("Unexpected response structure")

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
        "seed": seed,  # Pass the user-chosen (or random) seed
    }

    # Use the chosen endpoint (e.g., "flux-dev", "flux-pro-1.1-ultra", etc.)
    conn.request("POST", f"/v1/{endpoint}", body=json.dumps(payload), headers=headers)
    res = conn.getresponse()
    data = res.read()

    response_data = json.loads(data.decode("utf-8"))
    request_id = response_data["id"]
    st.text(f"Generation request ID: {request_id}")

    result = poll_for_result(conn, headers, request_id)

    if "result" in result and "sample" in result["result"]:
        return result["result"]["sample"]
    else:
        st.error("No image URL found in the response")
        return None


# -------------------- Streamlit App --------------------
st.title("Black Forest Labs Image Generation")

# Track whether we're deployed or running locally
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
# Load previously generated images from the local DB (if any).
# We show newest images first, so we ORDER BY timestamp DESC in the query.
# -----------------------------------------------------------------
if not deployed:
    conn = sqlite3.connect("image_metadata.db")
    cursor = conn.cursor()
    cursor.execute(
        """CREATE TABLE IF NOT EXISTS images
                      (id INTEGER PRIMARY KEY, slug TEXT, prompt TEXT, filename TEXT, base64_image TEXT, timestamp DATETIME)"""
    )
    conn.commit()

    rows = cursor.execute(
        "SELECT slug, prompt, filename, base64_image, timestamp FROM images ORDER BY timestamp DESC"
    ).fetchall()
    conn.close()

    # If the session just started (no images in session state), load images from DB
    if len(st.session_state.generated_images) == 0:
        for slug, prompt, filename, base64_image, _ in rows:
            image_data = base64.b64decode(base64_image)
            temp_dir = tempfile.mkdtemp()
            filepath = os.path.join(temp_dir, filename)
            with open(filepath, "wb") as f:
                f.write(image_data)
            # Insert at the bottom of the list if we're iterating in DESC order
            # But we want newest at top, so actually we can just append in the order they come in
            st.session_state.generated_images.append((filepath, filename, prompt))

# ---------------------------------------------------------
# UI: Model Selection, Seed selection (random or fixed)
# ---------------------------------------------------------
st.sidebar.subheader("BFL Model Settings")

# Available model endpoints
model_options = ["flux-dev", "flux-pro-1.1-ultra", "flux-pro-1.1"]  # default
selected_model = st.sidebar.selectbox("Choose a model endpoint", model_options, index=0)

use_random_seed = st.sidebar.checkbox("Use random seed?", value=False)
seed_value = 42  # default
if use_random_seed:
    seed_value = random.randint(1, 9999999)
    st.sidebar.write(f"Random seed chosen: {seed_value}")
else:
    seed_value = st.sidebar.number_input(
        "Set a specific seed", value=42, min_value=0, max_value=99999999, step=1
    )

st.write("**Current model endpoint:**", selected_model)
st.write("**Current seed:**", seed_value)

prompt = st.text_input("Enter your image prompt:")

if st.button("Generate Image"):
    if prompt:
        image_url = generate_image(prompt, api_key, selected_model, seed_value)
        if image_url:
            response = requests.get(image_url)
            if response.status_code == 200:
                slug = create_slug(prompt)
                filename = f"{slug}.jpg"

                if not deployed:
                    # Local environment: save to 'images' directory and SQLite
                    os.makedirs("images", exist_ok=True)
                    filepath = os.path.join("images", filename)
                    with open(filepath, "wb") as f:
                        f.write(response.content)

                    # Save to SQLite
                    conn = sqlite3.connect("image_metadata.db")
                    cursor = conn.cursor()
                    cursor.execute(
                        """CREATE TABLE IF NOT EXISTS images
                                      (id INTEGER PRIMARY KEY, slug TEXT, prompt TEXT, filename TEXT, base64_image TEXT, timestamp DATETIME)"""
                    )
                    base64_image = base64.b64encode(response.content).decode("utf-8")
                    cursor.execute(
                        "INSERT INTO images (slug, prompt, filename, base64_image, timestamp) VALUES (?, ?, ?, ?, ?)",
                        (slug, prompt, filename, base64_image, datetime.now()),
                    )
                    conn.commit()
                    conn.close()

                    # Insert the new image at the top so it's displayed first
                    st.session_state.generated_images.insert(
                        0, (filepath, filename, prompt)
                    )

                    st.success(
                        f"Image saved locally as '{filename}' and metadata stored in SQLite."
                    )
                else:
                    # Deployed environment: use a temporary file
                    temp_dir = tempfile.mkdtemp()
                    filepath = os.path.join(temp_dir, filename)
                    with open(filepath, "wb") as f:
                        f.write(response.content)

                    # Insert at top
                    st.session_state.generated_images.insert(
                        0, (filepath, filename, prompt)
                    )

                st.success("Image generated successfully!")
            else:
                st.error(
                    f"Failed to download image. Status code: {response.status_code}"
                )
    else:
        st.error("Please enter a prompt")

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

# Add a note about setting the API key
st.sidebar.info(
    "Make sure to set the BLACK_FOREST_LABS_API_KEY environment variable before running this app locally. "
    "You can do this by running:\n\n"
    "export BLACK_FOREST_LABS_API_KEY='your_api_key_here'\n\n"
    "Replace 'your_api_key_here' with your actual API key.\n\n"
    "If deploying, set the API key in Streamlit secrets."
)

if deployed:
    st.write("Running in deployed environment")
else:
    st.write("Running locally")
