from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import io
import socket
import threading
import logging
from .config import settings

_db_logger = logging.getLogger(__name__)

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=300,
    pool_size=25,
    max_overflow=50,
    pool_timeout=30
) if settings.DATABASE_URL else None
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine) if engine else None
Base = declarative_base()

# Thread-local registry of local PG sessions opened via get_db() for the
# current request thread. Lets long, slow external calls (notably Magento)
# release their idle local PG connection back to the pool before sleeping
# on a remote query, preventing pool exhaustion when many requests are
# blocked simultaneously on Magento timeouts.
#
# Safety: SQLAlchemy 2.x sessions lazily reacquire a connection on the
# next ORM operation, so calling .close() on idle sessions is transparent
# to the caller. Sessions with pending uncommitted writes are skipped to
# avoid losing in-flight transactions.
_active_local_sessions = threading.local()


def _register_local_session(session) -> None:
    bucket = getattr(_active_local_sessions, "sessions", None)
    if bucket is None:
        bucket = []
        _active_local_sessions.sessions = bucket
    bucket.append(session)


def _unregister_local_session(session) -> None:
    bucket = getattr(_active_local_sessions, "sessions", None)
    if not bucket:
        return
    try:
        bucket.remove(session)
    except ValueError:
        pass


def release_local_db_connections() -> int:
    """Release the underlying connection of any idle local PG session
    registered for the current thread, returning the count released.

    Called before long external DB calls (e.g. Magento) to avoid holding
    pool slots while waiting on remote I/O. Sessions with pending writes
    (in_transaction with non-empty `dirty`/`new`/`deleted`) are skipped.
    """
    bucket = getattr(_active_local_sessions, "sessions", None)
    if not bucket:
        return 0
    released = 0
    for session in list(bucket):
        try:
            # Skip sessions with pending uncommitted changes
            if session.in_transaction() and (
                session.dirty or session.new or session.deleted
            ):
                continue
            session.close()
            released += 1
        except Exception:
            # Never let cleanup error break the caller
            pass
    return released


def get_db():
    if SessionLocal is None:
        raise Exception("DATABASE_URL not configured")
    db = SessionLocal()
    _register_local_session(db)
    try:
        yield db
    finally:
        _unregister_local_session(db)
        db.close()

engine_ativo = None
SessionLocalAtivo = None

engine_magento = None
SessionLocalMagento = None

ssh_tunnel = None
engine_ssh = None
SessionLocalSSH = None

_watchdog_running = False
_watchdog_lock = threading.Lock()
# Single lock guarding ALL transitions of ssh_tunnel/engine_ssh
# (watchdog, on-demand ensure, manual init/close). This prevents the
# watchdog and ensure_ssh_engine_ready from racing each other
# (e.g. one closing what the other just rebuilt).
_ssh_lifecycle_lock = threading.RLock()


def _is_tunnel_alive() -> bool:
    """Return True if the SSH transport is active."""
    global ssh_tunnel
    if ssh_tunnel is None:
        return False
    client = ssh_tunnel.get('client') if isinstance(ssh_tunnel, dict) else None
    if client is None:
        return False
    transport = client.get_transport()
    return transport is not None and transport.is_active()


