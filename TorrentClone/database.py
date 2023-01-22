import os
import traceback
import hashlib
import TorrentClone


CHUNK_SIZE = 262144  # 256 KB

# Adds a file to the share list
async def add_share(share_path, full_file=True, total_size=0):
    share_path = os.path.normpath(share_path)
    filename = os.path.basename(share_path)
    if full_file:
        if not os.path.isfile(share_path):
            TorrentClone.gui.alert_share("File not found")
            return False

        if TorrentClone.DB.Shares.find_one({"filename": filename}):
            TorrentClone.gui.alert_share("File already shared")
            return False

        file_stats = os.stat(share_path)

        try:
            TorrentClone.DB.Shares.insert(
                {
                    "filename": filename,
                    "share_path": share_path,
                    "size": file_stats.st_size,
                    "progress": 100,
                    "chunks": get_chunks(share_path, full_file),
                }
            )
        except Exception as e:
            print(repr(e))

    else:
        filename = filename[:-5]
        try:
            TorrentClone.DB.Shares.insert(
                {
                    "filename": filename,
                    "share_path": share_path,
                    "size": total_size,
                    "progress": 0,
                    "chunks": get_chunks(share_path, full_file),
                }
            )
        except Exception as e:
            print(repr(e))

    # Reload the shares and rebuild UI
    reload_shares(full_file)

    return True


# Removes a file from the share list
async def remove_share(_id):
    share = TorrentClone.DB.Shares.find_one({"_id": _id})
    if not share:
        TorrentClone.gui.status_message("Unknown share, cannot be removed")
        return False

    TorrentClone.DB.Shares.delete_one({"_id": _id})
    reload_shares(True)
    return True


# Adds a file's chunk to the share list, also updates the progress bar
async def add_chunk_to_file(filename, chunk_id, chunk_hash):
    try:
        file = TorrentClone.DB.Shares.find_one({"filename": filename})
        chunks = file["chunks"]
        chunks[chunk_id] = {
            "peer_list": [f"{TorrentClone.networking.MY_IP}"],
            "chunk_hash": f"{chunk_hash}",
        }
        if file["progress"] >= 100:
            prog = 100
        else:
            prog = file["progress"] + (100 / (file["size"] / CHUNK_SIZE))

        TorrentClone.DB.Shares.update_one({"filename": filename}, {"$set": {"chunks": chunks}})
        TorrentClone.DB.Shares.update_one({"filename": filename}, {"$set": {"progress": prog}})

        reload_shares(False)
        if TorrentClone.MY_WINDOW["panel_downloads"].Widget is not None:
            if file["progress"] >= 100:
                TorrentClone.MY_WINDOW[("progress", file["filename"])].update(
                    visible=True,
                    current_count=100,
                    bar_color=(TorrentClone.gui.WARN, TorrentClone.gui.BGCOLOR),
                )
            else:
                TorrentClone.MY_WINDOW[("progress", file["filename"])].update(
                    visible=True, current_count=file["progress"]
                )
    except:
        print("Failed to add a chunk to the file")
        return False
    return True


# Pulls the shares from the database
def reload_shares(rebuild=False):
    TorrentClone.SHARES = [i for i in TorrentClone.DB.Shares.find()]

    if rebuild:
        TorrentClone.gui.rebuild_ui()


# Gets the hash of a file/chunk
def get_hash(file):
    try:
        with open(file, "rb") as f:
            buffer = f.read(CHUNK_SIZE)
            md5 = hashlib.md5(buffer)
            return md5.hexdigest()
    except:
        traceback.print_exc()


# Gets the chunk list of a file
def get_chunks(file, full_file=True):
    if full_file:
        try:
            with open(file, "rb") as f:
                chunks = {}
                index = 0
                while True:
                    buffer = f.read(CHUNK_SIZE)
                    if not buffer:
                        break
                    md5 = hashlib.md5(buffer)
                    chunks[index] = {
                        "peer_list": [f"{TorrentClone.networking.MY_IP}"],
                        "chunk_hash": md5.hexdigest(),
                    }
                    index += 1

                return chunks
        except:
            traceback.print_exc()
    else:
        return {}
