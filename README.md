# MultiMinio

The **MultiMinio** library is designed to enhance the resilience and robustness of applications relying on Minio, a high-performance object storage server.

This library acts as a wrapper around multiple Minio client instances, offering seamless failover and health-check capabilities.

If one Minio instance becomes unreachable or is detected as unhealthy, the MultiMinio automatically reroutes requests to the next available Minio client,
ensuring uninterrupted access to your object storage.

With its built-in health check mechanism, configurable timeouts, and logging features, MultiMinio ensures optimal performance and reliability for
mission-critical applications leveraging Minio's storage capabilities.
