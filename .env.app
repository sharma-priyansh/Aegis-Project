# In-cluster service names for the docker-compose app overlay.
AEGIS_POSTGRES_DSN=postgresql+asyncpg://aegis:aegis@postgres:5432/aegis
AEGIS_REDIS_URL=redis://redis:6379/0
AEGIS_KAFKA_BOOTSTRAP=kafka:9092
AEGIS_OTEL_ENDPOINT=http://otel-collector:4317
AEGIS_QDRANT_URL=http://qdrant:6333
AEGIS_OLLAMA_URL=http://ollama:11434
AEGIS_INGEST_TOKEN=dev-ingest-token
AEGIS_SIGNING_SECRET=dev-signing-secret-change-me
AEGIS_TOPOLOGY_PATH=/app/deploy/local/topology.example.json
