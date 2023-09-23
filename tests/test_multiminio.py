from unittest.mock import MagicMock, call, patch
from urllib.parse import ParseResult

import pytest
import requests
from minio import Minio

from multiminio import MultiMinio

# Mocking a successful health check
SUCCESS_HEALTH = requests.Response()
SUCCESS_HEALTH.status_code = 200

# Mocking a failed health check
FAIL_HEALTH = requests.RequestException()

EXPECTED_RESULT = "test result"
BUCKET1 = "bucket1"
OBJECT1 = "path1/object1"


@pytest.fixture
def client1():
    client = MagicMock(spec=Minio)
    base_url = MagicMock(spec=ParseResult)
    base_url.geturl.return_value = "http://minio1.com"
    client._base_url = base_url
    client.get_object.side_effect = [Exception("Client 1 failed initially"), "Client 1 Result"]
    return client


@pytest.fixture
def client2():
    client = MagicMock(spec=Minio)
    base_url = MagicMock(spec=ParseResult)
    base_url.geturl.return_value = "http://minio2.com"
    client._base_url = base_url

    def side_effect(bucket_name, object_nam, *args, **kwargs):
        return {(BUCKET1, OBJECT1): EXPECTED_RESULT}[(bucket_name, object_nam)]

    client.get_object = side_effect
    return client


class TestMultiMinio:
    @pytest.fixture(scope="function")
    def mock_request_get(self, mocker):
        """Mock the requests.get function to return a predetermined health check status."""
        mock_get = mocker.patch("requests.get")
        response = mocker.MagicMock()
        response.status_code = 200
        response.json.return_value = {"key": "value"}  # You can customize the response as needed

        # Set the return value of requests.get to the mocked response
        mock_get.return_value = response

        return mock_get

    @staticmethod
    @pytest.fixture(scope="function")
    def patched_minio(client1, client2):
        with patch("multiminio.multiminio.requests.get") as mock_get:
            # First call to health check returns a timeout for client1 and success for client2
            mock_get.side_effect = [FAIL_HEALTH, SUCCESS_HEALTH]
            yield MultiMinio([client1, client2])

    @staticmethod
    def test_multiminio_get_object():
        """Assert that when calling get_object it will use client2 and return the expected result"""
        client1 = MagicMock(spec=Minio)
        base_url = MagicMock(spec=ParseResult)
        base_url.geturl.return_value = "http://minio1.com"
        client1._base_url = base_url
        client1.get_object.side_effect = [Exception("Client 1 failed initially"), "Client 1 Result"]

        client2 = MagicMock(spec=Minio)
        base_url = MagicMock(spec=ParseResult)
        base_url.geturl.return_value = "http://minio2.com"
        client2._base_url = base_url

        def get_object2(bucket_name, object_nam, *args, **kwargs):
            return {(BUCKET1, OBJECT1): EXPECTED_RESULT}[(bucket_name, object_nam)]

        client2.get_object = get_object2
        with patch("multiminio.multiminio.requests.get") as mock_get:
            # First call to health check returns a timeout for client1 and success for client2
            mock_get.side_effect = [FAIL_HEALTH, SUCCESS_HEALTH]
            multi_minio = MultiMinio([client1, client2])
            result = multi_minio.get_object(BUCKET1, OBJECT1)
            assert result == EXPECTED_RESULT
            expected_health_calls = [call("http://minio1.com/minio/health/live", timeout=5.0), call("http://minio2.com/minio/health/live", timeout=5.0)]
            mock_get.assert_has_calls(expected_health_calls, any_order=False)
