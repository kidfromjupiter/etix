from sqlalchemy.orm import Session

from backend.models import EventSeatPricing, Seat, Row, PriceLevel, SeatStatus, Section

def clear_existing_event_data(db: Session, event_id: int):
    """Delete all seat-related data for an event"""
    # Delete in order to respect foreign key constraints
    db.query(EventSeatPricing).filter(EventSeatPricing.event_id == event_id).delete()
    db.commit()

def calculate_adjacent_seats(db: Session, event_id: int, min_group_size: int = 2):
    """
    Dynamically calculates groups of adjacent available seats for an event.
    """
    # Get all available seats for the event ordered by row and position
    available_seats = (db.query(
        Seat,
        Row,
        Section,
        PriceLevel
    ).join(Row, Seat.row_id == Row.id)
      .join(Section, Row.section_id == Section.id)
      .join(EventSeatPricing, EventSeatPricing.seat_id == Seat.id)
      .join(PriceLevel, EventSeatPricing.price_level_id == PriceLevel.id)
      .filter(EventSeatPricing.event_id == event_id)
      .order_by(Row.id, Seat.position_in_row)
      .all())

    if not available_seats:
        return []

    # Group adjacent seats
    groups = []
    current_group = []
    prev_row_id = None
    prev_position = None

    for seat, row, section, price_level in available_seats:
        if prev_row_id == row.id and (prev_position is None or seat.position_in_row == prev_position + 1):
            current_group.append((seat, row, section, price_level))
        else:
            if len(current_group) >= min_group_size:
                groups.append(current_group)
            current_group = [(seat, row, section, price_level)]
        prev_row_id = row.id
        prev_position = seat.position_in_row

    # Add the last group if large enough
    if len(current_group) >= min_group_size:
        groups.append(current_group)

    # Format the response
    result = []
    for group in groups:
        first_seat, first_row, first_section, first_price_level = group[0]
        total_price = sum(price_level.price for (_, _, _, price_level) in group)

        result.append({
            "row_id": first_row.id,
            "row_name": first_row.name,
            "section_id": first_section.id,
            "section_name": first_section.name,
            "seat_count": len(group),
            "seats": [{
                "id": seat.id,
                "name": seat.name,
                "position_in_row": seat.position_in_row,
                "price": price_level.price
            } for (seat, _, _, price_level) in group],
            "price_levels": [{
                "id": first_price_level.id,
                "name": first_price_level.name,
                "price": first_price_level.price
            }],  # Assuming all seats in group have same price level
            "total_price": total_price,
            "average_price": total_price / len(group)
        })

    return result


def ingest_ticket_data(db: Session, ticket_data: dict, section_name: str, event_id: int):
    # Clear all existing seat data for this event
    clear_existing_event_data(db, event_id)

    # First ensure the section exists
    section = db.query(Section).filter(Section.name == section_name).first()
    if not section:
        section = Section(name=section_name)  # Default venue_id
        db.add(section)
        db.commit()
        db.refresh(section)

    # Process seat status legend
    for code, desc in ticket_data.get('statusLegend', {}).items():
        status = db.query(SeatStatus).filter(SeatStatus.code == code).first()
        if not status:
            db_status = SeatStatus(
                code=code,
                description=desc,
                is_available=code == 'O'  # Assuming 'O' is available
            )
            db.add(db_status)

    # Process price levels
    price_level_map = {}
    for price, seats in ticket_data.get('availableByPrice', {}).items():
        if seats:  # Only process if there are seats at this price
            price_level = db.query(PriceLevel).filter(PriceLevel.price == float(price.replace('$', ''))).first()
            if not price_level:
                price_level = PriceLevel(
                    name=f"Price Level {price}",
                    price=float(price.replace('$', ''))
                )
                db.add(price_level)
                price_level_map[price] = price_level.id

    db.commit()  # Commit status and price levels first

    # Process rows and seats
    for row_name, seats in ticket_data.get('availableByRow', {}).items():
        # Find or create row
        row = db.query(Row).filter(Row.name == row_name, Row.section_id == section.id).first()
        if not row:
            row = Row(name=row_name, section_id=section.id)
            db.add(row)
            db.commit()
            db.refresh(row)

        for seat_data in seats:
            # Create seat if not exists
            seat = db.query(Seat).filter(Seat.row_id == row.id, Seat.name == seat_data['seat']).first()
            if not seat:
                seat = Seat(
                    row_id=row.id,
                    name=seat_data['seat'],
                    position_in_row=seat_data.get('seatIndex', 0)
                )
                db.add(seat)
                db.commit()
                db.refresh(seat)

            # Create or update seat pricing
            pricing = db.query(EventSeatPricing).filter(
                EventSeatPricing.seat_id == seat.id,
                EventSeatPricing.event_id == event_id  # Default event_id
            ).first()

            if not pricing:
                pricing = EventSeatPricing(
                    event_id=event_id,
                    seat_id=seat.id,
                    price_level_id=price_level_map.get(seat_data['price'], 1),  # Default price level
                    status_code=seat_data.get('status', 'O'),
                    hold_comment=seat_data.get('holdComment'),
                    note=seat_data.get('note')
                )
                db.add(pricing)

    db.commit()
    return {"message": "Data ingested successfully", "section": section_name}