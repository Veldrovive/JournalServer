import boto3
from botocore.exceptions import ClientError

from jserver.storage.file.file_manager import FileManager

from jserver.utils.logger import setup_logging
logger = setup_logging(__name__)

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from jserver.config import Config

import socket

def get_local_ip():
    try:
        # Create a UDP socket
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            # Connect to a public DNS server (does not actually establish a connection for UDP)
            s.connect(("8.8.8.8", 80))
            # Get the socket's own address
            local_ip = s.getsockname()[0]
            return local_ip
    except Exception as e:
        print(f"Could not get local IP: {e}")

class S3FileManager(FileManager):
    def __init__(self, config: 'Config'):
        manager_config = config.storage_manager.file_storage_manager
        manager_type = manager_config.manager_type
        if manager_type == 'minio':
            logger.debug("Using Minio file manager")
        elif manager_type == 's3':
            logger.debug("Using S3 file manager")
        else:
            raise ValueError(f"Unknown file storage manager type: {manager_type}")

        self.manager_config = manager_config
        host = self.manager_config.host
        if host == 'localhost':
            host = get_local_ip()
        port = self.manager_config.port
        username = self.manager_config.username
        password = self.manager_config.password
        self.bucket = self.manager_config.bucket

        self.client = boto3.client(
            's3',
            endpoint_url=f"http://{host}:{port}",
            aws_access_key_id=username,
            aws_secret_access_key=password
        )
        if self.client is None:
            raise ValueError("Could not create S3 client")

        # Create the bucket
        try:
            self.client.create_bucket(Bucket=self.bucket)
        except ClientError as e:
            if e.response['Error']['Code'] == 'BucketAlreadyOwnedByYou':
                pass
            else:
                raise e

    def insert_file(self, local_path: str) -> str:
        file_id = self.create_data_uuid()
        self.client.upload_file(local_path, self.bucket, file_id)
        return file_id

    def delete_file(self, file_id: str):
        self.client.delete_object(Bucket=self.bucket, Key=file_id)

    def pull_file(self, file_id: str, local_path: str):
        self.client.download_file(self.bucket, file_id, local_path)

    def get_file_url(self, file_id: str) -> str:
        url = self.client.generate_presigned_url(
            ClientMethod='get_object',
            Params={
                'Bucket': self.bucket,
                'Key': file_id
            }
        )
        return url
