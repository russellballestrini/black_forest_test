import streamlit as st
import subprocess
import os

st.title("Black Forest Labs Image Generation")

# Check if the API key is set in the environment
api_key = os.environ.get("BLACK_FOREST_LABS_API_KEY")
if not api_key:
    st.error(
        "BLACK_FOREST_LABS_API_KEY is not set in the environment. Please set it before running the app."
    )
    st.stop()

prompt = st.text_input("Enter your image prompt:")

if st.button("Generate Image"):
    if prompt:
        # Run the black_forest_test.py script with the provided prompt
        result = subprocess.run(
            ["python", "black_forest_test.py", prompt], capture_output=True, text=True
        )

        # Display the output
        st.text(result.stdout)

        # Display the generated image
        image_dir = "images"
        if os.path.exists(image_dir) and os.listdir(image_dir):
            latest_image = max(
                os.listdir(image_dir),
                key=lambda f: os.path.getctime(os.path.join(image_dir, f)),
            )
            st.image(os.path.join(image_dir, latest_image), caption="Generated Image")
        else:
            st.warning("No images found in the 'images' directory.")
    else:
        st.error("Please enter a prompt")

# Display all generated images
st.subheader("Generated Images")
image_dir = "images"
if os.path.exists(image_dir) and os.listdir(image_dir):
    for image in sorted(
        os.listdir(image_dir),
        key=lambda f: os.path.getctime(os.path.join(image_dir, f)),
        reverse=True,
    ):
        st.image(os.path.join(image_dir, image), caption=image, use_column_width=True)
else:
    st.info("No images have been generated yet.")

# Add a note about setting the API key
st.sidebar.info(
    "Make sure to set the BLACK_FOREST_LABS_API_KEY environment variable before running this app. "
    "You can do this by running:\n\n"
    "export BLACK_FOREST_LABS_API_KEY='your_api_key_here'\n\n"
    "Replace 'your_api_key_here' with your actual API key."
)
