import logging
from enum import auto
from threading import RLock
from typing import Callable, Collection, NamedTuple, Optional, Tuple, Type

import requests
from minio import Minio
from minio.error import InvalidResponseError, MinioException, S3Error
from streamerate import stream
from strenum import StrEnum
from tsx import TS


class HealthStatus(NamedTuple):
    status_code: int | Exception
    response_time: Optional[float]


class LoadBalanceType(StrEnum):
    FALLBACK = auto()
    ROUND_ROBIN = auto()
    RANDOM = auto()


FunctionType = Minio.__init__.__class__


class MultiMinio(Minio):
    HEALTH_CHECK_TIMEOUT = 5.0
    DEFAULT_FALLBACK_TIMEOUT = 60.0
    HEALTH_CHECK_HEARTBEAT = 300.0
    MAX_TRY_TIMEOUT = 60.0
    HEALTH_CHECK_INTERVAL = 10.0
    MAX_COMPATIBILITY = True  # If True, the MultiMinio instance will try to be max compatible with the received Minio instances, but possibly slightly slower

    def __new__(cls: type["MultiMinio"], *args, **kwargs) -> "MultiMinio":
        # Get all methods of Minio class
        all_attributes_and_methods = dir(Minio)
        public_methods = [attr for attr in all_attributes_and_methods if callable(getattr(Minio, attr)) and not attr.startswith("_")]
        instance = super().__new__(cls)
        for method_name in public_methods:
            method = getattr(Minio, method_name)
            setattr(instance, method_name, instance._method_wrapper(method))
        return instance

    def __init__(
        self,
        clients: Collection[Minio],
        load_balance_type: LoadBalanceType = LoadBalanceType.FALLBACK,
        fallback_timeout: float = DEFAULT_FALLBACK_TIMEOUT,
        health_check_timeout: float = HEALTH_CHECK_TIMEOUT,
        health_check_heartbeat: float = HEALTH_CHECK_HEARTBEAT,
        max_try_timeout: float = MAX_TRY_TIMEOUT,
        health_check_interval: float = HEALTH_CHECK_INTERVAL,
        ts_type: Type[TS] = TS,
    ):
        """
        :param clients: List of Minio client instances
        :param fallback_timeout: The maximum time to wait for a healthy client to become available.
        :param health_check_timeout: The timeout for the health check request.
        :param health_check_heartbeat: The interval between health checks.
        :param max_try_timeout: The maximum time to wait for a single request to complete.
        :param health_check_interval: The interval between health checks (it won't do more than one health c heck within this interval)
        :param ts_type: The timestamp type to use for time getting.
        """
        self._clients = tuple(clients)
        assert len(self._clients) > 0
        self._load_balance_type = load_balance_type
        assert load_balance_type == LoadBalanceType.FALLBACK, "Only fallback load balancing is supported at the moment"
        self._fallback_timeout = fallback_timeout
        self._health_check_timeout = health_check_timeout
        self._health_check_heartbeat = health_check_heartbeat
        self._max_try_timeout = max_try_timeout
        self._health_check_min_interval = health_check_interval
        assert self._health_check_heartbeat >= self._health_check_min_interval * 2
        assert self._health_check_min_interval >= self._health_check_timeout * 2
        self._current_client_index = 0  # Start with the first client - valid only for fallback load balancing
        self._ts_type = ts_type
        self._last_health_check_ts = TS(0)
        self._current_fail_ts: Optional[TS] = None
        self._health_statuses: Optional[Tuple[HealthStatus, ...]] = None
        self._lock = RLock()

    def _method_wrapper(self, method: Callable) -> Callable:
        assert isinstance(method, FunctionType)

        def wrapper(*args, **kwargs):
            assert isinstance(method, FunctionType)
            return self._execute_with_fallback(method, *args, **kwargs)

        return wrapper

    def _get_current_client(self) -> Minio:
        with self._lock:
            now_ts = self._ts_type.now()
            health_check_age = now_ts - self._last_health_check_ts
            if self._current_client_index > 0 and health_check_age > self._health_check_heartbeat:
                return self._get_next_client()
            return self._clients[self._current_client_index]

    def _execute_with_fallback(self, func: Callable, *args, **kwargs):
        """
        Execute a function on the Minio clients in order, falling back to the next one in case of errors.

        :param func: The function to execute, e.g., put_object, list_objects, etc.
        :param args:  Positional arguments for the function.
        :param kwargs: The keyword arguments to pass to the function
        :return: The result of the first successful execution or raises an exception if all attempts fail.
        """
        start_try_ts = self._ts_type.now()
        current_client = self._get_current_client()
        while self._ts_type.now() - start_try_ts < self._fallback_timeout:
            try:
                if self.MAX_COMPATIBILITY:
                    method = getattr(current_client, func.__name__)
                    result = method(*args, **kwargs)
                else:
                    result = func(current_client, *args, **kwargs)
                with self._lock:
                    self._current_fail_ts = None
                return result
            except S3Error:
                raise
            except InvalidResponseError:
                raise
            except Exception as e:  # pylint: disable=broad-exception-caught
                with self._lock:
                    if self._current_fail_ts is None:
                        self._current_fail_ts = start_try_ts
                    url = self._get_client_url(current_client)
                    logging.error(f"Minio client {url} when calling: \n{func.__name__}({args}, {kwargs})\nfailed with {e}.\nSearching for a healthy client...")
                    next_client = self._get_next_client()
                next_url = self._get_client_url(next_client)
                logging.error(f"Found healthy client {next_url}. Continuing...")
                current_client = next_client
        raise MinioException(f"Failed to execute:\n{func.__name__}({args}, {kwargs})\n on all Minio clients within {self._max_try_timeout:.3f} seconds")

    def _get_next_client(self) -> Minio:
        """
        Get the next available client. Return None if none are available.
        """
        start_ts = self._current_fail_ts or self._ts_type.now()
        with self._lock:
            while True:
                health_statuses = self._retrieve_clients_health()
                for i, health_status in enumerate(health_statuses):
                    if health_status.status_code == 200:
                        self._current_client_index = i
                        return self._clients[self._current_client_index]
                now_ts = self._ts_type.now()
                down_time = float(now_ts - start_ts)
                if down_time > self._fallback_timeout:
                    error_msg = f"All Minio clients are down for {down_time:.3f} seconds"
                    raise MinioException(error_msg)

    def _retrieve_clients_health(self) -> Tuple[HealthStatus, ...]:
        health_status_age = self._ts_type.now() - self._last_health_check_ts
        if self._last_health_check_ts > TS(0) and health_status_age < self._health_check_min_interval:
            assert self._health_statuses is not None
            return self._health_statuses
        pool_size = min(len(self._clients), 32)
        statuses = tuple(stream(self._clients).mtmap(self._check_health_status, poolSize=pool_size))
        self._last_health_check_ts = self._ts_type.now()
        self._health_statuses = statuses
        return statuses

    def _check_health_status(self, client: Minio) -> HealthStatus:
        url = self._get_client_url(client)
        t0 = self._ts_type.now()
        try:
            response = requests.get(f"{url}/minio/health/live", timeout=self._health_check_timeout)
            dt = float(self._ts_type.now() - t0)
            logging.warning(f"Health check for {url} took {dt:.3f} seconds")
            health_status = HealthStatus(status_code=response.status_code, response_time=dt)
            return health_status
        except requests.RequestException as e:
            dt = float(self._ts_type.now() - t0)
            health_status = HealthStatus(status_code=e, response_time=dt)
            return health_status

    @staticmethod
    def _get_client_url(client: Minio) -> str:
        try:
            url = client._base_url.geturl()  # pylint: disable=protected-access
        except AttributeError:
            _host = client._base_url.host  # pylint: disable=protected-access
            _is_https = client._base_url.is_https  # pylint: disable=protected-access
            _protocol = "https" if _is_https else "http"
            url = f"{_protocol}://{_host}"
        return url

    def __del__(self):
        """This override is needed to avoid calling the Minio.__del__ which requires some more instantiations and fails for this instance."""