def _ssh_watchdog():
    """Daemon thread: checks tunnel health every 15 s and reconnects if dead.
    All tunnel transitions go through `_ssh_lifecycle_lock` so we don't race
    `ensure_ssh_engine_ready()` callers."""
    import time as _time
    CHECK_INTERVAL = 15
    RECONNECT_DELAY = 5
    _db_logger.info("SSH tunnel watchdog started")
    while True:
        global _watchdog_running
        if not _watchdog_running:
            break
        _time.sleep(CHECK_INTERVAL)
        if not _watchdog_running:
            break
        if _is_tunnel_alive():
            continue
        _db_logger.warning("SSH tunnel watchdog: tunnel is DOWN – reconnecting...")
        try:
            from app.services.health_alert_service import log_and_alert as _health_alert
            _health_alert("SSH_TUNNEL_DOWN", "CRITICAL", "Túnel SSH para o banco de dados caiu", "O watchdog detectou que o túnel SSH está inativo e tentará reconexão.")
        except Exception:
            pass
        with _ssh_lifecycle_lock:
            # Re-check inside the lock — another thread may have rebuilt it.
            if _is_tunnel_alive():
                continue
            try:
                close_ssh_tunnel()
            except Exception as _ce:
                _db_logger.error(f"SSH watchdog: error closing old tunnel: {_ce}")
            _time.sleep(RECONNECT_DELAY)
            try:
                ok = _reconnect_ssh_tunnel()
                if ok:
                    _db_logger.info("SSH tunnel reconnected")
                    try:
                        from app.services.health_alert_service import log_event as _log_ev
                        _log_ev("SSH_TUNNEL_RECONNECTED", "INFO", "Túnel SSH reconectado com sucesso", None)
                    except Exception:
                        pass
                else:
                    _db_logger.warning("SSH tunnel watchdog: reconnect failed, will retry next cycle")
                    try:
                        from app.services.health_alert_service import log_and_alert as _health_alert
                        _health_alert("SSH_TUNNEL_RECONNECT_FAILED", "CRITICAL", "Falha ao reconectar o túnel SSH", "O watchdog tentou reconectar mas falhou. Nova tentativa no próximo ciclo (15s).")
                    except Exception:
                        pass
            except Exception as _re:
                _db_logger.error(f"SSH watchdog: reconnect error: {_re}")
    _db_logger.info("SSH tunnel watchdog stopped")


def start_ssh_watchdog():
    """Start the watchdog daemon thread if not already running."""
    global _watchdog_running
    with _watchdog_lock:
        if _watchdog_running:
            return
        _watchdog_running = True
    t = threading.Thread(target=_ssh_watchdog, daemon=True, name="ssh-watchdog")
    t.start()


def stop_ssh_watchdog():
    """Signal the watchdog to stop on next cycle."""
    global _watchdog_running
    _watchdog_running = False


def _reconnect_ssh_tunnel():
    """Re-run the SSH tunnel setup without starting a new watchdog."""
    return init_ssh_tunnel(_start_watchdog=False)


_ensure_magento_lock = threading.Lock()


def ensure_ssh_engine_ready(timeout_s: int = 20) -> bool:
    """Best-effort: make sure engine_ssh is alive. If it's missing or the tunnel
    is dead, try to (re)establish it synchronously. Returns True if engine_ssh
    is usable, False otherwise. Used by background snapshot rebuilds so they
    don't silently abort just because the tunnel went idle between cycles.
    Uses the shared `_ssh_lifecycle_lock` so it can't race the watchdog."""
    global engine_ssh
    if engine_ssh is not None and _is_tunnel_alive():
        return True
    if not all([settings.SSH_HOST, settings.SSH_USER, settings.SSH_PRIVATE_KEY,
                settings.DB_HOST, settings.DB_USER, settings.DB_PASSWORD, settings.DB_NAME]):
        return False
    with _ssh_lifecycle_lock:
        # Re-check inside the lock — watchdog may have rebuilt it meanwhile.
        if engine_ssh is not None and _is_tunnel_alive():
            return True
        try:
            close_ssh_tunnel()
        except Exception as _ce:
            _db_logger.warning(f"ensure_ssh_engine_ready: error closing stale tunnel: {_ce}")
        try:
            ok = init_ssh_tunnel(_start_watchdog=False)
            if ok:
                _db_logger.info("ensure_ssh_engine_ready: SSH tunnel re-established on demand")
                return engine_ssh is not None
        except Exception as _re:
            _db_logger.error(f"ensure_ssh_engine_ready: reinit failed: {_re}")
        return False


def ensure_magento_engine_ready() -> bool:
    """Best-effort: make sure engine_magento exists. (Re)create it synchronously
    if it was never configured or got disposed. Returns True if engine_magento
    is usable, False otherwise."""
    global engine_magento
    if engine_magento is not None:
        return True
    if not (settings.MYSQL_MAGENTO_HOST and settings.MYSQL_MAGENTO_PASSWORD and settings.MYSQL_MAGENTO_DATABASE):
        return False
    with _ensure_magento_lock:
        if engine_magento is not None:
            return True
        try:
            init_mysql_connections()
            if engine_magento is not None:
                _db_logger.info("ensure_magento_engine_ready: engine_magento re-created on demand")
                return True
        except Exception as _re:
            _db_logger.error(f"ensure_magento_engine_ready: reinit failed: {_re}")
        return False


