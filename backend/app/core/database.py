from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import io
import socket
import threading
from .config import settings

engine = create_engine(settings.DATABASE_URL) if settings.DATABASE_URL else None
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine) if engine else None
Base = declarative_base()

def get_db():
    if SessionLocal is None:
        raise Exception("DATABASE_URL not configured")
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

engine_ativo = None
SessionLocalAtivo = None

engine_magento = None
SessionLocalMagento = None

ssh_tunnel = None
engine_ssh = None
SessionLocalSSH = None

def init_ssh_tunnel():
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
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh_client.connect(
            hostname=settings.SSH_HOST,
            port=settings.SSH_PORT,
            username=settings.SSH_USER,
            pkey=pkey
        )
        
        transport = ssh_client.get_transport()
        
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
                            data = source.recv(4096)
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
            pool_recycle=3600
        )
        SessionLocalSSH = sessionmaker(autocommit=False, autoflush=False, bind=engine_ssh)
        
        print(f"Successfully connected to database '{settings.DB_NAME}' via SSH tunnel")
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
    global ssh_tunnel, engine_ssh
    if ssh_tunnel:
        try:
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
                ssh_tunnel.stop()
            
            if engine_ssh:
                engine_ssh.dispose()
            
            print("SSH tunnel closed successfully")
        except Exception as e:
            print(f"Error closing SSH tunnel: {e}")
        finally:
            ssh_tunnel = None

def init_mysql_connections():
    global engine_ativo, SessionLocalAtivo, engine_magento, SessionLocalMagento
    
    if settings.MYSQL_ATIVO_PASSWORD and settings.MYSQL_ATIVO_DATABASE:
        engine_ativo = create_engine(
            settings.MYSQL_ATIVO_URL,
            pool_pre_ping=True,
            pool_recycle=3600
        )
        SessionLocalAtivo = sessionmaker(autocommit=False, autoflush=False, bind=engine_ativo)
    
    if settings.MYSQL_MAGENTO_PASSWORD and settings.MYSQL_MAGENTO_DATABASE:
        engine_magento = create_engine(
            settings.MYSQL_MAGENTO_URL,
            pool_pre_ping=True,
            pool_recycle=3600
        )
        SessionLocalMagento = sessionmaker(autocommit=False, autoflush=False, bind=engine_magento)

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
