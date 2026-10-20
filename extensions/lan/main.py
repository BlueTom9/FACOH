import select
import socket
import struct
import threading
import time

_MAX_MESSAGE_SIZE = 16 * 1024 * 1024


def is_timeout(error):
    return isinstance(error, TimeoutError)


class LAN:
    def __init__(self):
        self._lock = threading.RLock()
        self._server_socket = None
        self._server_thread = None
        self._server_connections = {}
        self._last_server_connection = None
        self._next_connection_id = 1
        self._max_clients = 100
        self._client_connection = None
        self._udp_server_socket = None
        self._udp_client_socket = None

    def _make_connection(self, connection_socket, role, address):
        return {
            "socket": connection_socket,
            "role": role,
            "address": address,
            "buffer": bytearray(),
            "send_lock": threading.Lock(),
            "receive_lock": threading.Lock(),
            "closed": False
        }

    def _close_connection(self, connection):
        if connection is None:
            return
        with self._lock:
            if connection["closed"]:
                return
            connection["closed"] = True
            if self._client_connection is connection:
                self._client_connection = None
            connection_id = connection.get("id")
            if self._server_connections.get(connection_id) is connection:
                del self._server_connections[connection_id]
                if self._last_server_connection == connection_id:
                    self._last_server_connection = next(
                        reversed(self._server_connections),
                        None
                    )
        try:
            connection["socket"].shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        connection["socket"].close()

    def _get_connection(self, role="auto"):
        if not isinstance(role, int) and role not in (
            "auto", "client", "server"
        ):
            raise ValueError(
                "connection must be 'auto', 'client', 'server', or a client ID"
            )
        with self._lock:
            if isinstance(role, int) and not isinstance(role, bool):
                connection = self._server_connections.get(role)
            elif role == "client":
                connection = self._client_connection
            elif role == "server":
                connection = self._server_connections.get(
                    self._last_server_connection
                )
            else:
                connection = (
                    self._client_connection
                    or self._server_connections.get(
                        self._last_server_connection
                    )
                )
            if connection is None or connection["closed"]:
                raise ValueError(f"No active {role} connection")
            return connection

    def _accept_connections(self, server_socket):
        while True:
            try:
                connection_socket, address = server_socket.accept()
            except OSError:
                return
            connection_socket.setsockopt(
                socket.SOL_SOCKET,
                socket.SO_KEEPALIVE,
                1
            )
            connection = self._make_connection(
                connection_socket,
                "server",
                address
            )
            with self._lock:
                if self._server_socket is not server_socket:
                    accept_connection = False
                elif len(self._server_connections) < self._max_clients:
                    connection_id = self._next_connection_id
                    self._next_connection_id += 1
                    connection["id"] = connection_id
                    self._server_connections[connection_id] = connection
                    self._last_server_connection = connection_id
                    accept_connection = True
                else:
                    accept_connection = False
            if not accept_connection:
                self._close_connection(connection)

    def host(self, host="0.0.0.0", port=8080, backlog=5, max_clients=100):
        if max_clients < 1:
            raise ValueError("max_clients must be greater than zero")
        self.stop_host()
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_socket.bind((host, port))
            server_socket.listen(backlog)
        except OSError:
            server_socket.close()
            raise

        with self._lock:
            self._server_socket = server_socket
            self._max_clients = max_clients
            self._server_thread = threading.Thread(
                target=self._accept_connections,
                args=(server_socket,),
                daemon=True
            )
            self._server_thread.start()
        return server_socket.getsockname()

    def connect(self, host="127.0.0.1", port=8080, timeout=10):
        connection_socket = socket.create_connection(
            (host, port),
            timeout=timeout
        )
        connection_socket.settimeout(None)
        connection_socket.setsockopt(
            socket.SOL_SOCKET,
            socket.SO_KEEPALIVE,
            1
        )
        connection = self._make_connection(
            connection_socket,
            "client",
            connection_socket.getpeername()
        )
        with self._lock:
            old_connection = self._client_connection
            self._client_connection = connection
        self._close_connection(old_connection)
        return connection["address"]

    def send(self, message, connection="auto"):
        if connection == "all":
            return len(self.broadcast(message))
        active_connection = self._get_connection(connection)
        if isinstance(message, bytes):
            payload = message
        else:
            payload = str(message).encode("utf-8")
        if len(payload) > _MAX_MESSAGE_SIZE:
            raise ValueError(
                f"Message exceeds {_MAX_MESSAGE_SIZE} byte limit"
            )
        packet = struct.pack("!I", len(payload)) + payload
        try:
            with active_connection["send_lock"]:
                active_connection["socket"].sendall(packet)
        except OSError:
            self._close_connection(active_connection)
            raise
        return len(payload)

    def _read_more(self, connection, deadline):
        remaining = None
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Timed out waiting for a LAN message")
        readable, _, _ = select.select(
            [connection["socket"]],
            [],
            [],
            remaining
        )
        if not readable:
            raise TimeoutError("Timed out waiting for a LAN message")
        chunk = connection["socket"].recv(65536)
        if not chunk:
            self._close_connection(connection)
            raise ConnectionError("The LAN peer closed the connection")
        connection["buffer"].extend(chunk)

    def _receive_message(self, active_connection, timeout):
        if timeout is not None and timeout < 0:
            raise ValueError("timeout cannot be negative")
        deadline = None if timeout is None else time.monotonic() + timeout
        with active_connection["receive_lock"]:
            return self._receive_message_locked(active_connection, deadline)

    def _receive_message_locked(self, active_connection, deadline):
        buffer = active_connection["buffer"]
        while len(buffer) < 4:
            self._read_more(active_connection, deadline)
        message_size = struct.unpack("!I", buffer[:4])[0]
        if message_size > _MAX_MESSAGE_SIZE:
            self._close_connection(active_connection)
            raise ValueError("Received message exceeds the size limit")
        packet_size = 4 + message_size
        while len(buffer) < packet_size:
            self._read_more(active_connection, deadline)
        payload = bytes(buffer[4:packet_size])
        del buffer[:packet_size]
        try:
            return payload.decode("utf-8")
        except UnicodeDecodeError:
            return payload

    def receive(self, connection="auto", timeout=None):
        if connection == "any":
            return self.receive_any(timeout)
        active_connection = self._get_connection(connection)
        return self._receive_message(active_connection, timeout)

    def receive_any(self, timeout=None):
        if timeout is not None and timeout < 0:
            raise ValueError("timeout cannot be negative")
        with self._lock:
            connections = list(self._server_connections.values())
        if not connections:
            raise ValueError("No connected server clients")

        connections.sort(key=lambda connection: connection["id"])
        for connection in connections:
            connection["receive_lock"].acquire()
        deadline = None if timeout is None else time.monotonic() + timeout
        try:
            while True:
                for connection in connections:
                    buffer = connection["buffer"]
                    if len(buffer) >= 4:
                        message_size = struct.unpack("!I", buffer[:4])[0]
                        if (
                            message_size > _MAX_MESSAGE_SIZE
                            or len(buffer) >= 4 + message_size
                        ):
                            return (
                                connection["id"],
                                self._receive_message_locked(
                                    connection,
                                    deadline
                                )
                            )
                remaining = None
                if deadline is not None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError(
                            "Timed out waiting for a LAN message"
                        )
                readable, _, _ = select.select(
                    [connection["socket"] for connection in connections],
                    [],
                    [],
                    remaining
                )
                if not readable:
                    raise TimeoutError(
                        "Timed out waiting for a LAN message"
                    )
                ready_socket = readable[0]
                connection = next(
                    connection
                    for connection in connections
                    if connection["socket"] is ready_socket
                )
                return (
                    connection["id"],
                    self._receive_message_locked(connection, deadline)
                )
        finally:
            for connection in reversed(connections):
                connection["receive_lock"].release()

    def broadcast(self, message):
        with self._lock:
            connection_ids = list(self._server_connections)
        sent_to = []
        for connection_id in connection_ids:
            try:
                self.send(message, connection_id)
                sent_to.append(connection_id)
            except (OSError, ValueError):
                pass
        return sent_to

    def server_clients(self):
        with self._lock:
            return [
                {
                    "id": connection_id,
                    "address": connection["address"]
                }
                for connection_id, connection
                in self._server_connections.items()
            ]

    def disconnect(self, connection="auto"):
        if connection == "all":
            with self._lock:
                connections = [
                    self._client_connection,
                    *self._server_connections.values()
                ]
            closed = False
            for active_connection in connections:
                if active_connection is not None:
                    self._close_connection(active_connection)
                    closed = True
            return closed
        try:
            active_connection = self._get_connection(connection)
        except ValueError:
            return False
        self._close_connection(active_connection)
        return True

    def stop_host(self):
        with self._lock:
            server_socket = self._server_socket
            self._server_socket = None
            self._server_thread = None
        if server_socket is None:
            return False
        try:
            server_socket.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        server_socket.close()
        return True

    def is_connected(self, connection="auto"):
        if connection == "server":
            with self._lock:
                return bool(self._server_connections)
        try:
            self._get_connection(connection)
        except ValueError:
            return False
        return True

    def is_hosting(self):
        with self._lock:
            return self._server_socket is not None

    def local_address(self, connection="auto"):
        return self._get_connection(connection)["socket"].getsockname()

    def peer_address(self, connection="auto"):
        return self._get_connection(connection)["socket"].getpeername()

    def udp_host(self, host="0.0.0.0", port=8080):
        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            udp_socket.bind((host, port))
        except OSError:
            udp_socket.close()
            raise
        with self._lock:
            old_socket = self._udp_server_socket
            self._udp_server_socket = udp_socket
        if old_socket is not None:
            old_socket.close()
        return udp_socket.getsockname()

    def udp_connect(self, host="127.0.0.1", port=8080,
                    local_host="0.0.0.0", local_port=0):
        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            udp_socket.bind((local_host, local_port))
            udp_socket.connect((host, port))
        except OSError:
            udp_socket.close()
            raise
        with self._lock:
            old_socket = self._udp_client_socket
            self._udp_client_socket = udp_socket
        if old_socket is not None:
            old_socket.close()
        return udp_socket.getpeername()

    def _get_udp_socket(self, endpoint="auto"):
        if endpoint not in ("auto", "client", "server"):
            raise ValueError("endpoint must be 'auto', 'client', or 'server'")
        with self._lock:
            if endpoint == "client":
                udp_socket = self._udp_client_socket
            elif endpoint == "server":
                udp_socket = self._udp_server_socket
            else:
                udp_socket = (
                    self._udp_client_socket or self._udp_server_socket
                )
        if udp_socket is None:
            raise ValueError(f"No open UDP {endpoint} socket")
        return udp_socket

    def udp_send(self, message, host=None, port=None, endpoint="auto"):
        udp_socket = self._get_udp_socket(endpoint)
        payload = (
            message if isinstance(message, bytes)
            else str(message).encode("utf-8")
        )
        if len(payload) > 65507:
            raise ValueError("UDP payload cannot exceed 65507 bytes")
        if host is None and port is None:
            try:
                udp_socket.getpeername()
            except OSError as error:
                raise ValueError(
                    "host and port are required for an unconnected UDP socket"
                ) from error
            return udp_socket.send(payload)
        if host is None or port is None:
            raise ValueError("host and port must be provided together")
        if host == "255.255.255.255":
            udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sent = udp_socket.sendto(payload, (host, port))
        return sent

    def udp_receive(self, endpoint="auto", timeout=None, max_size=65507):
        if timeout is not None and timeout < 0:
            raise ValueError("timeout cannot be negative")
        if max_size < 1 or max_size > 65507:
            raise ValueError("max_size must be between 1 and 65507")
        udp_socket = self._get_udp_socket(endpoint)
        readable, _, _ = select.select(
            [udp_socket],
            [],
            [],
            timeout
        )
        if not readable:
            raise TimeoutError("Timed out waiting for a UDP datagram")
        payload, address = udp_socket.recvfrom(max_size + 1)
        if len(payload) > max_size:
            raise ValueError("UDP datagram exceeds max_size")
        try:
            payload = payload.decode("utf-8")
        except UnicodeDecodeError:
            pass
        return payload, address

    def udp_close(self, endpoint="auto"):
        if endpoint not in ("auto", "client", "server", "all"):
            raise ValueError(
                "endpoint must be 'auto', 'client', 'server', or 'all'"
            )
        with self._lock:
            if endpoint == "all":
                udp_sockets = [
                    self._udp_client_socket,
                    self._udp_server_socket
                ]
                self._udp_client_socket = None
                self._udp_server_socket = None
            elif endpoint == "client" or (
                endpoint == "auto" and self._udp_client_socket is not None
            ):
                udp_sockets = [self._udp_client_socket]
                self._udp_client_socket = None
            else:
                udp_sockets = [self._udp_server_socket]
                self._udp_server_socket = None
        closed = False
        for udp_socket in udp_sockets:
            if udp_socket is not None:
                udp_socket.close()
                closed = True
        return closed

    def udp_is_open(self, endpoint="auto"):
        if endpoint == "all":
            with self._lock:
                return (
                    self._udp_client_socket is not None
                    or self._udp_server_socket is not None
                )
        try:
            self._get_udp_socket(endpoint)
        except ValueError:
            return False
        return True

    def udp_local_address(self, endpoint="auto"):
        return self._get_udp_socket(endpoint).getsockname()

    def udp_peer_address(self, endpoint="auto"):
        return self._get_udp_socket(endpoint).getpeername()


_lan = LAN()

FUNCTIONS = {
    "host": _lan.host,
    "connect": _lan.connect,
    "send": _lan.send,
    "receive": _lan.receive,
    "is_timeout": is_timeout,
    "receive_any": _lan.receive_any,
    "broadcast": _lan.broadcast,
    "server_clients": _lan.server_clients,
    "disconnect": _lan.disconnect,
    "stop_host": _lan.stop_host,
    "is_connected": _lan.is_connected,
    "is_hosting": _lan.is_hosting,
    "local_address": _lan.local_address,
    "peer_address": _lan.peer_address,
    "udp_host": _lan.udp_host,
    "udp_connect": _lan.udp_connect,
    "udp_send": _lan.udp_send,
    "udp_receive": _lan.udp_receive,
    "udp_close": _lan.udp_close,
    "udp_is_open": _lan.udp_is_open,
    "udp_local_address": _lan.udp_local_address,
    "udp_peer_address": _lan.udp_peer_address
}
