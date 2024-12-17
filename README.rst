Black Forest Labs Image Generation
==================================

This project allows you to generate images based on prompts using the Black Forest Labs API. The generated images are saved to a local directory, and their metadata, including base64 representations, are stored in a SQLite database.

Requirements
------------

- Python 3.x
- Required Python packages:
    - ``http.client``
    - ``json``
    - ``base64``
    - ``os``
    - ``time``
    - ``requests``
    - ``streamlit`` (optional for web user interface)
    - ``argparse``
    - ``re``
    - ``sqlite3``
    - ``datetime``

Installation
------------

Install required packages::

    pip install -r requirements.txt

Setup
-----

1. Clone the Repository
~~~~~~~~~~~~~~~~~~~~~

Clone this repository to your local machine::

    git clone black_forest_test
    cd black_forest_test

2. Set Up Environment Variables
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Set your API key as an environment variable::

    export BLACK_FOREST_LABS_API_KEY="your_api_key_here"

Replace ``"your_api_key_here"`` with your actual Black Forest Labs API key.

Usage
-----

Run the script with a prompt::

    python black_forest_test.py "A beautiful sunset over the mountains"

The script will automatically create an ``images`` directory for storing generated images.


Run the streamlit!::

    streamlit run black_forest_streamlit.py


Output
------

- Generated images are saved in the ``images`` directory
- Image metadata stored in ``image_metadata.db`` SQLite database

Database Structure
-----------------

The ``images`` table contains:

- **id**: Unique identifier (INTEGER PRIMARY KEY)
- **slug**: Prompt-based slug (TEXT)
- **prompt**: Original generation prompt (TEXT)
- **filename**: Saved image filename (TEXT)
- **base64_image**: Base64 encoded image (TEXT)
- **timestamp**: Creation timestamp (DATETIME)

Notes
-----

- Requires active internet connection
- Keep API key confidential

License
-------

This work is dedicated to the public domain.

