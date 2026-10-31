"""Champion-select request identity, independent of UI and native runtimes."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Selection:
    session_id: str
    champion_id: int
    skin_id: int

    def __post_init__(self):
        if not isinstance(self.session_id, str) or not self.session_id.strip() or len(self.session_id) > 128:
            raise ValueError('A nonempty session identity is required')
        if type(self.champion_id) is not int or self.champion_id <= 0:
            raise ValueError('Invalid champion ID')
        if type(self.skin_id) is not int or self.skin_id // 1000 != self.champion_id:
            raise ValueError('Skin does not belong to selected champion')

    @property
    def base_skin_id(self):
        return self.champion_id * 1000

    @property
    def is_base(self):
        return self.skin_id == self.base_skin_id

    def require_current(self, session_id, champion_id):
        if self.session_id != session_id or self.champion_id != champion_id:
            raise ValueError('Selection belongs to a different game session or champion')
