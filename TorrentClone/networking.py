import os
import socket
import websockets
import asyncio
import traceback
import json
from concurrent.futures import TimeoutError as ConnectionTimeoutError
from TorrentClone import database
import TorrentClone


MY_NAME = socket.gethostname()  # The user's host name
PORT = 1111  # The port to connect to
CONNECTIONS = set()  # Peers I'm connected to

# Gets my IP address
with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
    s.connect(("8.8.8.8", 53))
    MY_IP = s.getsockname()[0]

print(MY_IP)
print(MY_NAME)


class ConnectionHandler:
    websocket = None
    hostname = None
    uri = None
    state = "disconnected"
    shares = []
    peers = []

    # Send message to peer
    async def send(self, message):
        try:
            data = json.dumps(message)
            await self.websocket.send(data)
        except websockets.exceptions.ConnectionClosedOK:
            print("ConnectionClosedOK DETECTED")
        except websockets.exceptions.ConnectionClosed:
            print("ConnectionClosed DETECTED")
        except:
            traceback.print_exc()

    # Receive message from peer
    async def recv(self):
        try:
            message = await self.websocket.recv()
            data = json.loads(message)
            return data
        except:
            traceback.print_exc()

    # Send a file chunk to peer
    async def chunk_send(self, filepath, chunk_id):
        self.state = "transfer"
        if filepath[-5:] == ".temp":
            filepath = os.path.join(filepath, f"{chunk_id}")
            try:
                with open(filepath, "rb") as f:
                    chunk = f.read(database.CHUNK_SIZE)
                    if not chunk:
                        self.state = "connected"
                        return
                    await self.websocket.send(chunk)
                    await asyncio.sleep(0)
            except:
                traceback.print_exc()

        else:
            try:
                with open(filepath, "rb") as f:
                    f.seek(int(chunk_id) * database.CHUNK_SIZE, 0)
                    chunk = f.read(database.CHUNK_SIZE)
                    if not chunk:
                        self.state = "connected"
                        return
                    await self.websocket.send(chunk)
                    await asyncio.sleep(0)
            except:
                traceback.print_exc()

        self.state = "connected"

    # Receive a file chunk from a peer
    async def chunk_recv(self, filename, total_size, chunk_hash, chunk_id):
        self.state = "transfer"
        chunk_folder = os.path.join(os.getcwd(), "downloads/", f"{filename}.temp")
        chunk_path = os.path.join(chunk_folder, f"{chunk_id}")
        try:
            chunk = await self.websocket.recv()
            if not chunk or filename not in TorrentClone.downloader.IN_PROGRESS:
                self.state = "connected"
                return False
            with open(chunk_path, "wb") as f:
                f.write(chunk)
                f.flush()
                await asyncio.sleep(0)
        except:
            traceback.print_exc()

        downloaded_hash = database.get_hash(chunk_path)
        # Compare the hash of the received and sent chunk to verify it wasn't corrupted
        if downloaded_hash != chunk_hash:
            print(
                f"Download of chunk {chunk_id} of file {filename} from {self.hostname} was corrupted"
            )
            try:
                os.remove(chunk_path)
            except:
                pass
            self.state = "connected"
            return False

        share = TorrentClone.DB.Shares.find_one({"filename": filename})
        if not share:
            await database.add_share(
                os.path.join(os.getcwd(), f"downloads/", f"{filename}.temp"), False, total_size
            )

        await database.add_chunk_to_file(filename, chunk_id, downloaded_hash)

        self.state = "connected"
        return True

    # Tries to connect to peer
    async def greet(self):
        try:
            self.websocket = await asyncio.wait_for(
                websockets.connect(self.uri, ping_timeout=None), timeout=3
            )
        except ConnectionTimeoutError:
            return
        except asyncio.exceptions.TimeoutError:
            return
        except ConnectionRefusedError:
            print(f"Connection refused to {self.uri}")
            return
        except:
            return

        await self.send({"hostname": MY_NAME})

        response = await self.recv()
        if "hostname" not in response:
            return False
        if len(response["hostname"]) > 1024:
            return False
        self.hostname = response["hostname"]

        confirmation = await self.recv()
        confirmed = confirmation.get("connection")
        # If the peer agreed to the connection
        if confirmed == "authorized":
            self.state = "connected"
            TorrentClone.gui.status_message(f"Connected to {self.hostname}")
            asyncio.get_event_loop().create_task(status_update(self))
        else:
            print("Peer not connected yet")

    # Handles request to connect from a peer
    async def welcome(self) -> bool:
        greeting = await self.recv()
        if "hostname" not in greeting:
            return False
        if len(greeting["hostname"]) > 1024:
            return False

        self.hostname = greeting["hostname"]

        self.uri = f"ws://{self.websocket.remote_address[0]}:{PORT}"

        await self.send({"hostname": MY_NAME})

        # Approve connection
        if TorrentClone.STATE == "connected":
            self.state == "connected"
            await self.send({"connection": "authorized"})
            TorrentClone.gui.status_message(f"New connection from {self.hostname}")
            # Start listening to the peer
            asyncio.get_event_loop().create_task(self.listener())
            # Send a status update to a new connection immediately
            asyncio.get_event_loop().create_task(status_update(self))
            return True
        else:
            await self.send({"connection": "unauthorized"})
            return False

    # Listens to messages from peers
    async def listener(self):
        try:
            async for message in self.websocket:
                data = json.loads(message)
                op_type = data.get("op_type")
                if op_type == "status":
                    print(f"{self.hostname} Status:\nConnections-{data['connections']}\n")
                    self.peers = data["connections"]
                    self.shares = data["shares"]

                    for peer in self.peers:
                        if peer["uri"][0] == "w":
                            await connect(peer["uri"])
                        else:
                            await connect(f"ws://{peer['uri']}:{PORT}")

                # Peer is requesting a file
                if op_type == "request":
                    print(
                        f"{self.hostname} Requested file:\n {data['filename']}, Chunk_id: {data['chunk_id']}"
                    )
                    found = False
                    # Prep all the file details that the recepient needs
                    for share in TorrentClone.SHARES:
                        if share["filename"] == data["filename"]:
                            found = True
                            filename = share["filename"]
                            share_path = share["share_path"]
                            chunk_hash = share["chunks"][data["chunk_id"]]["chunk_hash"]
                            await self.send(
                                {
                                    "op_type": "sending",
                                    "filename": filename,
                                    "total_size": share["size"],
                                    "chunk_hash": chunk_hash,
                                    "chunk_id": data["chunk_id"],
                                }
                            )

                            # Send the chunk
                            await self.chunk_send(share_path, data["chunk_id"])

                    if found == False:
                        await self.send(
                            {
                                "op_type": "sending",
                                "filename": "null",
                                "total_size": "null",
                                "chunk_hash": "null",
                                "chunk_id": "null",
                            }
                        )

                # Peer is sending a file
                if op_type == "sending":
                    print(
                        f"{self.hostname} Confirms sending file:\n {data['filename']}, Chunk_id: {data['chunk_id']}"
                    )
                    if (
                        data["filename"] == "null"
                        and data["chunk_hash"] == "null"
                        and data["chunk_id"] == "null"
                    ):
                        print("File not shared by the peer")
                        TorrentClone.STATE = "unexpected"

                    else:
                        # Take all the details for the file and receive it
                        if await self.chunk_recv(
                            data["filename"],
                            data["total_size"],
                            data["chunk_hash"],
                            data["chunk_id"],
                        ):
                            print(
                                f"Download complete for: {data['filename']}, chunk - {data['chunk_id']}"
                            )

                await asyncio.sleep(0)

        except ValueError:
            print("Empty message received")
        except websockets.exceptions.ConnectionClosedOK:
            print(f"ConnectionClosedOK from {self.hostname}")
            await unregister(self)
        except websockets.exceptions.ConnectionClosed:
            print(f"ConnectionClosed from {self.hostname}")
            await unregister(self)
        except websockets.exceptions.WebsocketException:
            print(f"WebsocketException from {self.hostname}")
            await unregister(self)
        except:
            traceback.print_exc()

    # Close the connection to a peer and update the state
    async def close(self):
        self.state = "disconnected"
        try:
            await self.websocket.close()
        except:
            traceback.print_exc()


