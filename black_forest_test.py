import http.client
import json
import base64
import os
import time
import requests
import argparse
import re
import sqlite3
from datetime import datetime


def create_slug(prompt, max_words=10):
    words = prompt.split()[:max_words]
    slug = "-".join(words)
    slug = re.sub(r"[^\w\-]", "", slug.lower())
    timestamp = int(time.time())
    return f"{slug}-{timestamp}"


def poll_for_result(conn, headers, request_id):
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
                print("Still processing...")
            else:
                print(f"Unknown status: {response['status']}")
        else:
            print("Unexpected response structure")

        time.sleep(5)


def main():
    parser = argparse.ArgumentParser(
        description="Generate an image using Black Forest Labs API"
    )
    parser.add_argument("prompt", help="The prompt for image generation")
    args = parser.parse_args()

    api_key = os.environ.get("BLACK_FOREST_LABS_API_KEY")
    if not api_key:
        raise ValueError("BLACK_FOREST_LABS_API_KEY environment variable is not set")

    conn = http.client.HTTPSConnection("api.bfl.ml")
    headers = {"Content-Type": "application/json", "X-Key": api_key}

    payload = {
        "prompt": args.prompt,
        "max_tokens": 512,
        "temperature": 0.7,
        "top_p": 0.9,
        "top_k": 40,
        "repetition_penalty": 1.1,
        "stop": ["\n\n"],
        "seed": 42,
    }

    conn.request("POST", "/v1/flux-dev", body=json.dumps(payload), headers=headers)
    # More expensive models (commented out):
    # conn.request("POST", "/v1/flux-pro-1.1-ultra", body=json.dumps(payload), headers=headers)
    # conn.request("POST", "/v1/flux-pro-1.1", body=json.dumps(payload), headers=headers)

    res = conn.getresponse()
    data = res.read()

    response_data = json.loads(data.decode("utf-8"))
    request_id = response_data["id"]
    print(f"Image generation request ID: {request_id}")

    result = poll_for_result(conn, headers, request_id)

    if "result" in result and "sample" in result["result"]:
        image_url = result["result"]["sample"]

        # Download the image
        response = requests.get(image_url)
        if response.status_code == 200:
            # Create a slug from the prompt and timestamp
            slug = create_slug(args.prompt)

            # Create 'images' directory if it doesn't exist
            os.makedirs("images", exist_ok=True)

            # Save the image to file system in the 'images' folder
            filename = f"{slug}.jpg"
            filepath = os.path.join("images", filename)
            with open(filepath, "wb") as image_file:
                image_file.write(response.content)
            print(f"Image saved as '{filepath}'")

            # Convert image to base64
            base64_image = base64.b64encode(response.content).decode("utf-8")

            # Connect to SQLite database
            db_conn = sqlite3.connect("image_metadata.db")
            cursor = db_conn.cursor()

            # Create table if it doesn't exist
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS images (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    slug TEXT,
                    prompt TEXT,
                    filename TEXT,
                    base64_image TEXT,
                    timestamp DATETIME
                )
            """
            )

            # Insert data into the database
            cursor.execute(
                """
                INSERT INTO images (slug, prompt, filename, base64_image, timestamp)
                VALUES (?, ?, ?, ?, ?)
            """,
                (slug, args.prompt, filename, base64_image, datetime.now()),
            )

            db_conn.commit()
            db_conn.close()

            print(f"Image metadata and base64 saved to database with slug: {slug}")
        else:
            print(f"Failed to download image. Status code: {response.status_code}")
    else:
        print("No image URL found in the response")


if __name__ == "__main__":
    main()
