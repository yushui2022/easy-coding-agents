from tools.base import registry
from typing import Any
import asyncio

@registry.register(
    name="ask_user",
    description="Ask the user a question and get their input. Useful for clarification or confirmation.",
    parameters={
        "properties": {
            "question": {"type": "string", "description": "The question to ask the user"}
        },
        "required": ["question"]
    }
)
async def ask_user(question: str, context: Any) -> str:
    """
    Pause execution and request input from the user.
    Requires an 'input_func' to be present in the context.
    """
    if not hasattr(context, 'input_func') or not context.input_func:
        return "Error: Interactive input is not supported in this environment (missing input_func)."
    
    try:
        # Call the injected async input function
        # This function should handle the UI interaction (e.g. prompt_toolkit)
        user_response = await context.input_func(question)
        return user_response
    except Exception as e:
        return f"Error getting user input: {str(e)}"

@registry.register(
    name="ask_selection",
    description="Ask the user to select from a list of options. Useful for presenting choices.",
    parameters={
        "properties": {
            "question": {"type": "string", "description": "The question to ask the user"},
            "options": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of options for the user to choose from"
            }
        },
        "required": ["question", "options"]
    }
)
async def ask_selection(question: str, options: list[str], context: Any) -> str:
    """
    Pause execution and request selection from the user.
    Requires a 'selection_func' to be present in the context.
    """
    if not hasattr(context, 'selection_func') or not context.selection_func:
        # Fallback to text input if selection_func is not available
        options_str = "\n".join([f"{i+1}. {opt}" for i, opt in enumerate(options)])
        full_question = f"{question}\nOptions:\n{options_str}\n(Please type your choice)"
        # Assuming ask_user is available in the same scope
        return await ask_user(full_question, context)

    try:
        user_response = await context.selection_func(question, options)
        
        # Smart handling for "Self choice" / "自己选择"
        # If user selected this, we should prompt for the actual custom input
        if user_response in ["Self choice", "自己选择", "Custom Input"]:
            # We use the existing ask_user logic to get free text input
            custom_input = await ask_user(f"You selected '{user_response}'. Please enter your custom instruction:", context)
            return f"User selected '{user_response}' and provided input: {custom_input}"
            
        return user_response
    except Exception as e:
        return f"Error getting user selection: {str(e)}"

