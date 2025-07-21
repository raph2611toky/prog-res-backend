import sys
from django.core.mail import send_mail
from dotenv import load_dotenv

load_dotenv()

def get_server_settings():
    ip_addr = '127.0.0.1'
    port=8000
    if 'runserver' in sys.argv:
        runserver_index = sys.argv.index('runserver')
        if len(sys.argv) > runserver_index + 1:
            ip_port = sys.argv[runserver_index + 1]
            if ':' in ip_port:
                ip_addr, port = ip_port.split(':')
            else:
                port = ip_port

    return ip_addr, int(port)
