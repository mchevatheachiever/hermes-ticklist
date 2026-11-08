"""Tool schemas for ticklist — what the model sees."""

ADD = {
    "description": (
        "Add items to a checklist in the Hermes Desktop TickList pane. Use it when the user "
        "gives you a list of things to do, buy, pack or check. Existing items are kept; "
        "duplicates are skipped. Returns the whole list plus a `display` field: copy that "
        "into your reply exactly, in one fenced code block."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "description": "The items to add, one per entry. Plain strings are expected.",
                "items": {"type": "string"},
            },
            "list": {
                "type": "string",
                "description": "Which list to add to. Defaults to 'ticklist'; a new list is created if needed.",
            },
        },
        "required": ["items"],
        "additionalProperties": False,
    },
}

SET = {
    "description": (
        "Tick or untick an item on a checklist. Match the item by its id or by its text "
        "(an exact, case-insensitive match first, then a unique substring). Use this when the "
        "user says something is done, or asks you to untick it. Returns the whole list as JSON "
        "plus a `display` field to copy into your reply."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "item": {"type": "string", "description": "Item id or its text."},
            "done": {"type": "boolean", "description": "true to tick, false to untick."},
            "list": {"type": "string", "description": "Which list. Defaults to the most recent one."},
        },
        "required": ["item", "done"],
        "additionalProperties": False,
    },
}

LIST = {
    "description": (
        "Read a checklist — every item, whether it is ticked, and a done/total count. With no "
        "argument it returns the most recent list. Also returns `lists`: every list's name, "
        "done/total, whether it is pinned, and which one is active — that is how you answer "
        "'what lists do I have' or 'which are pinned'. Returns a `display` field to copy into "
        "your reply so the user sees the list on text-only surfaces."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "list": {"type": "string", "description": "Which list. Omit for the most recent one."}
        },
        "additionalProperties": False,
    },
}

REMOVE = {
    "description": (
        "Delete an item from a checklist entirely (not the same as unticking it). Match by id "
        "or text."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "item": {"type": "string", "description": "Item id or its text."},
            "list": {"type": "string", "description": "Which list. Defaults to the most recent one."},
        },
        "required": ["item"],
        "additionalProperties": False,
    },
}

CLEAR = {
    "description": (
        "Empty a checklist. By default removes everything; with done_only=true it removes only "
        "the ticked items, which is the usual 'clear the finished ones' request."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "list": {"type": "string", "description": "Which list. Defaults to the most recent one."},
            "done_only": {
                "type": "boolean",
                "description": "Remove only ticked items. Default false (removes all).",
            },
        },
        "additionalProperties": False,
    },
}

DELETE_LIST = {
    "description": (
        "Delete an entire checklist and everything on it. This is not `tick_clear`: the "
        "list itself is gone, not just emptied. Use it when the user says to remove, "
        "drop or bin a list. Tell the user how many items went with it."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "list": {"type": "string", "description": "Which list to delete."},
        },
        "required": ["list"],
        "additionalProperties": False,
    },
}
