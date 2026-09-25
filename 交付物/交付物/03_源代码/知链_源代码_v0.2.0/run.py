import os
import uvicorn
from zhilian.app import load_environment

if __name__ == '__main__':
    load_environment()
    host = os.getenv('ZHILIAN_HOST', '127.0.0.1')
    if host not in ('127.0.0.1', 'localhost', '::1') and not os.getenv('ZHILIAN_ACCESS_PASSWORD'):
        raise SystemExit('Public/LAN binding requires ZHILIAN_ACCESS_PASSWORD. See README.md.')
    uvicorn.run('zhilian.app:app', host=host, port=int(os.getenv('ZHILIAN_PORT', '8765')))
