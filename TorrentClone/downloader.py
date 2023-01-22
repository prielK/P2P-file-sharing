import os
import asyncio
import traceback
import shutil
import random
import TorrentClone


IN_PROGRESS = []  # Files being downloaded currently
CANCELING = []  # Downloads in progress of being cancelled

# Lists all the files available to download from my peers
def list_all_downloads():
    download_list = []
    temp_dict = {}

    # Removes any duplicate files and combines the peers for each chunk
    for share in [
        share
        for share_list in [connection.shares for connection in TorrentClone.networking.CONNECTIONS]
        for share in share_list
    ]:
        if share["filename"] not in temp_dict.keys():
            temp_dict[share["filename"]] = share
        else:
            chunks = temp_dict[share["filename"]]["chunks"]
            share_chunks = share["chunks"]
            for id, chunk in share_chunks.items():
                if id not in chunks.keys():
                    chunks[id] = share_chunks[id]
                else:
                    temp_peer_list = set(chunks[id]["peer_list"])
                    temp_peer_list.update(chunk["peer_list"])
                    chunks[id]["peer_list"] = list(temp_peer_list)

            temp_dict[share["filename"]]["chunks"] = chunks
    download_list = list(temp_dict.values())

    return download_list


# Downloads a file from peers
async def download_file(filename):
    to_cancel = False
    download_list = list_all_downloads()
    for download in download_list:
        if download["filename"] == filename:
            requested_file = download
            already_shared = False
            for share in TorrentClone.SHARES:
                if requested_file["filename"] == share["filename"]:
                    already_shared = True

            # Set up the directory for the downloaded files
            file_path = os.path.join(os.getcwd(), "downloads/")
            try:
                os.makedirs(file_path)
            except FileExistsError:
                pass
            # Set up the temp directory for the downloaded file chunks
            temp_path = os.path.join(file_path, f"{filename}.temp")
            try:
                os.makedirs(temp_path)
            except FileExistsError:
                pass

            # Creates the chunk queue based on rarity (less peer sharing = higher priority)
            chunks = requested_file["chunks"]
            chunk_queue = []
            for k in sorted(chunks, key=lambda k: len(chunks[k]["peer_list"]), reverse=False):
                chunk_queue.append(k)
            # Request the chunks
            await request_chunks(filename, chunk_queue)

            # Wait for all the chunks to arrive
            count = 0
            chunk_num = len(chunks)
            while count < chunk_num and not to_cancel:
                timeout = 6
                if (
                    TorrentClone.STATE == "unexpected"
                    or filename not in TorrentClone.downloader.IN_PROGRESS
                ):
                    print("Detected unexpected state")
                    to_cancel = True
                    break

                # Check if timeout out reached (when for a while no new chunks were downloaded)
                while timeout > 0 and len(os.listdir(temp_path)) == count:
                    print(f"Counting to timeout - {6-timeout} out of 6")
                    timeout -= 1
                    if filename not in TorrentClone.downloader.IN_PROGRESS:
                        to_cancel = True
                        break
                    await asyncio.sleep(5)

                    # Try to restore the missing chunks by resending the request for them
                    if timeout == 3:
                        restore_queue = []
                        for ch_id in chunk_queue:
                            if ch_id not in os.listdir(temp_path):
                                restore_queue.append(ch_id)
                        await request_chunks(filename, restore_queue)

                # If the timeout was reached, no new chunks were received and the file wasn't fully downloaded - some chunks are unavailable, stop downloading
                if timeout == 0 and len(os.listdir(temp_path)) < chunk_num:
                    print("Timeout while waiting for chunks")
                    to_cancel = True
                    break
                count = len(os.listdir(temp_path))
                await asyncio.sleep(0)

            if not to_cancel:
                if not already_shared:
                    for share in TorrentClone.SHARES:
                        # Before combining the chunks remove them from being shared
                        if share["filename"] == filename:
                            try:
                                await TorrentClone.database.remove_share(share["_id"])
                            except:
                                traceback.print_exc()
                            break

                    # For all in-transit chunks
                    await asyncio.sleep(3)

                # Combine the chunks and remove the temp files
                await combine_chunks(temp_path, os.path.join(file_path, f"{filename}"), chunk_num)

            # Remove the temp directory with the temp chunk files, also remove the chunks from being shared
            await remove_temp_files(temp_path, filename, already_shared)

            # Adds the complete file to the share list
            if not to_cancel and not already_shared:
                if await TorrentClone.database.add_share(
                    os.path.join(file_path, f"{filename}"), True, download["size"]
                ):
                    print("File added to share list successfully")

            await asyncio.sleep(0)

            # Marks the file as not in progress of downloading or canceling
            try:
                TorrentClone.downloader.IN_PROGRESS.remove(filename)
            except ValueError:
                pass
            if to_cancel:
                try:
                    TorrentClone.downloader.CANCELING.remove(filename)
                except ValueError:
                    pass

            # Rebuilds the UI (if it wasn't rebuilt since share wasn't added)
            if TorrentClone.gui.CURR_PANEL == "panel_downloads":
                TorrentClone.gui.rebuild_ui()

    TorrentClone.STATE = "connected"


