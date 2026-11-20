from __future__ import annotations
import re
DISPLAY_NAMES: dict[str, str] = {'HC Garden Skippable Locations': "Zelda (her Letter, and Impa's Lullaby)", 'HC Garden': "Castle guards' garden (not Zelda)", 'Beyond Door of Time': 'Master Sword pedestal (past the Door of Time)', 'Beyond Door of Time Skippable Locations': 'Rauru (Light Medallion)', 'Root Exits': 'Save warp or warp song', 'GF Above Jail Child Locations': 'Gerudo Fortress ledge above the jail (child)', '[unmodeled] Tower Collapse Interior Exit': "Ganon's Tower collapse (inside, by the exit)"}
_COLLAPSE_ROOMS: dict[str, str] = {'Tower Collapse Exterior Top': "Ganon's Tower collapse (outside): top, by the boss room", 'Tower Collapse Interior Boss Room Floor': "Ganon's Tower collapse (inside): room under the boss room", 'Tower Collapse Exterior 2 Gaps Top': "Ganon's Tower collapse (outside): two-gap walkway, upper end", 'Tower Collapse Exterior 2 Gaps Bottom': "Ganon's Tower collapse (outside): two-gap walkway, lower end", 'Tower Collapse Interior Burning Rocks': "Ganon's Tower collapse (inside): burning-rocks room", 'Tower Collapse Exterior 0 Gaps': "Ganon's Tower collapse (outside): walkway with no gaps", 'Tower Collapse Interior Stalfos Fight': "Ganon's Tower collapse (inside): Stalfos room", 'Tower Collapse Exterior 1 Gap Top': "Ganon's Tower collapse (outside): one-gap walkway, upper end", 'Tower Collapse Exterior 1 Gap Bottom': "Ganon's Tower collapse (outside): one-gap walkway, lower end", 'Tower Collapse Interior Staircase Top': "Ganon's Tower collapse (inside): top of the staircase", 'Tower Collapse Interior Staircase Bottom': "Ganon's Tower collapse (inside): bottom of the staircase"}
DISPLAY_NAMES.update(_COLLAPSE_ROOMS)
_ZELDA_ROOMS = ('Tower Collapse Exterior Top', 'Tower Collapse Interior Boss Room Floor', 'Tower Collapse Interior Burning Rocks', 'Tower Collapse Interior Stalfos Fight', 'Tower Collapse Interior Staircase Top', 'Tower Collapse Exterior 2 Gaps Top', 'Tower Collapse Exterior 0 Gaps', 'Tower Collapse Exterior 1 Gap Top')
DISPLAY_NAMES.update({f'{raw} (Zelda waiting)': f'{_COLLAPSE_ROOMS[raw]}, Zelda waiting' for raw in _ZELDA_ROOMS})
_TRIAL_DOOR = re.compile('^(?P<room>.+) \\[Door: (?P<door>\\w+)\\]$')

def display_name(region: str, *, with_raw: bool=True) -> str:
    plain = DISPLAY_NAMES.get(region)
    if plain is None:
        match = _TRIAL_DOOR.match(region)
        if match:
            inner = display_name(match['room'], with_raw=False)
            if match['door'] == 'Tower':
                return f"{inner} (entered down the stairs from Ganon's Tower)"
            return f"{inner} (entered through the {match['door']} Trial door)"
    if plain is None:
        return region
    return f'{plain} [{region}]' if with_raw else plain
