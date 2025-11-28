from langchain_core.tools import tool
from shared_store import BASE64_STORE, url_time
import time
import os
import requests
import json
from collections import defaultdict
from typing import Any, Dict, Optional

cache = defaultdict(int)
retry_limit = 4
@tool
def post_request(url: str, payload: Dict[str, Any], headers: Optional[Dict[str, str]] = None) -> Any:
    """
    Send an HTTP POST request to the given URL with the provided payload.

    This function is designed for LangGraph applications, where it can be wrapped
    as a Tool or used inside a Runnable to call external APIs, webhooks, or backend
    services during graph execution.
    REMEMBER: This a blocking function so it may take a while to return. Wait for the response.
    Args:
        url (str): The endpoint to send the POST request to.
        payload (Dict[str, Any]): The JSON-serializable request body.
        headers (Optional[Dict[str, str]]): Optional HTTP headers to include
            in the request. If omitted, a default JSON header is applied.

    Returns:
        Any: The response body. If the server returns JSON, a parsed dict is
        returned. Otherwise, the raw text response is returned.

    Raises:
        requests.HTTPError: If the server responds with an unsuccessful status.
        requests.RequestException: For network-related errors.
    """
    # Handling if the answer is a BASE64
    ans = payload.get("answer")

    if isinstance(ans, str) and ans.startswith("BASE64_KEY:"):
        key = ans.split(":", 1)[1]
        payload["answer"] = BASE64_STORE[key]
    headers = headers or {"Content-Type": "application/json"}
    try:
        cur_url = os.getenv("url")
        cache[cur_url] += 1
        sending = payload
        if isinstance(payload.get("answer"), str):
            sending = {
                "answer": payload.get("answer", "")[:100],
                "email": payload.get("email", ""),
                "url": payload.get("url", "")
            }
        print(f"\nSending Answer \n{json.dumps(sending, indent=4)}\n to url: {url}")
        response = requests.post(url, json=payload, headers=headers)

        # Raise on 4xx/5xx
        response.raise_for_status()

        # Try to return JSON, fallback to raw text
        data = response.json()
        print("Got the response: \n", json.dumps(data, indent=4), '\n')
        if "message" in data:
            del data["message"]

        delay = data.get("delay", 0)
        delay = delay if isinstance(delay, (int, float)) else 0

        next_url = data.get("url") 
        if next_url not in url_time:
            url_time[next_url] = time.time()

        correct = data.get("correct")
        if not correct:
            cur_time = time.time()
            prev = url_time[next_url]
            if cache[cur_url] >= retry_limit or delay >= 180 or (prev != "0" and (cur_time - float(prev)) > 90): # Shouldn't retry
                data = {"url": data.get("url", "")} 
            else: # Retry
                os.environ["offset"] = str(url_time[next_url])
                data["url"] = cur_url
                data["message"] = "Retry Again!" 
        print("Formatted: '\n", json.dumps(data, indent=4), '\n')
        forward_url = data.get("url", "")
        os.environ["url"] = forward_url 
        if forward_url == next_url:
            os.environ["offset"] = "0"

        return data
    except requests.HTTPError as e:
        # Extract server’s error response
        err_resp = e.response

        try:
            err_data = err_resp.json()
        except ValueError:
            err_data = err_resp.text

        print("HTTP Error Response:\n", err_data)
        return err_data

    except Exception as e:
        print("Unexpected error:", e)
        return str(e)