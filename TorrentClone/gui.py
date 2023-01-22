import traceback
import PySimpleGUI as sg
import sys
import asyncio
from TorrentClone import downloader
import TorrentClone


__MESSAGE_QUEUE__ = ""

MY_BLUE = "#3D5A80"
MY_CYAN = "#98C1D9"
MY_ORANGE = "#EE6C4D"
OFF_GREY = "#FAFAFA"
OFF_BLACK = "#293241"
GREY = "#EEEEEE"

ACCENT = MY_BLUE
HIGHLIGHT = MY_CYAN
WARN = MY_ORANGE
TEXTCOLOR = OFF_GREY
BGCOLOR = OFF_BLACK

MY_THEME = {
    "BACKGROUND": BGCOLOR,
    "TEXT": TEXTCOLOR,
    "INPUT": HIGHLIGHT,
    "SCROLL": ACCENT,
    "TEXT_INPUT": BGCOLOR,
    "BUTTON": (TEXTCOLOR, ACCENT),
    "PROGRESS": (HIGHLIGHT, BGCOLOR),
    "BORDER": 1,
    "SLIDER_DEPTH": 0,
    "PROGRESS_DEPTH": 0,
}

FONT_SMALL = ("Montserrat", 8)
FONT = ("Montserrat", 12)
FONT_BOLD = ("Montserrat", 12, "bold")
FONT_BIGGER = ("Montserrat", 14)
FONT_BIGGEST = ("Montserrat", 16, "bold")
BUTTON_PROPS = {"font": FONT_BOLD, "size": (7, 2), "border_width": 1}
BUTTON_BIGGER = {**BUTTON_PROPS, "size": (10, 2)}

CURR_PANEL = None

