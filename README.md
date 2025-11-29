# Web-Burp

A browser-based intercepting proxy for HTTP/HTTPS traffic, similar to Burp Suite.

## Quick Start

### Build and run with Docker:

```bash
docker-compose up --build
```

### Access the application:

Open your browser to `http://localhost:5000`

## Development

### Local development without Docker:

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

## Features (Planned)

- ✅ Flask-based web UI
- ✅ Docker containerization
- ⏳ HTTP/HTTPS proxy server
- ⏳ Request/response interception
- ⏳ Traffic history logging
- ⏳ Request repeater
- ⏳ MITM certificate generation
- ⏳ Traffic modification
- ⏳ Plugin system
- ⏳ Automated scanning

## Architecture

```
web-burp/
├── app.py              # Flask application
├── templates/          # HTML templates
├── static/             # CSS, JS
├── data/              # Captured traffic storage
├── Dockerfile         # Container definition
└── docker-compose.yml # Orchestration
```

## License

For authorized testing and educational purposes only.
