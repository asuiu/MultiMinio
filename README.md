# MultiMinio: High-Availability Minio/S3 Client Wrapper

# MultiMinio

MultiMinio is a Python library designed to provide a high-availability wrapper around multiple Minio client instances. By orchestrating the behavior of multiple
Minio clients, MultiMinio ensures resilience and failover, enhancing the reliability of your data storage operations.

This library acts as a wrapper around multiple Minio client instances, offering seamless failover and health-check capabilities.

If one Minio instance becomes unreachable or is detected as unhealthy, the MultiMinio automatically reroutes requests to the next available Minio client,
ensuring uninterrupted access to your object storage.

With its built-in health check mechanism, configurable timeouts, and logging features, MultiMinio ensures optimal performance and reliability for
mission-critical applications leveraging Minio's storage capabilities.

## Features

- **Multiple Minio Clients:** Manage and utilize multiple Minio client instances simultaneously.
- **Health Checks:** Automated health checks for the Minio instances to determine their availability.
- **Resilience Mechanisms:**
- **Fallback:** Currently, MultiMinio supports the Fallback resilience mechanism, ensuring requests are directed to healthy Minio instances when others are
  unavailable. This assumes that Minio instances are synchronized in an Eventually Consistent manner.
- **Future Implementations:** In upcoming versions, MultiMinio will introduce RoundRobin and Random load balancing techniques, adding more flexibility and
  options for directing traffic among Minio instances.
- **Customizable Settings:** Configure health check intervals, timeouts, and other parameters to suit your needs.

## Installation

Install MultiMinio directly from PyPi using `pip` (https://pypi.org/project/multiminio/):

```bash
pip install multiminio
```

## Usage

Here's a basic example of how to use MultiMinio with two Minio client instances:

```python
from multiminio import MultiMinio
from minio import Minio

# Create two Minio client instances
client1 = Minio("localhost:9001")
client2 = Minio("localhost:9002")

# Bundle the Minio clients into a MultiMinio instance
minio_client = MultiMinio(clients=[client1, client2])
```

### Configuration

#### Initialization Parameters

- `clients`: List of initialized Minio client instances.
- `fallback_timeout`: Maximum time to wait for a healthy client to become available. Default is 60.0 seconds.
- `health_check_timeout`: Duration to wait for the health check request to complete. Default is 5.0 seconds.
- `health_check_heartbeat`: Interval between health checks. Default is 300.0 seconds.
- `max_try_timeout`: Maximum time to wait for a single request to complete. Default is 60.0 seconds.
- `health_check_interva`l`: Minimum interval between consecutive health checks. Default is 10.0 seconds.

## Contribution

If you'd like to contribute to the development of MultiMinio, please fork the repository and submit a pull request.

- https://github.com/asuiu/multiminio

## License

MultiMinio is licensed under MIT license.

## Author

Andrei Suiu

- mail: [andrei.suiu@gmail.com](mailto:andrei.suiu@gmail.com)
- [LinkedIn](https://www.linkedin.com/in/andrei-suiu/)

## Support

For any queries or issues, please open an issue on the GitHub repository, and we'll address it promptly.