# Creates the UI layout
def create_layout():
    layout_start = [
        [
            sg.Column(
                [[sg.Image(data=TorrentClone.imageset.BANNER, pad=(75, 50))]],
                justification="center",
            )
        ],
        [
            sg.Column(
                [
                    [
                        sg.Button("Connect", **BUTTON_BIGGER, pad=(50, 5)),
                        sg.Button("Quit", **BUTTON_BIGGER),
                    ]
                ],
                justification="center",
            )
        ],
        [sg.Text("", pad=(0, 50))],
    ]

    layout_main = [
        [
            sg.Image(data=TorrentClone.imageset.MINI_BANNER, pad=(10, 6)),
            sg.Button("Download", **BUTTON_BIGGER, pad=(10, 1)),
            sg.Button("Share", **BUTTON_BIGGER),
        ],
    ]

    share_list = []

    for share in TorrentClone.SHARES:
        if share["size"] < 1024:
            size_str = f"{int(share['size'])} Bytes"
        elif share["size"] < 1024 * 1024:
            size_str = f"{share['size']/1024:.2f} KB"
        else:
            size_str = f"{share['size']/(1024*1024):.2f} MB"
        share_list.append(
            [
                sg.Button(
                    image_data=TorrentClone.imageset.DELETE,
                    button_color=("", BGCOLOR),
                    border_width=0,
                    key=("remove", share["_id"]),
                ),
                sg.Text(
                    share["filename"], font=FONT, text_color="Lightblue", size=(50, 1), pad=(10, 10)
                ),
                sg.Text(
                    (f"{size_str}"),
                    font=FONT_SMALL,
                    justification="right",
                    size=(10, 1),
                    pad=(10, 10),
                ),
            ]
        )

    col_share_list = sg.Column(share_list)

    # Checks if scroll bar required (too many shares)
    if len(share_list) > 7:
        share_scroll = {
            "size": (650, 314),
            "scrollable": True,
            "vertical_scroll_only": True,
        }
    else:
        share_scroll = {"size": (667, 314)}

    pane_shares = [sg.Column([[col_share_list]], **share_scroll, pad=(10, 5))]

    layout_main.append(pane_shares)

    # The status bar
    status_bar = sg.Frame(
        layout=[
            [
                sg.Text(
                    deque_message(),
                    text_color=BGCOLOR,
                    background_color=TEXTCOLOR,
                    key="connection_status",
                    size=(87, 1),
                )
            ]
        ],
        title="",
        relief=sg.RELIEF_SUNKEN,
        key="pane_status",
        background_color=TEXTCOLOR,
        border_width=0,
        pad=(0, 0),
    )

    layout_share = [
        [sg.Image(data=TorrentClone.imageset.MINI_BANNER, pad=(10, 6))],
        [sg.Text("")],
        [sg.Text("Select file to share:", font=FONT_BIGGER, size=(45, 1), pad=(10, 5))],
        [
            sg.Input("", key="new_share", font=FONT_BIGGER, size=(50, 1), pad=(10, 5)),
            sg.FileBrowse(target="new_share", font=FONT_BOLD, size=(7, 2), pad=(8, 0)),
        ],
        [sg.Text("", text_color=WARN, key="share_status", size=(40, 1), pad=(10, 5))],
        [sg.Text("", pad=(0, 55))],
        [
            sg.Column(
                [
                    [
                        sg.Button("Confirm", **BUTTON_BIGGER, pad=(10, 1)),
                        sg.Button("Cancel", **BUTTON_BIGGER),
                    ]
                ],
                justification="center",
            )
        ],
    ]

    # Lists available files to download
    download_list = []
    all_downloads = downloader.list_all_downloads()

    # Creates the download buttons
    for download in all_downloads:
        if download["filename"] in downloader.IN_PROGRESS:
            button = sg.Button(
                "",
                image_data=TorrentClone.imageset.DELETE,
                button_color=("white", BGCOLOR),
                pad=(8, 10),
                border_width=0,
                key=("download", download["filename"]),
            )
        else:
            button = sg.Button(
                "",
                image_data=TorrentClone.imageset.DOWNLOAD,
                button_color=("white", BGCOLOR),
                pad=(8, 10),
                border_width=0,
                key=("download", download["filename"]),
            )
        if download["size"] < 1024:
            size_str = f"{int(download['size'])} Bytes"
        elif download["size"] < 1024 * 1024:
            size_str = f"{download['size']/1024:.2f} KB"
        else:
            size_str = f"{download['size']/(1024*1024):.2f} MB"
        download_list.append(
            [
                button,
                sg.Text(
                    download["filename"],
                    font=FONT,
                    text_color="Lightblue",
                    size=(25, 1),
                    pad=(5, 10),
                ),
                sg.Text(
                    (f"{size_str}"),
                    font=FONT_SMALL,
                    justification="right",
                    size=(10, 1),
                    pad=(5, 10),
                ),
                sg.ProgressBar(
                    max_value=100,
                    key=("progress", download["filename"]),
                    orientation="h",
                    size=(25, 10),
                ),
            ]
        )

    col_download_list = sg.Column(download_list)

    # Checks if scroll bar required (too many downloads)
    if len(download_list) > 7:
        download_scroll = {
            "size": (650, 314),
            "scrollable": True,
            "vertical_scroll_only": True,
        }
    else:
        download_scroll = {"size": (667, 314)}

    pane_downloads = sg.Column([[col_download_list]], **download_scroll, pad=(10, 5))

    layout_downloads = [
        [
            sg.Image(data=TorrentClone.imageset.MINI_BANNER, pad=(10, 6)),
            sg.Column(
                [
                    [
                        sg.Text("", **BUTTON_BIGGER, pad=(10, 1)),
                        sg.Button("Cancel", key="cancel_downloads", **BUTTON_BIGGER),
                    ]
                ]
            ),
        ],
        [pane_downloads],
    ]

    # Sets the panel visibility based on the last panel open (in order to rebuild the same panel)
    st = False
    mn = False
    sh = False
    dl = False

    if TorrentClone.STATE == "init":
        st = True
    elif CURR_PANEL is None or CURR_PANEL == "panel_main":
        mn = True
    elif CURR_PANEL == "panel_share":
        sh = True
    else:
        dl = True

    col_start = sg.Column(layout_start, key="panel_start", visible=st)
    col_main = sg.Column(layout_main, key="panel_main", visible=mn)
    col_share = sg.Column(layout_share, key="panel_share", visible=sh)
    col_downloads = sg.Column(layout_downloads, key="panel_downloads", visible=dl)

    layout = [
        [sg.Pane([col_start, col_main, col_share, col_downloads], relief=sg.RELIEF_FLAT)],
        [status_bar],
    ]

    return layout


# Rebuilds the UI
def rebuild_ui():
    TorrentClone.MY_WINDOW.finalize()
    try:
        new_window = sg.Window(
            "TorrentClone",
            icon=TorrentClone.imageset.LOGO,
            border_depth=0,
            location=TorrentClone.MY_WINDOW.current_location(),
            finalize=True,
        ).Layout(create_layout())
        TorrentClone.MY_WINDOW.close()
        TorrentClone.MY_WINDOW = new_window
        asyncio.get_event_loop().create_task(refresh_ui())
    except:
        traceback.print_exc()


