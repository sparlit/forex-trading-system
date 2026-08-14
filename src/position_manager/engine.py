"""Position Manager skeleton.
Tracks open positions and updates state.
"""



class PositionManager:
    def __init__(self):
        self.positions: dict[str, dict] = {}

    def add_position(self, position: dict) -> None:
        """Add a new open position using its 'position_id' key.
        The order dict is expected to contain a unique 'position_id' field.
        """
        position_id = position.get('position_id')
        if not position_id:
            raise ValueError('position dict must contain a "position_id" key')
        self.open_position(position_id, position)


    def open_position(self, position_id: str, details: dict) -> None:
        self.positions[position_id] = details


    def get_open_positions(self) -> list[dict]:
        return list(self.positions.values())
