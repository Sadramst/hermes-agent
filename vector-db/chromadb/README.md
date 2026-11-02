# ChromaDB

Hermes Agent talks to the upstream `chromadb/chroma` container. This directory records how that service is wired. The server image is pulled in Docker Compose; it is not rebuilt from this folder.

- Image and port: `vector-db/config/chroma.yaml`
- Compose services: `docker/docker-compose.dev.yml`, `docker/docker-compose.test.yml`, `docker/docker-compose.prod.yml`
- Client: `src/services/chroma.py`
- Data volume mount: `/data` (`persist_path` in the Chroma 1.0.0 image config)
- Shared network: `hermes-net`
- Agent setting: `CHROMA_HOST=chromadb` and `CHROMA_PORT=8000`
- Listen port inside the container: `8000` (`vector-db/config/chroma.yaml`)
- Host publish: development `8000`. Production does not publish Chroma.
- Collection: `hermes-documents`
- Production auth: `chroma-gate` checks `CHROMA_AUTH_TOKEN`. The Chroma 1.0.0 image does not.

The client calls `GET /api/v2/heartbeat` and falls back to `GET /api/v1/heartbeat`. `POST /documents` and `GET /documents/search` write and query `hermes-documents`.
