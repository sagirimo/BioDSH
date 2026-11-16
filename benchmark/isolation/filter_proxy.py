"""Forward proxy for benchmark agents that refuses benchmark-answer hosts (2026-10-27).

Agents reach the internet only through the machine's upstream proxy (direct connections time out here), so a hosts file
cannot block Hugging Face: the upstream resolves names. This proxy sits in front of the upstream, answers 403 for blocked
hosts (CONNECT and absolute-URI requests alike) and pipes everything else through. isolate.sh points the agent's proxy
variables at it and starts it when it is not already listening. Log: ~/bench/filter_proxy.log (one line per refusal).
"""
import asyncio, os, sys, time
from pathlib import Path

LISTEN = ('127.0.0.1', int(os.environ.get('FILTER_PROXY_PORT', '7891')))
UPSTREAM = os.environ.get('FILTER_PROXY_UPSTREAM', 'http://100.91.83.96:7890').split('://')[-1].rstrip('/')
BLOCK = ('huggingface.co', 'hf.co', 'hf-mirror.com', 'xethub.hf.co')
LOG = Path.home() / 'bench/filter_proxy.log'


def blocked(host):
    host = host.lower().split(':')[0].strip('[]')
    return any(host == b or host.endswith('.' + b) for b in BLOCK)


async def pipe(r, w):
    try:
        while data := await r.read(65536):
            w.write(data)
            await w.drain()
    except (ConnectionError, asyncio.CancelledError):
        pass
    finally:
        w.close()


async def handle(cr, cw):
    try:
        head = await cr.readuntil(b'\r\n\r\n')
    except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, ConnectionError):
        cw.close()
        return
    line = head.split(b'\r\n', 1)[0].decode('latin-1')
    parts = line.split()
    target = parts[1] if len(parts) > 1 else ''
    host = target if parts and parts[0] == 'CONNECT' else target.split('://')[-1].split('/')[0]
    if blocked(host):
        with LOG.open('a') as f:
            f.write(f'{time.strftime("%F %T")} refused {line}\n')
        cw.write(b'HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
        await cw.drain()
        cw.close()
        return
    h, p = UPSTREAM.rsplit(':', 1)
    try:
        ur, uw = await asyncio.open_connection(h, int(p))
    except OSError:
        cw.close()
        return
    uw.write(head)
    await uw.drain()
    await asyncio.gather(pipe(cr, uw), pipe(ur, cw))


async def main():
    server = await asyncio.start_server(handle, *LISTEN)
    async with server:
        await server.serve_forever()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except OSError as e:  # already running
        sys.exit(f'filter_proxy: {e}')
