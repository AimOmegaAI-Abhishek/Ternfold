import hashlib
import httpx
import pytest
from ternfold.storage import LocalStorage, StorageUnavailable, SupabaseStorage, UnavailableStorage, configured_storage, safe_key


@pytest.mark.parametrize('key', ['../escape', '/absolute', 'C:/absolute', 'folder/../escape', 'folder\\escape', 'folder//file'])
def test_storage_rejects_unsafe_keys(key):
    with pytest.raises(ValueError):
        safe_key(key)


def test_local_immutable_round_trip_and_size_bound(tmp_path):
    storage = LocalStorage(tmp_path)
    key, digest = storage.put('org/test/case/test', '.csv', b'hello')
    assert digest == hashlib.sha256(b'hello').hexdigest()
    assert storage.read(key) == b'hello'
    assert storage.put('org/test/case/test', '.csv', b'hello') == (key, digest)
    with pytest.raises(ValueError, match='10 MB'):
        storage.read(key, max_bytes=4)
    storage.delete(key)
    with pytest.raises(FileNotFoundError):
        storage.read(key)


def test_vercel_never_falls_back_to_local_files(monkeypatch):
    monkeypatch.setenv('VERCEL', '1')
    monkeypatch.delenv('SUPABASE_URL', raising=False)
    monkeypatch.delenv('SUPABASE_SERVICE_ROLE_KEY', raising=False)
    instance = configured_storage()
    assert isinstance(instance, UnavailableStorage)
    with pytest.raises(StorageUnavailable, match='Vercel requires'):
        instance.put('test', '.pdf', b'content')


def test_supabase_private_signing_and_bounded_download():
    seen = []
    def handler(request):
        seen.append(request)
        if '/bucket/' in request.url.path:
            return httpx.Response(200, json={'public': False, 'file_size_limit': 10_000_000})
        if '/upload/sign/' in request.url.path:
            return httpx.Response(200, json={'url': '/object/upload/sign/ternfold-private/org/file.pdf?token=scoped'})
        if '/object/sign/' in request.url.path:
            return httpx.Response(200, json={'signedURL': '/object/sign/ternfold-private/org/file.pdf?token=scoped'})
        return httpx.Response(200, content=b'12345')
    storage = SupabaseStorage('https://test.supabase.co', 'server-only-secret', transport=httpx.MockTransport(handler))
    signed = storage.signed_upload('org/file.pdf')
    assert signed == 'https://test.supabase.co/storage/v1/object/upload/sign/ternfold-private/org/file.pdf?token=scoped'
    assert 'server-only-secret' not in signed
    assert storage.signed_download('org/file.pdf', 'source.pdf').endswith('&download=source.pdf')
    assert storage.read('org/file.pdf', max_bytes=5) == b'12345'
    with pytest.raises(ValueError):
        storage.read('org/file.pdf', max_bytes=4)
    assert all(r.headers['authorization'] == 'Bearer server-only-secret' for r in seen)


def test_public_bucket_is_rejected():
    storage = SupabaseStorage('https://test.supabase.co', 'secret', transport=httpx.MockTransport(lambda req: httpx.Response(200, json={'public': True, 'file_size_limit': 10_000_000})))
    with pytest.raises(StorageUnavailable, match='must be private'):
        storage.signed_upload('org/test.pdf')


def test_unbounded_bucket_is_rejected():
    storage = SupabaseStorage('https://test.supabase.co', 'secret', transport=httpx.MockTransport(lambda req: httpx.Response(200, json={'public': False, 'file_size_limit': None})))
    with pytest.raises(StorageUnavailable, match='10000000'):
        storage.signed_upload('org/test.pdf')


def test_storage_error_never_contains_key():
    storage = SupabaseStorage('https://test.supabase.co', 'secret-value', transport=httpx.MockTransport(lambda req: httpx.Response(403, json={'message': 'secret-value'})))
    with pytest.raises(StorageUnavailable) as exc:
        storage.signed_upload('org/test.pdf')
    assert 'secret-value' not in str(exc.value)


def test_rejects_other_storage_hosts():
    with pytest.raises(StorageUnavailable):
        SupabaseStorage('https://malicious.example', 'secret')
