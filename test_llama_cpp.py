from 
from langchain.tools import tool
from langchain_core.messages import HumanMessage

@tool
def get_weather(city: str) -> str:
    """Get the current weather for a city."""
    return f"The weather in {city} is sunny and 72°F."

# Load llama.cpp model (use --chat-template for tool calling models)
llm = ChatLlamaCpp(
    model_path="D:/AI/llm-models/NousResearch/Hermes-2-Pro-Llama-3-8B-GGUF/Hermes-2-Pro-Llama-3-8B-Q4_K_M.gguf",  # Tool-aware model
    temperature=0,
    n_gpu_layers=-1,  # Offload to GPU if available
    verbose=True
)

# Bind tools - model generates tool calls in JSON format
llm_with_tools = llm.bind_tools([get_weather])

# Invoke with message
response = llm_with_tools.invoke([HumanMessage(content="What's the weather in SF?")])
print(response.tool_calls)  # List of tool calls