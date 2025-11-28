from shared_store import BASE64_STORE
import os
import base64, uuid
from langchain_core.tools import tool
@tool
def encode_image_to_base64(image_path: str) -> str:
    """
    Encode an image file into a full Base64 string without exposing the binary
    output to the LLM.

    This tool reads an image from the given file path, converts it into a
    Base64-encoded string, and stores the *full* Base64 value in a shared
    in-memory dictionary (BASE64_STORE). Instead of returning the large Base64
    blob—which can overwhelm conversation memory, break routing, or cause LLM
    tool-call loops—the tool returns a lightweight placeholder of the form:

        BASE64_KEY:<uuid>

    The LLM uses this placeholder as the 'answer' during reasoning. Later,
    the post_request tool detects the placeholder and replaces it with the
    original Base64 string from BASE64_STORE before submitting it to the server.

    This design prevents:
    - Extremely large Base64 strings from entering the conversation history
    - Agent freezing or malformed function calls
    - Token overflow crashes
    - Misrouting caused by Base64 being misinterpreted as HTML or a tool call

    Parameters
    ----------
    image_path : str
        The file system path of the image to encode. Can be PNG, JPG, GIF,
        WEBP, or any binary image format.

    Returns
    -------
    str
        A small placeholder token referencing the full Base64 string stored
        in memory, e.g. "BASE64_KEY:4f9d93ea-7e94-4edc-962c-e6f7d358c2a3".
    """
    try:
        image_path = os.path.join("LLMFiles", image_path)
        with open(image_path, "rb") as f:
            raw = f.read()
    
        encoded = base64.b64encode(raw).decode("utf-8")

        key = str(uuid.uuid4())
        BASE64_STORE[key] = encoded

        return f"BASE64_KEY:{key}"
    except Exception as e:
        return f"Error occurred: {e}"