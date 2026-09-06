from __future__ import annotations

import hashlib
import os
import mimetypes
from pathlib import Path
from urllib.parse import quote, urlparse

import httpx


class StorageUnavailable(RuntimeError):
    """A safe operational message that never includes credentials or signed URLs."""


def safe_key(key: str) -> str:
    if not key or key.startswith(('/', '\\')) or '\\' in key or any(p in {'', '.', '..'} or ':' in p for p in key.split('/')):
        raise ValueError('Unsafe storage key')
    return key


def object_key(namespace: str, suffix: str, data: bytes) -> tuple[str, str]:
    digest = hashlib.sha256(data).hexdigest()
    clean = ''.join(ch for ch in suffix.lower() if ch.isalnum() or ch == '.')[-12:] or '.bin'
    return f'{safe_key(namespace)}/{digest}{clean}', digest


class LocalStorage:
    direct_uploads = False

    def __init__(self, root: str | Path | None = None):
        default = Path(os.getenv('LOCALAPPDATA', str(Path.cwd() / '.runtime'))) / 'Ternfold' / 'storage'
        self.root = Path(root or os.getenv('TERNFOLD_STORAGE_ROOT', str(default)))
        # Lazy creation keeps imports safe on read-only hosts.

    def put(self, namespace: str, suffix: str, data: bytes) -> tuple[str, str]:
        key, digest = object_key(namespace, suffix, data)
        path = self.root.joinpath(*key.split('/'))
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(data)
        return key, digest

    def read(self, key: str, max_bytes: int | None = None) -> bytes:
        with self.root.joinpath(*safe_key(key).split('/')).open('rb') as source:
            data = source.read(max_bytes + 1 if max_bytes is not None else -1)
        if max_bytes is not None and len(data) > max_bytes:
            raise ValueError('This file is larger than the 10 MB limit.')
        return data

    def delete(self, key: str) -> None:
        self.root.joinpath(*safe_key(key).split('/')).unlink(missing_ok=True)

    def signed_download(self, key: str, filename: str | None = None) -> str | None:
        return None


class SupabaseStorage:
    direct_uploads = True

    def __init__(self, url: str, secret: str, bucket: str = 'ternfold-private', transport=None):
        parsed = urlparse(url)
        if parsed.scheme != 'https' or not parsed.hostname or not parsed.hostname.endswith('.supabase.co') or parsed.path not in {'', '/'} or parsed.username or parsed.query or parsed.fragment:
            raise StorageUnavailable('SUPABASE_URL must be the HTTPS project URL from Supabase settings.')
        if not secret or '/' in bucket or not bucket:
            raise StorageUnavailable('Set SUPABASE_SERVICE_ROLE_KEY and SUPABASE_STORAGE_BUCKET for private evidence storage.')
        self.base = url.rstrip('/') + '/storage/v1'
        self.bucket = bucket
        self._client = httpx.Client(headers={'apikey': secret, 'Authorization': f'Bearer {secret}'}, timeout=httpx.Timeout(60, connect=10), transport=transport, follow_redirects=False)

    def _path(self, key: str) -> str:
        return quote(self.bucket, safe='') + '/' + quote(safe_key(key), safe='/')

    def _request(self, method: str, path: str, **kwargs):
        try:
            response = self._client.request(method, self.base + path, **kwargs)
        except httpx.HTTPError as exc:
            raise StorageUnavailable('Private storage could not be reached. Existing work is preserved; retry the operation.') from None
        if response.status_code == 404:
            raise FileNotFoundError('Private storage object or configured bucket was not found.')
        if response.status_code >= 400:
            raise StorageUnavailable(f'Private storage rejected this operation (HTTP {response.status_code}). Check the private bucket and service credential.')
        return response

    def check_private_bucket(self) -> None:
        info = self._request('GET', '/bucket/' + quote(self.bucket, safe='')).json()
        if info.get('public') is not False:
            raise StorageUnavailable('The configured evidence bucket must be private.')
        limit = info.get('file_size_limit')
        if limit is None or int(limit) != 10_000_000:
            raise StorageUnavailable('Set the private evidence bucket file size limit to exactly 10000000 bytes (10 MB).')

    def put(self, namespace: str, suffix: str, data: bytes) -> tuple[str, str]:
        key, digest = object_key(namespace, suffix, data)
        self.check_private_bucket()
        try:
            response = self._client.post(self.base + '/object/' + self._path(key), content=data, headers={'Content-Type': mimetypes.guess_type(key)[0] or 'application/octet-stream', 'x-upsert': 'false'})
        except httpx.HTTPError:
            raise StorageUnavailable('Private storage could not be reached. Retry the upload.') from None
        # A retry of immutable content is safe only when its existing bytes agree.
        if response.status_code in {400, 409}:
            if self.read(key) != data:
                raise StorageUnavailable('Existing immutable evidence did not match this upload.')
        elif response.status_code >= 400:
            raise StorageUnavailable(f'Private storage rejected the upload (HTTP {response.status_code}).')
        return key, digest

    def read(self, key: str, max_bytes: int | None = None) -> bytes:
        try:
            with self._client.stream('GET', self.base + '/object/authenticated/' + self._path(key)) as response:
                if response.status_code == 404:
                    raise FileNotFoundError('Private evidence is unavailable.')
                if response.status_code >= 400:
                    raise StorageUnavailable(f'Private storage rejected the read (HTTP {response.status_code}).')
                chunks, size = [], 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if max_bytes is not None and size > max_bytes:
                        raise ValueError('This file is larger than the 10 MB limit.')
                    chunks.append(chunk)
                return b''.join(chunks)
        except httpx.HTTPError:
            raise StorageUnavailable('Private storage could not be reached. Retry the operation.') from None

    def delete(self, key: str) -> None:
        self._request('DELETE', '/object/' + quote(self.bucket, safe=''), json={'prefixes': [safe_key(key)]})

    def _signed_url(self, value: str) -> str:
        if value.startswith('/'):
            return self.base + value
        if value.startswith(self.base + '/'):
            return value
        raise StorageUnavailable('Private storage returned an invalid signed URL.')

    def signed_upload(self, key: str) -> str:
        self.check_private_bucket()
        result = self._request('POST', '/object/upload/sign/' + self._path(key), json={}, headers={'x-upsert': 'false'}).json()
        return self._signed_url(result['url'])

    def signed_download(self, key: str, filename: str | None = None) -> str:
        body = {'expiresIn': 60}
        result = self._request('POST', '/object/sign/' + self._path(key), json=body).json()
        url = self._signed_url(result['signedURL'])
        if filename:
            url += '&download=' + quote(filename, safe='')
        return url


class UnavailableStorage:
    direct_uploads = False
    def _fail(self, *args, **kwargs):
        raise StorageUnavailable('Vercel requires SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY and a private SUPABASE_STORAGE_BUCKET. Local file storage is disabled on Vercel.')
    put = read = delete = signed_download = _fail


def configured_storage():
    url = os.getenv('SUPABASE_URL', '')
    secret = os.getenv('SUPABASE_SERVICE_ROLE_KEY', '')
    if url and secret:
        return SupabaseStorage(url, secret, os.getenv('SUPABASE_STORAGE_BUCKET', 'ternfold-private'))
    if os.getenv('VERCEL'):
        return UnavailableStorage()
    return LocalStorage()


storage = configured_storage()
