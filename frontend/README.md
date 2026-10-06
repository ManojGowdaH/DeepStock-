# Frontend

This service serves the static dashboard UI for the DeepStock AI project.

## Run locally

```powershell
cd "D:\Deep Learning\deepstock-ai\frontend"
python -m http.server 3000 --bind 127.0.0.1
```

## Docker deploy

```powershell
docker build -t deepstock-frontend .
docker run --rm -p 3000:3000 deepstock-frontend
```

## Open in browser

```text
http://localhost:3000
```
