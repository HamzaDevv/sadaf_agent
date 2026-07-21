"""
tools/calculator.py — Sadaf Jarvis Calculator Tool

Safe math expression evaluator using Python's ast module.
Handles: basic arithmetic, percentages, powers, and common math functions.
"""
import ast
import math
import re
import operator


# Allowed operations (whitelist — no exec/eval of arbitrary code)
SAFE_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

SAFE_FUNCTIONS = {
    "sqrt": math.sqrt,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "log": math.log10,
    "ln": math.log,
    "abs": abs,
    "round": round,
    "floor": math.floor,
    "ceil": math.ceil,
    "pi": math.pi,
    "e": math.e,
}


def _safe_eval(node):
    """Recursively evaluate an AST node with only safe operations."""
    if isinstance(node, ast.Constant):
        return node.value
    elif isinstance(node, ast.Name):
        if node.id in SAFE_FUNCTIONS:
            return SAFE_FUNCTIONS[node.id]
        raise ValueError(f"Unknown name: {node.id}")
    elif isinstance(node, ast.BinOp):
        op = SAFE_OPS.get(type(node.op))
        if op is None:
            raise ValueError(f"Unsupported operation: {type(node.op).__name__}")
        return op(_safe_eval(node.left), _safe_eval(node.right))
    elif isinstance(node, ast.UnaryOp):
        op = SAFE_OPS.get(type(node.op))
        if op is None:
            raise ValueError(f"Unsupported unary op")
        return op(_safe_eval(node.operand))
    elif isinstance(node, ast.Call):
        func = _safe_eval(node.func)
        args = [_safe_eval(a) for a in node.args]
        return func(*args)
    else:
        raise ValueError(f"Unsupported node type: {type(node).__name__}")


def _preprocess(expr: str) -> str:
    """Clean and normalize a math expression from natural language."""
    expr = expr.lower().strip()
    # Remove filler words
    for filler in ["what is", "what's", "calculate", "compute", "solve", "equals", "equal", "="]:
        expr = expr.replace(filler, "")
    # Handle percentage: "15% of 200" → "0.15 * 200"
    expr = re.sub(r"(\d+(?:\.\d+)?)\s*%\s*of\s*(\d+(?:\.\d+)?)",
                  lambda m: f"{float(m.group(1)) / 100} * {m.group(2)}", expr)
    expr = re.sub(r"(\d+(?:\.\d+)?)\s*percent\s*of\s*(\d+(?:\.\d+)?)",
                  lambda m: f"{float(m.group(1)) / 100} * {m.group(2)}", expr)
    # Handle "x percent" standalone
    expr = re.sub(r"(\d+(?:\.\d+)?)\s*percent", lambda m: str(float(m.group(1)) / 100), expr)
    # Replace word operators
    expr = expr.replace("times", "*").replace("multiplied by", "*")
    expr = expr.replace("divided by", "/").replace("plus", "+").replace("minus", "-")
    expr = expr.replace("to the power of", "**").replace("squared", "**2").replace("cubed", "**3")
    expr = expr.replace("^", "**")
    return expr.strip()


def _format_result(value: float) -> str:
    """Format result for spoken output."""
    if isinstance(value, float) and value == int(value):
        return str(int(value))
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def calculate(query: str) -> str:
    """Evaluate a math expression and return a spoken-English answer."""
    expr = _preprocess(query)

    if not expr:
        return "I didn't catch a math expression. Try something like 'what is 15 percent of 200'."

    try:
        tree = ast.parse(expr, mode="eval")
        result = _safe_eval(tree.body)
        formatted = _format_result(result)
        return f"That's {formatted}."
    except ZeroDivisionError:
        return "You can't divide by zero, that's undefined."
    except Exception as e:
        return f"I couldn't calculate that. Try rephrasing it as a math expression."
