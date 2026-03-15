import pyodbc
from textual.app import App, ComposeResult
from textual.widgets import ListView, ListItem, Label


class EventApp(App):


    BINDINGS = [
        ("j", "cursor_down", "Down"),
        ("k", "cursor_up", "Up"),
    ]

    def __init__(self, events):
        super().__init__()
        self.events = events
        self.selected_event = None

    def compose(self) -> ComposeResult:
        yield ListView(id="event_list")

    def on_mount(self):

        listview = self.query_one("#event_list", ListView)

        for eventNo, name in self.events:
            text = f"{eventNo} : {name}"
            listview.append(
                ListItem(Label(text), id=f"event_{eventNo}")
            )

    def on_list_view_selected(self, event):
        self.selected_event = int(event.item.id.replace("event_", ""))
        self.exit()


def get_event_no(server, password):

    connectionStr =  ("DRIVER=FreeTDS;" 
         f"SERVER={server};" 
          "PORT=1433;"
          "UID=sw;" 
          "DATABASE=sw;" 
         f"PWD={password};" 
          "TDS_Version=7.4;")

   

    events = []

    with pyodbc.connect(connectionStr) as conn:

        query = """
            select
                大会番号 as eventNo,
                大会名1 as eventName
            from 大会設定
        """

        cursor = conn.cursor()
        cursor.execute(query)

        for row in cursor:
            events.append((row.eventNo, row.eventName))

    app = EventApp(events)
    app.run()

    print("\033[2J\033[H", end="")
    return app.selected_event
