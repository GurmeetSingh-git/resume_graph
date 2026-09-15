# Resume Tailor Frontend

This directory contains the React and Vite frontend for the Resume Tailor application. It calls the FastAPI backend at `http://localhost:8000`.

## Prerequisites

- Node.js and npm
- Python 3.10 or newer
- A configured backend environment, including the required API keys in a root `.env` file

## Install dependencies

From the repository root, install the Python dependencies:

```powershell
python -m pip install -r requirements.txt
```

Then install the frontend dependencies:

```powershell
cd frontend
npm install
```

## Run the application

Open two terminals from the repository root.

In the first terminal, start the backend:

```powershell
python -m uvicorn api:app --reload --port 8000
```

In the second terminal, start the frontend:

```powershell
cd frontend
npm run dev
```

Open the URL printed by Vite, usually `http://localhost:5173`.

## Frontend commands

Run these commands from `frontend/`:

```powershell
npm run dev       # Start the Vite development server
npm run build     # Create a production build in dist/
npm run preview   # Preview the production build locally
npm run lint      # Run Oxlint
```

## Main files

- `src/App.jsx`: Main resume tailoring workflow and backend requests
- `src/App.css`: Component styles
- `src/index.css`: Global styles
- `vite.config.js`: Vite configuration
