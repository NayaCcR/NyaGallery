"""Bounded direct HTTP image downloads; never use proxy or redirect handlers."""
from __future__ import annotations

from dataclasses import dataclass
import http.client
import ipaddress
from pathlib import Path
import queue
import socket
import ssl
import threading
import time
from urllib.parse import unquote, urlsplit


class RemoteImageError(ValueError):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass(frozen=True)
class RemoteImage:
    content: bytes
    content_type: str
    filename: str


def _resolve(host: str, port: int, timeout: float) -> list:
    # OS DNS resolution is not interruptible. Bound the caller's wait; a daemon
    # resolver can finish later but never initiates a connection.
    result: queue.Queue = queue.Queue(maxsize=1)

    def resolve() -> None:
        try:
            result.put(socket.getaddrinfo(host, port, type=socket.SOCK_STREAM))
        except Exception as exc:
            result.put(exc)

    threading.Thread(target=resolve, daemon=True).start()
    value = result.get(timeout=timeout)
    if isinstance(value, Exception):
        raise value
    if not value:
        raise RemoteImageError(400, "Remote host is not publicly reachable")
    for _, _, _, _, address in value:
        ip = ipaddress.ip_address(address[0])
        mapped = getattr(ip, "ipv4_mapped", None)
        if not ip.is_global or ip.is_multicast or (mapped is not None and (not mapped.is_global or mapped.is_multicast)):
            raise RemoteImageError(400, "Remote host is not publicly reachable")
    return value


class _PinnedConnection(http.client.HTTPConnection):
    def __init__(self, host: str, port: int, address: tuple, *, secure: bool, timeout: float):
        super().__init__(host, port, timeout=timeout)
        self.address = address
        self.secure = secure
        self._transport = None
        self._expired = threading.Event()

    def connect(self) -> None:
        family, socktype, proto, _, sockaddr = self.address
        self.sock = socket.socket(family, socktype, proto)
        self._transport = self.sock
        self.sock.settimeout(self.timeout)
        if self._expired.is_set():
            raise TimeoutError()
        # Numeric sockaddr returned by the single validated DNS lookup: no
        # create_connection/getaddrinfo call and no environment proxy lookup.
        self.sock.connect(sockaddr)
        if self.secure:
            self.sock = ssl.create_default_context().wrap_socket(self.sock, server_hostname=self.host, do_handshake_on_connect=False)
            self._transport = self.sock
            if self._expired.is_set():
                raise TimeoutError()
            self.sock.do_handshake()

    def abort(self) -> None:
        self._expired.set()
        # HTTPConnection may relinquish its socket to a Connection: close
        # response; keep the transport so its body can still be interrupted.
        if self._transport is not None:
            try:
                self._transport.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        self.close()


def fetch_remote_image(url: str, max_bytes: int, *, total_timeout: float = 30, io_timeout: float = 10) -> RemoteImage:
    """Fetch one image without redirects, with a deadline including DNS wait."""
    connection = None
    timer = None
    deadline = time.monotonic() + total_timeout
    try:
        if max_bytes <= 0 or total_timeout <= 0 or io_timeout <= 0:
            raise ValueError("Invalid download limits")
        url = url.strip()
        if any(ord(char) < 32 or ord(char) == 127 for char in url):
            raise ValueError("Invalid URL characters")
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username is not None or parsed.password is not None:
            raise RemoteImageError(400, "URL must be an absolute http or https URL without user information")
        host = parsed.hostname.encode("idna").decode("ascii")
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        addresses = _resolve(host, port, total_timeout)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError()
        connection = _PinnedConnection(host, port, addresses[0], secure=parsed.scheme == "https", timeout=min(io_timeout, remaining))
        # A socket timeout alone permits an indefinitely slow trickle. Shutdown
        # also interrupts header/body reads when the overall budget expires.
        timer = threading.Timer(remaining, connection.abort)
        timer.daemon = True
        timer.start()
        target = parsed.path or "/"
        if parsed.query:
            target += "?" + parsed.query
        connection.request("GET", target, headers={"User-Agent": "NyaGallery/1.0", "Accept": "image/*", "Accept-Encoding": "identity", "Connection": "close"})
        with connection.getresponse() as response:
            if not 200 <= response.status < 300:
                raise RemoteImageError(400, "Remote server did not return a successful image response")
            content_type = response.getheader("Content-Type", "").split(";", 1)[0].strip().lower()
            if not content_type.startswith("image/"):
                raise RemoteImageError(415, "Remote resource is not an image")
            declared = response.getheader("Content-Length")
            if declared is not None and (not declared.isdecimal() or int(declared) < 0):
                raise ValueError("Invalid content length")
            if declared is not None and int(declared) > max_bytes:
                raise RemoteImageError(413, "Remote image is too large")
            chunks = []
            size = 0
            while True:
                chunk = response.read1(min(64 * 1024, max_bytes + 1 - size))
                if time.monotonic() >= deadline:
                    raise TimeoutError()
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    raise RemoteImageError(413, "Remote image is too large")
                chunks.append(chunk)
            if declared is not None and size != int(declared):
                raise ValueError("Incomplete response")
        filename = Path(unquote(parsed.path)).name or "remote-image"
        if not Path(filename).suffix:
            filename += "." + content_type.split("/", 1)[1].split("+", 1)[0]
        return RemoteImage(b"".join(chunks), content_type, filename)
    except RemoteImageError:
        raise
    except Exception as exc:
        raise RemoteImageError(400, "Failed to fetch remote image") from exc
    finally:
        if timer is not None:
            timer.cancel()
        if connection is not None:
            connection.close()
