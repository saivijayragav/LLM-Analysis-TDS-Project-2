from langgraph.graph import StateGraph, END, START
from shared_store import url_time
import time
from langchain_core.rate_limiters import InMemoryRateLimiter
from langgraph.prebuilt import ToolNode
from tools import (
    get_rendered_html, download_file, post_request,
    run_code, add_dependencies, ocr_image_tool, transcribe_audio, encode_image_to_base64
)
from typing import TypedDict, Annotated, List
from langchain_core.messages import trim_messages
from langchain.chat_models import init_chat_model
from langgraph.graph.message import add_messages
import os
from dotenv import load_dotenv
load_dotenv()

EMAIL = os.getenv("EMAIL")
SECRET = os.getenv("SECRET")

RECURSION_LIMIT = 5000
MAX_TOKENS = 180000


# -------------------------------------------------
# STATE
# -------------------------------------------------
class AgentState(TypedDict):
    messages: Annotated[List, add_messages]


TOOLS = [
    run_code, get_rendered_html, download_file,
    post_request, add_dependencies, ocr_image_tool, transcribe_audio, encode_image_to_base64
]


# -------------------------------------------------
# LLM INIT (NO SYSTEM PROMPT HERE)
# -------------------------------------------------
rate_limiter = InMemoryRateLimiter(
    requests_per_second=7 / 60,
    check_every_n_seconds=1,
    max_bucket_size=7
)

llm = init_chat_model(
    model_provider="google_genai",
    model="gemini-2.5-flash",
    rate_limiter=rate_limiter
).bind_tools(TOOLS)



# -------------------------------------------------
# SYSTEM PROMPT (WILL BE INSERTED ONLY ONCE)
# -------------------------------------------------
SYSTEM_PROMPT = f"""
You are an autonomous quiz-solving agent.

Your job is to:
1. Load each quiz page from the given URL.
2. Extract instructions, parameters, and submit endpoint.
3. Solve tasks exactly.
4. Submit answers ONLY to the correct endpoint.
5. Follow new URLs until none remain, then output END.

Rules:
- For base64 generation of an image NEVER use your own code, always use the "encode_image_to_base64" tool that's provided
- Never hallucinate URLs or fields.
- Never shorten endpoints.
- Always inspect server response.
- Never stop early.
- Use tools for HTML, downloading, rendering, OCR, or running code.
- Include:
    email = {EMAIL}
    secret = {SECRET}
"""


# -------------------------------------------------
# AGENT NODE
# -------------------------------------------------
def agent_node(state: AgentState):
    # time-handling
    cur_time = time.time()
    cur_url = os.getenv("url")
    prev_time = url_time[cur_url]
    offset = os.getenv("offset")
    if prev_time is not None:
        prev_time = float(prev_time)
        diff = cur_time - prev_time

        if diff >= 180 or (offset != "0" and (cur_time - float(offset)) > 90):
            print("Timeout exceeded — instructing LLM to purposely submit wrong answer.", diff, "Offset=", offset)

            fail_instruction = """
            You have exceeded the time limit for this task (over 130 seconds).
            Immediately call the `post_request` tool and submit a WRONG answer for the CURRENT quiz.
            """

            # LLM will figure out the right endpoint + JSON structure itself
            result = llm.invoke([
                {"role": "user", "content": fail_instruction}
            ])
            return {"messages": [result]}

    trimmed_messages = trim_messages(
        messages=state["messages"],
        max_tokens=MAX_TOKENS,
        strategy="last",
        include_system=True,
        start_on="human",
        token_counter=llm,  # Use the LLM to count actual tokens, not just list length
    )
    
    result = llm.invoke(trimmed_messages)

    return {"messages": [result]}

# -------------------------------------------------
# ROUTE LOGIC (YOURS WITH MINOR SAFETY IMPROVES)
# -------------------------------------------------
def route(state):
    last = state["messages"][-1]
    # print("=== ROUTE DEBUG: last message type ===")

    tool_calls = getattr(last, "tool_calls", None)

    if tool_calls:
        print("Route → tools")
        return "tools"

    content = getattr(last, "content", None)

    if isinstance(content, str) and content.strip() == "END":
        return END

    if isinstance(content, list) and len(content) and isinstance(content[0], dict):
        if content[0].get("text", "").strip() == "END":
            return END

    print("Route → agent")
    return "agent"



# -------------------------------------------------
# GRAPH
# -------------------------------------------------
graph = StateGraph(AgentState)

graph.add_node("tools", ToolNode(TOOLS))

graph.add_edge(START, "agent")
graph.add_edge("tools", "agent")
graph.add_conditional_edges("agent", route)
robust_retry = {
    "initial_interval": 1,
    "backoff_factor": 2,
    "max_interval": 60,
    "max_attempts": 10
}

graph.add_node("agent", agent_node, retry=robust_retry)
app = graph.compile()



# -------------------------------------------------
# RUNNER
# -------------------------------------------------
def run_agent(url: str):
    # system message is seeded ONCE here
    initial_messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": url}
    ]

    app.invoke(
        {"messages": initial_messages},
        config={"recursion_limit": RECURSION_LIMIT}
    )

    print("Tasks completed successfully!")
