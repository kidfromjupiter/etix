from datetime import datetime


class EmbedBuilder:
    def __init__(self):
        pass

    def build_detailed_seat_embed(self, alert):
        embed = {
            "title": "🎟️ New Seat Available!",
            "fields": [
                {"name": "Event", "value": alert.get('eventUrl')},
                {"name": "Time", "value": datetime.fromisoformat(alert.get('eventTime')).strftime('%A, %B %d, %Y at %I:%M %p')},
                {"name": "Section", "value": alert.get('section')},
                {"name": "Row", "value": alert.get('row')},
                {"name": "Seat", "value": alert.get('seat')},
                {"name": "Price", "value": f"${alert.get('price')}"}
            ],
            "color": 5814783
        }
        return embed

    def build_summary_embed(self, url, time, no_of_seats, section):
        embed = {
            "title": "🎟️ Seat Summary Update",
            "fields":[
                {"name": "Event", "value": url},
                {"name": "Time", "value": datetime.fromisoformat(time).strftime('%A, %B %d, %Y at %I:%M %p')},
                {"name": "Section", "value": section},
                {"name": "Seats", "value": no_of_seats},
            ],
            "color": 16711680
        }
        return embed
