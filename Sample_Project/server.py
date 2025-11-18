import os
from flask import Flask, send_from_directory, jsonify, request
from flask_cors import CORS

app = Flask(__name__, static_folder='frontend/dist')
CORS(app)

@app.route('/api/data', methods=['GET'])
def api_data():
    sample = {'message': 'Hello from Flask backend', 'ok': True}
    return jsonify(sample)

@app.route('/api/<path:subpath>', methods=['GET','POST'])
def api_proxy(subpath):
    # Simple example endpoint: echoes path and query/body for easy testing.
    info = {
        'requested_path': subpath,
        'method': request.method,
        'args': request.args.to_dict(),
    }
    try:
        info['json'] = request.get_json(silent=True)
    except Exception:
        info['json'] = None
    return jsonify(info)

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_frontend(path):
    # Serve static files from frontend/dist when available; otherwise informative message
    dist_dir = os.path.join(os.getcwd(), 'frontend', 'dist')
    
    if path != '' and os.path.exists(os.path.join(dist_dir, path)):
        return send_from_directory(dist_dir, path)
    index_path = os.path.join(dist_dir, 'index.html')
    if os.path.exists(index_path):
        return send_from_directory(dist_dir, 'index.html')
    return jsonify({'message': 'Frontend build not found. Run `cd frontend && npm install && npm run build`.'}), 200

if __name__ == '__main__':
    # Use 0.0.0.0 for easier local testing in containers/VMs if needed
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=True)