class ServerHandler(ConnectionHandler):
    def __init__(self, websocket):
        self.websocket = websocket


class ClientHandler(ConnectionHandler):
    def __init__(self, uri):
        self.uri = uri


# Connects to a peer
async def connect(uri):
    # To avoid trying to connect to myself
    if uri == f"ws://{MY_IP}:{PORT}":
        return

    # To avoid duplicate connections
    for c in CONNECTIONS:
        if uri == c.uri or uri[5:-5] == c.uri or c.uri[5:-5] == uri:
            return

    connection = ClientHandler(uri)
    await connection.greet()
    # To avoid adding the connection twice
    for c in CONNECTIONS:
        if (
            connection.uri == c.uri
            or connection.uri[5:-5] == c.uri
            or c.uri[5:-5] == connection.uri
        ):
            return

    if connection.state == "connected":
        CONNECTIONS.add(connection)
        asyncio.get_event_loop().create_task(connection.listener())


# Checks if private network, then scans ports
async def port_scan():
    while TorrentClone.STATE != "connected":
        await asyncio.sleep(3)
    if not MY_IP[:3] == "192" and not MY_IP[:3] == "172" and not MY_IP[:3] == "10.":
        print("This is not a private network, shutting down.")
        exit()

    # Gets IP range (for local network)
    ip_range = MY_IP.split(".")
    ip_range.pop()
    ip_range = ".".join(ip_range)

    # Loops through all possible IPs in the range
    i = 1
    task_list = []
    while i < 256:
        target_ip = f"{ip_range}.{i}"
        uri = f"ws://{target_ip}:{PORT}"
        task_list.append(connect(uri))
        # Try to connect to peers in batches of 5 at a time
        if not i % 5:
            await asyncio.gather(*task_list)
            task_list = []
        i += 1
        await asyncio.sleep(0)


