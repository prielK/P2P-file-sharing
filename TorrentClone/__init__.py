import PySimpleGUI as sg
import asyncio
import os
import tinydb
from tinymongo import TinyMongoClient
from TorrentClone.imageset import LOGO
from TorrentClone.gui import refresh_ui, ui, create_layout, status_message, MY_THEME
from TorrentClone.networking import port_scan, status_update, start_server

# TinyMongo fix
class TinyMongoClient(TinyMongoClient):
    @property
    def _storage(self):
        return tinydb.storages.JSONStorage


# DB
__client__ = TinyMongoClient(os.path.join(os.getcwd(), "TorrentClone.db"))
DB = __client__["TorrentClone"]

SHARES = []
# Check all shared files to see if they still exist
for share in DB.Shares.find():
    if os.path.isfile(share["share_path"]):
        SHARES.append(share)
    else:
        DB.Shares.delete_one({"_id": share["_id"]})

STATE = "init"
status_message("Offline")

# GUI
sg.theme_add_new("my_theme", MY_THEME)
sg.change_look_and_feel("my_theme")
MY_WINDOW = sg.Window("TorrentClone", icon=LOGO, border_depth=0, finalize=True).Layout(
    create_layout()
)

# All the tasks that run on init
async def looper():
    tasks = [ui(), port_scan(), status_update(), start_server, refresh_ui()]
    await asyncio.gather(*tasks)


def main():
    asyncio.get_event_loop().run_until_complete(looper())