# Sends messages requesting the chunks from the received list for the received file name
async def request_chunks(filename, chunk_queue):
    rate_limit = 0
    chunks = None
    # Requests to receive chunks (each chunk saved as file)
    for id in chunk_queue:
        if (
            filename not in TorrentClone.downloader.IN_PROGRESS
            or TorrentClone.STATE == "unexpected"
        ):
            break

        # After requesting a batch of chunks, updates the download list to accoutn for possible changes
        if rate_limit < 1:
            await asyncio.sleep(2)
            rate_limit = 64
            download_list = list_all_downloads()
            for download in download_list:
                if download["filename"] == filename:
                    chunks = download["chunks"]
                    break

        if chunks is not None:
            # Chooses a random peer from the available peers (that are sharing the chunk) and request the chunk
            peers = chunks[id]["peer_list"]
            random_peer = random.choice(peers)
            for connection in TorrentClone.networking.CONNECTIONS:
                if connection.uri[5:-5] == random_peer:
                    print(f"Requesting chunk {id} from {connection.uri}")
                    await connection.send(
                        {"op_type": "request", "filename": filename, "chunk_id": id}
                    )
                    rate_limit -= 1
                    break
        else:
            print(f"File is no longer available for download")
            TorrentClone.STATE = "unexpected"

        await asyncio.sleep(0)


# Combines the chunks to a single file
async def combine_chunks(chunks_path, file_path, chunk_amount):
    with open(file_path, "wb") as f:
        for chunk_name in range(chunk_amount):
            chunk_path = os.path.join(chunks_path, f"{chunk_name}")
            with open(chunk_path, "rb") as chunk_file:
                chunk = chunk_file.read()
                f.write(chunk)
                f.flush()
            removed = False
            while not removed:
                try:
                    os.remove(chunk_path)
                    removed = True
                except PermissionError:
                    print("Chunk file still not closed")
                await asyncio.sleep(0)
        print("Chunks combined successfully")


# Deletes the temp directory and temp files, removes chunks from being shared
async def remove_temp_files(temp_path, filename, already_shared):
    rm = False
    try:
        os.rmdir(temp_path)
        rm = True
    except OSError:
        rm = False

    if not rm:
        # For all in-transit chunks
        await asyncio.sleep(3)

        # Fail safe to avoid deleting any file which is not a chunk file
        if all(file.isnumeric() for file in os.listdir(temp_path)):
            try:
                shutil.rmtree(temp_path)
            except:
                traceback.print_exc()

        # Removes any chunks of the unfinished download from being shared
        for share in TorrentClone.SHARES:
            if share["filename"] == filename:
                if not already_shared:
                    try:
                        await TorrentClone.database.remove_share(share["_id"])
                    except:
                        traceback.print_exc()
                break


# Cancels the download of the specified file
def cancel_download(filename):
    try:
        TorrentClone.downloader.IN_PROGRESS.remove(filename)
    except ValueError:
        pass
    TorrentClone.downloader.CANCELING.append(filename)