# Handles a peer connection
async def register_client(websocket, _):
    connection = ServerHandler(websocket)
    done = False
    while True:
        if not done:
            if await connection.welcome():
                # Avoid duplicate connections
                for c in CONNECTIONS:
                    if (
                        connection.uri == c.uri
                        or connection.uri[5:-5] == c.uri
                        or c.uri[5:-5] == connection.uri
                    ):
                        return
                connection.state = "connected"
                CONNECTIONS.add(connection)
                done = True

        await asyncio.sleep(0)


# Removes the connection after disconnecting from a peer
async def unregister(connection):
    try:
        CONNECTIONS.remove(connection)
        await connection.close()
    except:
        print("Unable to remove connection")


# Sends a status update message to all peers periodically
async def status_update(new_connection=None):
    while True:
        if TorrentClone.STATE == "connected" or TorrentClone.STATE == "transfer":
            TorrentClone.gui.status_message(f"Online - {len(CONNECTIONS)} peers connected")

            # Makes a list of my connections
            connection_list = [
                {"hostname": connection.hostname, "uri": connection.uri}
                for connection in CONNECTIONS
            ]

            # Makes a list of files I am sharing
            share_list = []
            try:
                for share in TorrentClone.SHARES:
                    share_list.append(
                        {
                            "filename": share["filename"],
                            "size": share["size"],
                            "chunks": share["chunks"],
                        }
                    )
            except IndexError:
                pass

            # For sending a status_update to new connections immediately
            if new_connection is not None:
                if new_connection.state == "connected" or new_connection.state == "transfer":
                    await new_connection.send(
                        {
                            "op_type": "status",
                            "hostname": MY_NAME,
                            "connections": connection_list,
                            "shares": share_list,
                        }
                    )
                break

            # Sends a status update to all peers
            try:
                for connection in CONNECTIONS:
                    if connection.state == "connected" or connection.state == "transfer":
                        await connection.send(
                            {
                                "op_type": "status",
                                "hostname": MY_NAME,
                                "connections": connection_list,
                                "shares": share_list,
                            }
                        )
            except RuntimeError:
                pass

        await asyncio.sleep(30)


# Listens to incoming connection requests
start_server = websockets.serve(register_client, MY_IP, PORT, ping_timeout=None)

if __name__ == "__main__":

    asyncio.get_event_loop().run_until_complete(start_server)
    asyncio.get_event_loop().create_task(status_update())
    asyncio.get_event_loop().run_forever()
