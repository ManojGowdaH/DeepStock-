# Frontend

This service serves the static dashboard UI for the DeepStock AI project.

## Production deployment

This frontend is a static site. Deploy the repository root or the `frontend/` directory to Vercel using the settings below.

### Vercel settings

- Root Directory: `frontend`
- Framework Preset: `Other`
- Build Command: `echo "No build step required for this static frontend."`
- Output Directory: `.`
- Install Command: leave empty

The frontend communicates with:

```text
https://deepstock-thtj.onrender.com
```

## Docker deploy

```powershell
docker build -t deepstock-frontend .
docker run --rm -p 3000:3000 deepstock-frontend
```
