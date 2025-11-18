# generator.py
import os
import json
import zipfile
from dotenv import load_dotenv
from datetime import datetime
import re

# Try importing ollama, but don't crash if it's not installed / reachable.
try:
    import ollama
    _OLLAMA_AVAILABLE = True
except Exception:
    _OLLAMA_AVAILABLE = False

load_dotenv()

PROPRIETARY_MARKERS = [
    "instagram", "facebook", "whatsapp", "uber", "airbnb",
    "tiktok", "twitter", "snapchat", "x.com"
]


def likely_proprietary_spec(ux_spec):
    domain = ux_spec.get("domain", "") or ""
    if any(x in domain.lower() for x in PROPRIETARY_MARKERS):
        return True

    for p in ux_spec.get("pages", []):
        title = (p.get("title") or "").lower()
        if any(x in title for x in PROPRIETARY_MARKERS):
            return True

    return False


# ----------------------------------------------------------
# SANITIZER — REMOVES MARKDOWN, TRIPLE QUOTES, EXTRACTS JSON
# ----------------------------------------------------------

def sanitize_llm_output(text):
    """
    Strip common surrounding markdown fences and extract the first
    balanced JSON object found in text. Raises RuntimeError if none found.
    
    This version is more aggressive in handling conversational fluff and fences.
    """
    if not isinstance(text, str):
        raise RuntimeError("LLM returned non-string content")

    # 1. Remove fenced code blocks ```...``` and try to capture content inside 'json' block
    # We use non-greedy matching `*?`
    fenced_content = re.search(r"```json\s*([\s\S]*?)```|```([\s\S]*?)```", text, flags=re.IGNORECASE)
    
    if fenced_content:
        # Prioritize content captured inside a json fence (group 1), otherwise use content from any fence (group 2)
        text_to_parse = (fenced_content.group(1) or fenced_content.group(2) or "").strip()
    else:
        # No fences found, use original text
        text_to_parse = text.strip()


    # 2. If the text is still tiny or just contained backticks (meaning the LLM failed), clean the original text.
    if len(text_to_parse) < 5 and len(text) > 10:
        text_to_parse = text.replace('```', '').strip()

    # 3. Replace triple double-quotes (""" ) with single double-quote to avoid nested string problems
    text_to_parse = text_to_parse.replace('"""', '"')

    # 4. Extract the first balanced JSON object.
    start = text_to_parse.find("{")
    if start == -1:
        raise RuntimeError("No JSON object found in LLM output:\n" + text_to_parse[:1000])

    # Find the start of the JSON object, trimming any leading commentary/fluff
    text_to_parse = text_to_parse[start:]
    
    # Naive balancing scan from the start of the object {
    depth = 0
    end_index = -1
    for i in range(len(text_to_parse)):
        ch = text_to_parse[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end_index = i
                break
    if end_index == -1:
        raise RuntimeError("Could not find end of JSON object in LLM output (unbalanced braces):\n" + text_to_parse[:1000])

    json_text = text_to_parse[:end_index+1]
    return json_text


# ----------------------------------------------------------
# PROMPT WITHOUT NESTED F-STRINGS (SAFE)
# ----------------------------------------------------------

def build_prompt_from_spec(ux_spec, app_name="GeneratedApp"):
    # Keep the ux_spec string truncated to a safe length to avoid model context overflow
    ux_json = json.dumps(ux_spec, indent=2)[:6000]

    template = (
        "You MUST output ONLY valid JSON.\n"
        "NO markdown. NO ``` blocks. NO commentary. NO triple quotes.\n\n"
        "RULES:\n"
        "- Output a single JSON object with top-level key \"files\".\n"
        "- Each file value MUST be a JSON string containing \\n newlines.\n"
        "- The content of server.py must fully support serving the React build.\n"
        "- The frontend/index.html MUST NOT contain a reference to /src/main.jsx, as Vite injects the production build script automatically.\n"
        "- NEVER use markdown formatting.\n"
        "- NEVER wrap code in backticks.\n"
        "- NEVER output extra explanation outside JSON.\n\n"
        "GENERATE THIS PROJECT STRUCTURE:\n\n"
        "1. Backend (Flask):\n"
        "   - server.py:\n"
        "        * serves API at /api/*\n"
        "        * React build served from /frontend/dist using a custom route (static_folder=None)\n"
        "        * fallback route returns index.html\n\n"
        "2. requirements.txt:\n"
        "        flask\n"
        "        flask_cors\n\n"
        "3. React Frontend (Vite + React):\n"
        "   folder: frontend/\n\n"
        "   MUST INCLUDE:\n"
        "   - frontend/package.json\n"
        "   - frontend/vite.config.js\n"
        "   - frontend/index.html\n"
        "   - frontend/src/main.jsx\n"
        "   - frontend/src/App.jsx\n"
        "   - frontend/src/components/AutoLayout.jsx\n\n"
        "   App.jsx should fetch /api/data and render components based on the UX SPEC.\n\n"
        "4. README.md: instructions for backend + frontend setup\n\n"
        "UX SPEC FOR CONTEXT (Use this to design the front-end components and layout in App.jsx):\n"
        + ux_json
        + "\n\n"
        "OUTPUT EXACTLY AS JSON:\n"
        "{\n"
        "  \"files\": {\n"
        "    \"server.py\": \"...\",\n"
        "    \"requirements.txt\": \"...\",\n"
        "    \"frontend/package.json\": \"...\",\n"
        "    \"frontend/vite.config.js\": \"...\",\n"
        "    \"frontend/index.html\": \"...\",\n"
        "    \"frontend/src/main.jsx\": \"...\",\n"
        "    \"frontend/src/App.jsx\": \"...\",\n"
        "    \"frontend/src/components/AutoLayout.jsx\": \"...\",\n"
        "    \"README.md\": \"...\"\n"
        "  }\n"
        "}\n"
    )

    return template


# ----------------------------------------------------------
# OLLAMA CALL (optional) WITH SAFE ERROR HANDLING
# ----------------------------------------------------------

def call_ollama_for_files(prompt, model="llama3.2:3b", max_tokens=4000):
    """
    Call ollama.chat and return the parsed 'files' mapping.
    If Ollama isn't available or fails, raise RuntimeError so the caller can fallback.
    """
    if not _OLLAMA_AVAILABLE:
        raise RuntimeError("Ollama library not available in this environment.")

    # NOTE: Ensure this model is available on your local Ollama server.
    try:
        response = ollama.chat(
            model=model,
            messages=[
                {"role": "system", "content": "Return ONLY valid JSON containing a 'files' mapping."},
                {"role": "user", "content": prompt}
            ],
            options={"num_predict": max_tokens}
        )

        raw = response.get("message", {}).get("content", "")
        if not raw:
            raise RuntimeError("Ollama returned empty response")

        clean = sanitize_llm_output(raw)
        parsed = json.loads(clean)

        if "files" not in parsed or not isinstance(parsed["files"], dict):
            raise RuntimeError("'files' key missing or invalid in model output")

        return parsed["files"]

    except Exception as e:
        # Give a clear error message back to caller
        raise RuntimeError(f"Ollama call failed: {e}")


# ----------------------------------------------------------
# ZIP BUILDER
# ----------------------------------------------------------

def make_zip(files_map, out_path):
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        for path, content in files_map.items():
            # ensure directories exist in zip entries
            if not isinstance(content, (str, bytes)):
                content = json.dumps(content, indent=2)
            # normalize path separators
            arcname = path.replace("\\", "/")
            z.writestr(arcname, content)
    print("Wrote", out_path)


# ----------------------------------------------------------
# DEFAULT FAILSAFE FILES (if model not available or fails)
# ----------------------------------------------------------

DEFAULT_FILES = {
    "server.py": (
        "import os\n"
        "from flask import Flask, send_from_directory, jsonify, request\n"
        "from flask_cors import CORS\n\n"
        "# Set static_folder=None, relying solely on serve_frontend for asset handling.\n"
        "app = Flask(__name__, static_folder=None)\n"
        "CORS(app)\n\n"
        "@app.route('/api/data', methods=['GET'])\n"
        "def api_data():\n"
        "    sample = {'message': 'Hello from Flask backend', 'ok': True}\n"
        "    return jsonify(sample)\n\n"
        "@app.route('/api/<path:subpath>', methods=['GET','POST'])\n"
        "def api_proxy(subpath):\n"
        "    # Simple example endpoint: echoes path and query/body for easy testing.\n"
        "    info = {\n"
        "        'requested_path': subpath,\n"
        "        'method': request.method,\n"
        "        'args': request.args.to_dict(),\n"
        "    }\n"
        "    try:\n"
        "        info['json'] = request.get_json(silent=True)\n"
        "    except Exception:\n"
        "        info['json'] = None\n"
        "    return jsonify(info)\n\n"
        "@app.route('/', defaults={'path': ''})\n"
        "@app.route('/<path:path>')\n"
        "def serve_frontend(path):\n"
        "    ""\n"
        "    Serves the built frontend assets (JS/CSS/Index.html) from the frontend/dist directory.\n"
        "    This acts as the Single Page Application (SPA) catch-all.\n"
        "    ""\n"
        "    # Define the directory where Vite places its production output\n"
        "    dist_dir = os.path.join(os.getcwd(), 'frontend', 'dist')\n"
        "    \n"
        "    # Construct the full path to the requested file (e.g., assets/index-xxx.js)\n"
        "    requested_file = os.path.join(dist_dir, path)\n"
        "\n"
        "    # 1. If a specific asset file is requested and exists (handles assets/foo.js)\n"
        "    if path != '' and os.path.exists(requested_file):\n"
        "        # Serve the file by using its directory and filename\n"
        "        directory = os.path.dirname(requested_file)\n"
        "        filename = os.path.basename(requested_file)\n"
        "        return send_from_directory(directory, filename)\n"
        "\n"
        "    # 2. If path is root or asset not found, serve the main index.html (SPA fallback)\n"
        "    index_path = os.path.join(dist_dir, 'index.html')\n"
        "    if os.path.exists(index_path):\n"
        "        return send_from_directory(dist_dir, 'index.html')\n"
        "        \n"
        "    # 3. Fallback message if the build hasn't been run\n"
        "    return jsonify({'message': 'Frontend build not found. Run `cd frontend && npm install && npm run build`.'}), 200\n\n"
        "if __name__ == '__main__':\n"
        "    # Use 0.0.0.0 for easier local testing in containers/VMs if needed\n"
        "    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=True)\n"
    ),
    "requirements.txt": "flask\nflask_cors\n",
    "frontend/package.json": json.dumps({
        "name": "react-app",
        "version": "1.0.0",
        "private": True,
        "scripts": {"dev": "vite", "build": "vite build", "preview": "vite preview"},
        "dependencies": {"react": "^18.0.0", "react-dom": "^18.0.0"},
        "devDependencies": {"vite": "^5.0.0", "@vitejs/plugin-react": "^4.0.0"}
    }, indent=2),
    "frontend/vite.config.js": (
        "import { defineConfig } from 'vite';\n"
        "import react from '@vitejs/plugin-react';\n"
        "export default defineConfig({ plugins: [react()] });\n"
    ),
    # -------------------------------------------------------------
    # CRITICAL: index.html MUST be clean for production build.
    # -------------------------------------------------------------
    "frontend/index.html": (
        "<!doctype html>\n"
        "<html>\n"
        "  <head>\n"
        "    <meta charset=\"utf-8\" />\n"
        "    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />\n"
        "    <title>Generated React App</title>\n"
        "  </head>\n"
        "  <body>\n"
        "    <div id=\"root\"></div>\n"
        "    <!-- Vite will inject the production script reference here during 'npm run build' -->\n"
        "  </body>\n"
        "</html>\n"
    ),
    "frontend/src/main.jsx": (
        "import React from 'react';\n"
        "import { createRoot } from 'react-dom/client';\n"
        "import App from './App.jsx';\n\n"
        "createRoot(document.getElementById('root')).render(\n"
        "  <React.StrictMode>\n"
        "    <App />\n"
        "  </React.StrictMode>\n"
        ");\n"
    ),
    "frontend/src/App.jsx": (
        "import React, {useEffect, useState} from 'react';\n"
        "import AutoLayout from './components/AutoLayout.jsx';\n\n"
        "export default function App(){\n"
        "  const [data, setData] = useState(null);\n"
        "  useEffect(()=>{\n"
        "    fetch('/api/data')\n"
        "      .then(r=>r.json())\n"
        "      .then(setData)\n"
        "      .catch(e=>setData({error: String(e)}));\n"
        "  }, []);\n"
        "  return (\n"
        "    <AutoLayout>\n"
        "      <h1>Generated React Frontend</h1>\n"
        "      <p>This is a functional fallback application. If the LLM generation was successful, this content should be replaced by the design extracted from the UX spec.</p>\n"
        "      <pre>{JSON.stringify(data, null, 2)}</pre>\n"
        "    </AutoLayout>\n"
        "  );\n"
        "}\n"
    ),
    "frontend/src/components/AutoLayout.jsx": (
        "import React from 'react';\n"
        "export default function AutoLayout({children}){\n"
        "  return (\n"
        "    <div style={{fontFamily:'Arial, sans-serif', padding:20}}>\n"
        "      {children}\n"
        "    </div>\n"
        "  );\n"
        "}\n"
    ),
    "README.md": (
        "# React + Flask Generated App\\n\\n"
        "## Backend\\n"
        "1. Create a Python virtual environment and activate it.\\n"
        "2. Install dependencies: `pip install -r requirements.txt`\\n"
        "3. Run backend: `python server.py`\\n\\n"
        "The backend exposes `/api/data` and `/api/<path>` endpoints, and serves the frontend build from `frontend/dist` if present.\\n\\n"
        "## Frontend\\n"
        "1. `cd frontend`\\n"
        "2. `npm install`\\n"
        "3. `npm run build` to create the production files.\\n"
        "4. Then run the backend to serve the built app.\\n"
    )
}


# ----------------------------------------------------------
# MAIN GENERATOR
# ----------------------------------------------------------

def generate_scaffold(ux_spec, app_name="ReactApp", model="llama3.2:3b", out_zip=None):
    """
    Generate a scaffold zip. Attempts to call Ollama to produce
    a richer set of files; on failure falls back to DEFAULT_FILES.
    """
    if likely_proprietary_spec(ux_spec):
        raise RuntimeError("Proprietary app detected — cannot clone or reproduce a verbatim UI.")

    prompt = build_prompt_from_spec(ux_spec, app_name)

    files = {}
    # Attempt to get model-generated files
    try:
        files = call_ollama_for_files(prompt, model=model) if _OLLAMA_AVAILABLE else {}
    except Exception as e:
        # Model failed — log and fall back to defaults
        print("Model generation failed:", e)
        files = {}

    # Merge with safe defaults to ensure required files exist and have proper server.py
    # Model files (if any) win; otherwise defaults are used.
    final_files = DEFAULT_FILES.copy()
    # overlay model-provided files (string values expected)
    for k, v in files.items():
        if isinstance(v, (dict, list)):
            # convert to pretty JSON
            final_files[k] = json.dumps(v, indent=2)
        else:
            final_files[k] = str(v)

    # Ensure server.py is a reasonable full file (not a 1-liner) — if model provided server.py but it's tiny, replace with default
    sp = final_files.get("server.py", "")
    if len(sp.strip()) < 50 or "\n" not in sp:
        final_files["server.py"] = DEFAULT_FILES["server.py"]

    # Ensure requirements.txt exists
    if "requirements.txt" not in final_files or not final_files["requirements.txt"].strip():
        final_files["requirements.txt"] = DEFAULT_FILES["requirements.txt"]

    # Ensure frontend minimal files exist
    needed_frontend = [
        "frontend/package.json",
        "frontend/vite.config.js",
        "frontend/index.html",
        "frontend/src/main.jsx",
        "frontend/src/App.jsx",
        "frontend/src/components/AutoLayout.jsx",
    ]
    for fn in needed_frontend:
        if fn not in final_files:
            final_files[fn] = DEFAULT_FILES.get(fn, "")

    # Create output zip name if not supplied
    if not out_zip:
        safe_name = app_name.replace(" ", "_")
        out_zip = f"{safe_name}_scaffold_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.zip"

    make_zip(final_files, out_zip)
    return out_zip


# ----------------------------------------------------------
# CLI ENTRYPOINT
# ----------------------------------------------------------

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate scaffold zip from UX spec JSON")
    parser.add_argument("ux_spec_json", help="Path to ux_spec.json produced by extractor")
    parser.add_argument("--app_name", default="GeneratedReactApp")
    parser.add_argument("--model", default="llama3.2:3b")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    spec_path = args.ux_spec_json
    if not os.path.exists(spec_path):
        raise SystemExit("Spec file not found: " + spec_path)

    with open(spec_path, "r", encoding="utf-8") as fh:
        ux_spec = json.load(fh)

    zip_path = generate_scaffold(ux_spec, app_name=args.app_name, model=args.model, out_zip=args.out)
    print("Scaffold generated:", zip_path)