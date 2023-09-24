import os
import socket
from unittest.mock import patch

import certifi
import pytest
import requests
import urllib3
from minio import InvalidResponseError, Minio, S3Error
from minio.error import MinioException

from multiminio import MultiMinio
from tests.functional.config import CONFIG

# Mocking a successful health check
SUCCESS_HEALTH = requests.Response()
SUCCESS_HEALTH.status_code = 200

# Mocking a failed health check
FAIL_HEALTH = requests.RequestException()

EXPECTED_RESULT = "test result"
BUCKET1 = "bucket1"
OBJECT1 = "path1/object1"
EXISTING_OBJ = "ADABTC-s/aggs/1m/ADABTC-s.20210301.agg-1m.pk.gz"
EXISTING_BUCKET = "market-data-test"


class TestFunctionalMultiMinio:
    @staticmethod
    @pytest.fixture(scope="function")
    def patched_minio(client1, client2):
        with patch("multiminio.multiminio.requests.get") as mock_get:
            # First call to health check returns a timeout for client1 and success for client2
            mock_get.side_effect = [FAIL_HEALTH, SUCCESS_HEALTH]
            yield MultiMinio([client1, client2])

    @staticmethod
    def _check_internal_ip(hostname: str) -> bool:
        INTERNAL_IP_PREFIXES = ("172.16.", "192.168.", "10.1.")
        if ":" in hostname:
            host, _ = hostname.split(":")
        else:
            host = hostname
        ip_address = socket.gethostbyname(host)
        return ip_address.startswith(INTERNAL_IP_PREFIXES)

    def build_client(self, hostname: str, key: str, secret: str) -> Minio:
        conn_pool_size = 5
        ca_certs = os.environ.get("SSL_CERT_FILE") or certifi.where()
        https_pool_manager = urllib3.PoolManager(
            timeout=1,
            maxsize=conn_pool_size,
            cert_reqs="CERT_REQUIRED",
            ca_certs=ca_certs,
            retries=urllib3.Retry(total=0, backoff_factor=0.2, status_forcelist=[500, 502, 503, 504]),
        )
        # and a non-SSL http client
        http_pool_manager = urllib3.PoolManager(
            timeout=1,
            maxsize=conn_pool_size,
            retries=urllib3.Retry(total=0, backoff_factor=0.2, status_forcelist=[500, 502, 503, 504]),
        )
        secure = not self._check_internal_ip(hostname)
        if secure:
            http_client = https_pool_manager
        else:
            http_client = http_pool_manager

        minio_client = Minio(
            hostname,
            access_key=key,
            secret_key=secret,
            secure=secure,
            region="custom",
            http_client=http_client,
        )
        return minio_client

    def test_multiminio_nominal(self):
        client1 = self.build_client(CONFIG.MINIO_PUBLIC_SERVER1, CONFIG.MINIO_ACCESS_KEY1, CONFIG.MINIO_SECRET_KEY1)
        client2 = self.build_client(CONFIG.MINIO_PUBLIC_SERVER2, CONFIG.MINIO_ACCESS_KEY2, CONFIG.MINIO_SECRET_KEY2)
        multi_minio = MultiMinio(clients=[client1, client2])

        # read bucket/object from client1
        result = multi_minio.get_object(EXISTING_BUCKET, EXISTING_OBJ)
        assert result.status == 200
        assert len(result.data) == 74795

        # inexistent object read throws exception
        with pytest.raises(S3Error) as exc_info:
            bucket = "market-data-test"
            inexistent_obj = "inexistent_obj"
            result = multi_minio.get_object(bucket, inexistent_obj)
        assert exc_info.value.code == "NoSuchKey"
        assert result.status == 200

        # both clients are up
        statuses = multi_minio._retrieve_clients_health()
        assert statuses[0].status_code == 200
        assert statuses[1].status_code == 200

    def test_multiminio_wrong_credentials_throws(self):
        client1 = self.build_client(CONFIG.MINIO_PUBLIC_SERVER1, CONFIG.MINIO_ACCESS_KEY1, "inexistend_secret_key")
        client2 = self.build_client(CONFIG.MINIO_PUBLIC_SERVER2, CONFIG.MINIO_ACCESS_KEY2, CONFIG.MINIO_SECRET_KEY2)
        multi_minio = MultiMinio(clients=[client1, client2])

        with pytest.raises(S3Error) as exc_info:
            multi_minio.get_object(EXISTING_BUCKET, EXISTING_OBJ)
        assert exc_info.value.code == "SignatureDoesNotMatch"

    def test_multiminio_wrong_SSL_throws_access_denied(self):
        secure = not self._check_internal_ip(CONFIG.MINIO_PUBLIC_SERVER1)
        client1 = Minio(
            CONFIG.MINIO_PUBLIC_SERVER1,
            access_key=CONFIG.MINIO_ACCESS_KEY1,
            secret_key=CONFIG.MINIO_SECRET_KEY1,
            secure=not secure,  # here we force the wrong SSL
            region="custom",
        )

        client2 = self.build_client(CONFIG.MINIO_PUBLIC_SERVER2, CONFIG.MINIO_ACCESS_KEY2, CONFIG.MINIO_SECRET_KEY2)
        multi_minio = MultiMinio(clients=[client1, client2])

        with pytest.raises(S3Error) as exc_info:
            multi_minio.get_object(EXISTING_BUCKET, EXISTING_OBJ)
        assert exc_info.value.code == "AccessDenied"

    def test_wrong_HTTP_service_raises_invalid_response_error(self):
        client1 = self.build_client("microsoft.com", CONFIG.MINIO_ACCESS_KEY1, CONFIG.MINIO_SECRET_KEY1)
        client2 = self.build_client(CONFIG.MINIO_PUBLIC_SERVER2, CONFIG.MINIO_ACCESS_KEY2, CONFIG.MINIO_SECRET_KEY2)
        multi_minio = MultiMinio(clients=[client1, client2])

        with pytest.raises(InvalidResponseError) as exc_info:
            multi_minio.get_object(EXISTING_BUCKET, EXISTING_OBJ)
        assert exc_info.value._code == 400

    def test_multiminio_wrong_IP_switches_to_client2(self):
        client1 = self.build_client("192.168.101.101", CONFIG.MINIO_ACCESS_KEY1, CONFIG.MINIO_SECRET_KEY1)
        client2 = self.build_client(CONFIG.MINIO_PUBLIC_SERVER2, CONFIG.MINIO_ACCESS_KEY2, CONFIG.MINIO_SECRET_KEY2)
        multi_minio = MultiMinio(clients=[client1, client2])

        bucket = "market-data"
        result = multi_minio.get_object(bucket, EXISTING_OBJ)
        assert result.status == 200

    def test_multiminio_both_wrong_IPs_throws_MinioException(self):
        client1 = self.build_client("192.168.101.101", CONFIG.MINIO_ACCESS_KEY1, CONFIG.MINIO_SECRET_KEY1)
        client2 = self.build_client("192.168.101.102", CONFIG.MINIO_ACCESS_KEY2, CONFIG.MINIO_SECRET_KEY2)
        multi_minio = MultiMinio(clients=[client1, client2], fallback_timeout=2)

        bucket = "market-data"
        with pytest.raises(MinioException):
            multi_minio.get_object(bucket, EXISTING_OBJ)
