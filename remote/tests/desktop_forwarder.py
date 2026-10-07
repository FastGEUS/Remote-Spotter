"""Test-only TCP forwarder replacing an SSH peer; never shipped as transport."""
import asyncio
import sys

async def main():
    target,local=map(int,sys.argv[1:])
    async def handle(reader,writer):
        peer_reader,peer_writer=await asyncio.open_connection('127.0.0.1',target)
        async def copy(source,destination):
            try:
                while data:=await source.read(65536):
                    destination.write(data);await destination.drain()
            finally:destination.close()
        await asyncio.gather(copy(reader,peer_writer),copy(peer_reader,writer),return_exceptions=True)
    server=await asyncio.start_server(handle,'127.0.0.1',local)
    print(f'debug1: Local forwarding listening on 127.0.0.1 port {local}.',file=sys.stderr,flush=True)
    async with server:await server.serve_forever()

if __name__=='__main__':asyncio.run(main())
