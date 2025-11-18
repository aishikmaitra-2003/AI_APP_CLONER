# React + Flask Generated App\n

Backend:  Create a Python virtual environment and activate it.

Install dependencies: `pip install -r requirements.txt`

Run backend: `python server.py`

The backend exposes `/api/data` and `/api/<path>` endpoints, and serves the frontend build from `frontend/dist` if present.

Frontend\n1. `cd frontend`\n2. `npm install`\n3. `npm run dev` (for development) or `npm run build` then copy `dist` to `frontend/dist` for the backend to serve the built app.\n
