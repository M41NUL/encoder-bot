# encoder.py — ENCODER BOT Encoding Engine

import base64
import marshal
import zlib
import ast
import types
import textwrap
from datetime import datetime
from config import BOT_NAME, DEVELOPER, GITHUB, EMAIL


# ─── HEADER GENERATOR ────────────────────────────────────────────────────────

def build_header(method: str) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return f'''# ============================================
# 🔐 TOOL NAME: {BOT_NAME}
# 👨‍💻 Developer: {DEVELOPER}
# 🌐 GitHub: {GITHUB}
# 📩 Email: {EMAIL}
#
# ⚙️ Encoding Tool Information
# - Tool Name: {BOT_NAME}
# - Encoding Method: {method}
# - Created Time: {now}
#
# 📜 License: MIT
# © Copyright (c) MAINUL - X
# ============================================
'''


# ─── SYNTAX VALIDATOR ────────────────────────────────────────────────────────

def validate_python(code: str) -> tuple[bool, str]:
    try:
        ast.parse(code)
        return True, ""
    except SyntaxError as e:
        return False, f"SyntaxError at line {e.lineno}: {e.msg}"
    except Exception as e:
        return False, str(e)


# ─── BASE64 ENCODING ─────────────────────────────────────────────────────────

def encode_base64(source_code: str) -> tuple[bool, str]:
    """
    Wraps source in a base64 + exec() loader.
    The produced script is standalone and self-executing.
    """
    try:
        valid, err = validate_python(source_code)
        if not valid:
            return False, f"Invalid Python code: {err}"

        encoded = base64.b64encode(source_code.encode("utf-8")).decode("ascii")
        wrapped = "\n    ".join(textwrap.wrap(encoded, 60))

        payload = textwrap.dedent(f"""\
            {build_header("Base64")}
            import base64 as _b64

            _code = (
                "{wrapped}"
            )
            exec(_b64.b64decode(_code).decode("utf-8"))
        """)

        return True, payload

    except Exception as e:
        return False, f"Base64 encoding failed: {e}"


# ─── MARSHAL ENCODING ────────────────────────────────────────────────────────

def encode_marshal(source_code: str) -> tuple[bool, str]:
    """
    Compiles source to bytecode, serialises with marshal, then base64-wraps
    the binary so the output is a printable .py file.
    """
    try:
        valid, err = validate_python(source_code)
        if not valid:
            return False, f"Invalid Python code: {err}"

        code_obj = compile(source_code, "<encoded>", "exec")
        marshalled = marshal.dumps(code_obj)
        encoded = base64.b64encode(marshalled).decode("ascii")
        wrapped = "\n    ".join(textwrap.wrap(encoded, 60))

        payload = textwrap.dedent(f"""\
            {build_header("Marshal")}
            import marshal as _m, base64 as _b64

            _data = (
                "{wrapped}"
            )
            exec(_m.loads(_b64.b64decode(_data)))
        """)

        return True, payload

    except Exception as e:
        return False, f"Marshal encoding failed: {e}"


# ─── ULTRA ENCODING ──────────────────────────────────────────────────────────

def encode_ultra(source_code: str) -> tuple[bool, str]:
    """
    Three-layer protection:
      1. compile() → Python bytecode (code object)
      2. marshal.dumps() → binary serialisation
      3. zlib.compress() → compression
      4. base64.b64encode() → printable ASCII

    Loader reconstructs in reverse: b64decode → decompress → marshal.loads → exec
    """
    try:
        valid, err = validate_python(source_code)
        if not valid:
            return False, f"Invalid Python code: {err}"

        # Layer 1 — compile to bytecode
        code_obj = compile(source_code, "<ultra_encoded>", "exec")

        # Layer 2 — marshal the code object
        marshalled = marshal.dumps(code_obj)

        # Layer 3 — compress
        compressed = zlib.compress(marshalled, level=9)

        # Layer 4 — base64 encode
        encoded = base64.b64encode(compressed).decode("ascii")
        wrapped = "\n    ".join(textwrap.wrap(encoded, 60))

        payload = textwrap.dedent(f"""\
            {build_header("Ultra (Base64 + zlib + Marshal)")}
            import marshal as _m, zlib as _z, base64 as _b64

            _ultra = (
                "{wrapped}"
            )
            exec(_m.loads(_z.decompress(_b64.b64decode(_ultra))))
        """)

        return True, payload

    except Exception as e:
        return False, f"Ultra encoding failed: {e}"


# ─── DISPATCHER ──────────────────────────────────────────────────────────────

ENCODERS = {
    "base64": encode_base64,
    "marshal": encode_marshal,
    "ultra": encode_ultra,
}

METHOD_LABELS = {
    "base64": "🔐 Base64",
    "marshal": "⚙️ Marshal",
    "ultra": "🔥 Ultra",
}


def encode(source_code: str, method: str) -> tuple[bool, str]:
    """
    Unified entry point.
    Returns (success: bool, result: str)
    result is the encoded code on success, or an error message on failure.
    """
    fn = ENCODERS.get(method.lower())
    if fn is None:
        return False, f"Unknown method '{method}'. Choose: base64, marshal, ultra"
    return fn(source_code)


def get_method_label(method: str) -> str:
    return METHOD_LABELS.get(method.lower(), method.upper())
