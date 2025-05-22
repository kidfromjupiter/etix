class EmbedBuilder:
    def __init__(self):
        pass

    def build_detailed_seat_embed(self, alert):
        embed = {
            "title": "🎟️ New Seat Available!",
            "fields": [
                {"name": "Event", "value": alert.get('eventUrl')},
                {"name": "Time", "value": alert.get('eventTime')},
                {"name": "Section", "value": alert.get('section')},
                {"name": "Row", "value": alert.get('row')},
                {"name": "Seat", "value": alert.get('seat')},
                {"name": "Price", "value": f"${alert.get('price')}"}
            ],
            "color": 5814783
        }
        return embed

    def build_summary_embed(self, url, time, no_of_seats, section):
        summary_message = (
            f"Found {no_of_seats} seats in section {section}"
        )
        embed = {
            "title": "🎟️ Seat Summary Update",
            "description": summary_message,
            "fields":[
                {"name": "Event", "value": url},
                {"name": "Time", "value": time},
            ],
            "color": 5814783
        }
        return embed