def init_ssh_tunnel(_start_watchdog: bool = True):
    global ssh_tunnel, engine_ssh, SessionLocalSSH
    import paramiko
    import tempfile
    import os as os_module
    
    if not all([settings.SSH_HOST, settings.SSH_USER, settings.SSH_PRIVATE_KEY, 
                settings.DB_HOST, settings.DB_USER, settings.DB_PASSWORD, settings.DB_NAME]):
        print("SSH tunnel configuration incomplete. Skipping SSH tunnel initialization.")
        return False
    
    try:
        key_content = settings.SSH_PRIVATE_KEY
        key_content = key_content.replace('\\n', '\n')
        key_content = key_content.replace('\\r', '')
        
        if '\n' not in key_content and '-----BEGIN' in key_content:
            import re
            key_content = re.sub(r'(-----BEGIN [A-Z ]+ KEY-----)\s*', r'\1\n', key_content)
            key_content = re.sub(r'\s*(-----END [A-Z ]+ KEY-----)', r'\n\1', key_content)
            
            match = re.match(r'(-----BEGIN [A-Z ]+ KEY-----\n)(.*?)(\n-----END [A-Z ]+ KEY-----)', key_content, re.DOTALL)
            if match:
                header, body, footer = match.groups()
                body = body.replace('  ', '\n').replace(' ', '')
                key_content = header + body + footer
        
        if not key_content.startswith('-----BEGIN'):
            print("Warning: SSH key format may be incorrect")
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.pem', delete=False) as temp_key:
            temp_key.write(key_content)
            temp_key_path = temp_key.name
        
        os_module.chmod(temp_key_path, 0o600)
        
        pkey = None
        last_error = None
        
        if 'OPENSSH' in key_content:
            from paramiko import Ed25519Key
            
            try:
                key_file_io = io.StringIO(key_content)
                pkey = Ed25519Key.from_private_key(key_file_io)
                print("Successfully loaded Ed25519 OpenSSH key")
            except Exception as e1:
                last_error = e1
                try:
                    key_file_io = io.StringIO(key_content)
                    pkey = paramiko.RSAKey.from_private_key(key_file_io)
                    print("Successfully loaded RSA OpenSSH key")
                except Exception as e2:
                    last_error = e2
                    try:
                        key_file_io = io.StringIO(key_content)
                        pkey = paramiko.ECDSAKey.from_private_key(key_file_io)
                        print("Successfully loaded ECDSA OpenSSH key")
                    except Exception as e3:
                        last_error = e3
        else:
            key_types = [
                (paramiko.RSAKey, "RSA"),
                (paramiko.Ed25519Key, "Ed25519"),
                (paramiko.ECDSAKey, "ECDSA"),
            ]
            
            for key_class, key_name in key_types:
                try:
                    pkey = key_class.from_private_key_file(temp_key_path)
                    print(f"Successfully loaded {key_name} key")
                    break
                except Exception as e:
                    last_error = e
                    continue
        
        os_module.unlink(temp_key_path)
        
        if pkey is None:
            raise Exception(f"Could not load SSH key with any supported format. Last error: {last_error}")
        
        ssh_client = paramiko.SSHClient()

        # --- Host key verification (MITM protection) ---
        # AutoAddPolicy silently trusts any server key, enabling MITM.
        # We require a pinned server public key supplied via SSH_HOST_KEY
        # ("<key-type> <base64-key>", the two middle fields of a known_hosts line).
        # If the variable is absent we refuse to connect (fail-closed).
        ssh_host_key_raw = settings.SSH_HOST_KEY.strip()
        if not ssh_host_key_raw:
            raise Exception(
                "SSH_HOST_KEY is not configured. Refusing to open an SSH tunnel "
                "without a pinned server host key — set SSH_HOST_KEY to the "
                "server's public key ('<key-type> <base64-key>') to enable the "
                "tunnel."
            )

        try:
            key_parts = ssh_host_key_raw.split()
            if len(key_parts) < 2:
                raise ValueError("SSH_HOST_KEY must be '<key-type> <base64-key>'")
            key_type_str, key_b64 = key_parts[0], key_parts[1]

            import base64
            key_data = base64.b64decode(key_b64)
            key_msg = paramiko.message.Message(key_data)

            _key_class_map = {
                "ssh-rsa": paramiko.RSAKey,
                "ssh-ed25519": paramiko.Ed25519Key,
                "ecdsa-sha2-nistp256": paramiko.ECDSAKey,
                "ecdsa-sha2-nistp384": paramiko.ECDSAKey,
                "ecdsa-sha2-nistp521": paramiko.ECDSAKey,
            }
            # DSSKey foi removido de versões recentes do paramiko (DSA é obsoleto).
            _dss_cls = getattr(paramiko, "DSSKey", None)
            if _dss_cls is not None:
                _key_class_map["ssh-dss"] = _dss_cls
            key_class = _key_class_map.get(key_type_str)
            if key_class is None:
                raise ValueError(f"Unsupported SSH host key type: {key_type_str}")

            pinned_host_key = key_class(msg=key_msg)
        except Exception as hk_err:
            raise Exception(
                f"Failed to parse SSH_HOST_KEY: {hk_err}. "
                "Ensure SSH_HOST_KEY is a valid '<key-type> <base64-key>' string."
            )

        # Paramiko matches host-key entries using "[host]:port" when the port
        # is not 22, mirroring the OpenSSH known_hosts convention.
        host_key_lookup = (
            f"[{settings.SSH_HOST}]:{settings.SSH_PORT}"
            if settings.SSH_PORT != 22
            else settings.SSH_HOST
        )
        ssh_client.get_host_keys().add(
            host_key_lookup, key_type_str, pinned_host_key
        )
        ssh_client.set_missing_host_key_policy(paramiko.RejectPolicy())
        # --- End host key verification ---

        ssh_client.connect(
            hostname=settings.SSH_HOST,
            port=settings.SSH_PORT,
            username=settings.SSH_USER,
            pkey=pkey
        )
        
        transport = ssh_client.get_transport()
        if transport:
            transport.set_keepalive(30)
        
        local_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        local_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        local_server.bind(('127.0.0.1', 0))
        local_port = local_server.getsockname()[1]
        local_server.listen(5)
        
        def forward_tunnel(local_socket, transport, remote_host, remote_port):
            while True:
                try:
                    client_sock, addr = local_socket.accept()
                    channel = transport.open_channel(
                        'direct-tcpip',
                        (remote_host, remote_port),
                        client_sock.getpeername()
                    )
                    if channel is None:
                        client_sock.close()
                        continue
                    
                    def forward(source, dest):
                        while True:
                            data = source.recv(32768)
                            if len(data) == 0:
                                break
                            dest.sendall(data)
                        source.close()
                        dest.close()
                    
                    t1 = threading.Thread(target=forward, args=(client_sock, channel))
                    t2 = threading.Thread(target=forward, args=(channel, client_sock))
                    t1.daemon = True
                    t2.daemon = True
                    t1.start()
                    t2.start()
                except Exception as e:
                    print(f"Forward tunnel error: {e}")
                    break
        
        tunnel_thread = threading.Thread(
            target=forward_tunnel,
            args=(local_server, transport, settings.DB_HOST, settings.DB_PORT)
        )
        tunnel_thread.daemon = True
        tunnel_thread.start()
        
        ssh_tunnel = {
            'client': ssh_client,
            'server': local_server,
            'port': local_port
        }
        
        print(f"SSH tunnel established on local port {local_port}")
        
        db_url = f"mysql+pymysql://{settings.DB_USER}:{settings.DB_PASSWORD}@127.0.0.1:{local_port}/{settings.DB_NAME}"
        engine_ssh = create_engine(
            db_url,
            pool_pre_ping=True,
            pool_recycle=1800,
            pool_size=5,
            max_overflow=10,
            pool_timeout=30,
            connect_args={'connect_timeout': 15, 'read_timeout': 120, 'write_timeout': 30}
        )
        SessionLocalSSH = sessionmaker(autocommit=False, autoflush=False, bind=engine_ssh)
        
        print(f"Successfully connected to database '{settings.DB_NAME}' via SSH tunnel")
        if _start_watchdog:
            start_ssh_watchdog()
        return True
        
    except Exception as e:
        print(f"Failed to establish SSH tunnel: {e}")
        import traceback
        traceback.print_exc()
        return False