# Refreshes the status message and download bars
async def refresh_ui():
    await check_window()
    TorrentClone.MY_WINDOW["pane_status"].expand(expand_x=True)
    await check_window()

    downloads = downloader.list_all_downloads()
    download_names = []
    for download in downloads:
        download_names.append(download["filename"])

    # Makes the progress bar update, once it reaches 100% it changes the color to WARN
    for share in TorrentClone.SHARES:
        if share["filename"] in download_names:
            if share["progress"] >= 100:
                TorrentClone.MY_WINDOW[("progress", share["filename"])].update(
                    visible=True, current_count=100, bar_color=(WARN, BGCOLOR)
                )
            else:
                TorrentClone.MY_WINDOW[("progress", share["filename"])].update(
                    visible=True, current_count=share["progress"]
                )


# Sets the alert message
def alert_share(message):
    TorrentClone.MY_WINDOW["share_status"].update(message)


# Sets the status message
def status_message(message):
    TorrentClone.gui.__MESSAGE_QUEUE__ = message
    try:
        if TorrentClone.MY_WINDOW["connection_status"].Widget:
            TorrentClone.MY_WINDOW["connection_status"].update(message)
    except AttributeError:
        pass
    except:
        traceback.print_exc()
    asyncio.get_event_loop().create_task(delayed_deque())


# Gets the next message in the queue
def deque_message():
    return TorrentClone.gui.__MESSAGE_QUEUE__


# Set the status based on the message in queue
async def delayed_deque():
    await check_window()
    TorrentClone.MY_WINDOW["connection_status"].update(TorrentClone.gui.__MESSAGE_QUEUE__)


# Checks if the window is built
async def check_window():
    while (
        TorrentClone.MY_WINDOW["panel_start"].Widget is None
        and TorrentClone.MY_WINDOW["panel_main"].Widget is None
        and TorrentClone.MY_WINDOW["panel_share"].Widget is None
        and TorrentClone.MY_WINDOW["panel_downloads"].Widget is None
    ):
        await asyncio.sleep(0)
    return True


# Controls transitions between panels, adding/removing shares and initiating file downloads
async def ui():
    global CURR_PANEL
    while True:
        event, value = TorrentClone.MY_WINDOW.read(timeout=10)
        if event in (None, "Quit"):
            sys.exit()
        elif event == "Connect":
            TorrentClone.STATE = "connected"
            status_message("Online")
            TorrentClone.MY_WINDOW["panel_start"].update(visible=False)
            TorrentClone.MY_WINDOW["panel_main"].update(visible=True)
            CURR_PANEL = "panel_main"
        elif event == "Share":
            TorrentClone.MY_WINDOW["panel_main"].update(visible=False)
            TorrentClone.MY_WINDOW["panel_share"].update(visible=True)
            CURR_PANEL = "panel_share"
        elif event == "Cancel":
            TorrentClone.MY_WINDOW["panel_share"].update(visible=False)
            TorrentClone.MY_WINDOW["panel_main"].update(visible=True)
            TorrentClone.MY_WINDOW["new_share"].update("")
            CURR_PANEL = "panel_main"
        elif event == "Confirm":
            if value["new_share"]:
                if await TorrentClone.database.add_share(value["new_share"]):
                    status_message("New file has been added to the share list")
                    CURR_PANEL = "panel_main"
        # Handles share removals
        elif "remove" in event:
            response = sg.popup_ok_cancel(
                "Are you sure you want to remove this file from the share list?\n\nYou will not be able to share the file again unless you re-download it (if there are other peers sharing it).",
                no_titlebar=True,
                text_color=BGCOLOR,
                background_color=TEXTCOLOR,
                font=FONT,
                button_color=("white", WARN),
                location=get_target_location(),
            )
            if response == "OK":
                if await TorrentClone.database.remove_share(event[1]):
                    status_message("File was removed from the share list")
        elif event == "Download":
            CURR_PANEL = "panel_downloads"
            rebuild_ui()
        elif event == "cancel_downloads":
            TorrentClone.MY_WINDOW["panel_main"].update(visible=True)
            TorrentClone.MY_WINDOW["panel_downloads"].update(visible=False)
            CURR_PANEL = "panel_main"
        elif "download" in event:
            if event[1] not in downloader.IN_PROGRESS and event[1] not in downloader.CANCELING:
                downloader.IN_PROGRESS.append(event[1])
                asyncio.get_running_loop().create_task(downloader.download_file(event[1]))
                rebuild_ui()
            elif event[1] in downloader.IN_PROGRESS:
                downloader.cancel_download(event[1])

        await asyncio.sleep(0)


# Gets the window location for the message pop-up
def get_target_location():
    location = TorrentClone.MY_WINDOW.current_location()
    size = TorrentClone.MY_WINDOW.size
    target_location_x = (location[0] + (size[0] / 2)) - 190
    target_location_y = (location[1] + (size[1] / 2)) - 50
    return target_location_x, target_location_y