def get_db_ssh():
    if SessionLocalSSH is None:
        raise Exception("SSH database connection not configured. Check SSH and DB settings.")
    db = SessionLocalSSH()
    try:
        yield db
    finally:
        db.close()

def close_ssh_tunnel():
    global ssh_tunnel, engine_ssh, SessionLocalSSH
    try:
        if ssh_tunnel:
            if isinstance(ssh_tunnel, dict):
                server = ssh_tunnel.get('server')
                if server:
                    try:
                        server.close()
                    except Exception:
                        pass

                client = ssh_tunnel.get('client')
                if client:
                    try:
                        client.close()
                    except Exception:
                        pass
            else:
                try:
                    ssh_tunnel.stop()
                except Exception:
                    pass

        if engine_ssh:
            try:
                engine_ssh.dispose()
            except Exception:
                pass

        _db_logger.info("SSH tunnel closed successfully")
    except Exception as e:
        _db_logger.error(f"Error closing SSH tunnel: {e}")
    finally:
        ssh_tunnel = None
        engine_ssh = None
        SessionLocalSSH = None

def init_mysql_connections():
    global engine_ativo, SessionLocalAtivo, engine_magento, SessionLocalMagento
    
    if settings.MYSQL_ATIVO_PASSWORD and settings.MYSQL_ATIVO_DATABASE:
        try:
            engine_ativo = create_engine(
                settings.MYSQL_ATIVO_URL,
                pool_pre_ping=True,
                pool_recycle=1800,
                pool_size=5,
                max_overflow=10,
                pool_timeout=30,
                connect_args={'connect_timeout': 15, 'read_timeout': 120, 'write_timeout': 30}
            )
            SessionLocalAtivo = sessionmaker(autocommit=False, autoflush=False, bind=engine_ativo)
            print("MySQL Ativo connection configured")
        except Exception as e:
            print(f"Failed to configure MySQL Ativo: {e}")
    
    if settings.MYSQL_MAGENTO_HOST and settings.MYSQL_MAGENTO_PASSWORD and settings.MYSQL_MAGENTO_DATABASE:
        try:
            from urllib.parse import quote_plus
            password_encoded = quote_plus(settings.MYSQL_MAGENTO_PASSWORD)
            magento_url = f"mysql+pymysql://{settings.MYSQL_MAGENTO_USER}:{password_encoded}@{settings.MYSQL_MAGENTO_HOST}:{settings.MYSQL_MAGENTO_PORT}/{settings.MYSQL_MAGENTO_DATABASE}"
            engine_magento = create_engine(
                magento_url,
                pool_pre_ping=True,
                # Recycle conns aggressively — avoids MySQL killing them
                # via wait_timeout (commonly 600–1800s on managed servers)
                # and reduces "MySQL server has gone away" incidents.
                pool_recycle=600,
                # Pool sized to absorb concurrent Marketing/ISC/snapshot work
                # without exhausting under load. With pool_pre_ping + recycle=600s
                # idle staleness is already handled, so we can afford more slots.
                pool_size=8,
                max_overflow=12,
                pool_timeout=20,
                pool_use_lifo=True,
                connect_args={'connect_timeout': 15, 'read_timeout': 90, 'write_timeout': 30}
            )
            SessionLocalMagento = sessionmaker(autocommit=False, autoflush=False, bind=engine_magento)
            print(f"MySQL Magento connection configured for database '{settings.MYSQL_MAGENTO_DATABASE}'")
        except Exception as e:
            print(f"Failed to configure MySQL Magento: {e}")

def get_db_ativo():
    if SessionLocalAtivo is None:
        raise Exception("MySQL Ativo connection not configured. Check MYSQL_ATIVO_PASSWORD and MYSQL_ATIVO_DATABASE.")
    db = SessionLocalAtivo()
    try:
        yield db
    finally:
        db.close()

def get_db_magento():
    if SessionLocalMagento is None:
        raise Exception("MySQL Magento connection not configured. Check MYSQL_MAGENTO_PASSWORD and MYSQL_MAGENTO_DATABASE.")
    db = SessionLocalMagento()
    try:
        yield db
    finally:
        db.close()
