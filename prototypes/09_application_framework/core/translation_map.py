"""
translation_map.py

Stores translated text mapped to desktop coordinates.

The Translation Map is the central data structure used by
LingoLens.

It represents the currently translated Windows desktop and
acts as the single source of truth for every translated
desktop region.

The map is intentionally independent from OCR, Translation,
Desktop Observation and the Floating Lens.
"""

from dataclasses import dataclass
from enum import Enum
from itertools import count
from typing import Callable


# ------------------------------------------------------------
# Runtime Entry ID Generator
# ------------------------------------------------------------

_entry_id = count(1)


# ------------------------------------------------------------
# Translation Entry State
# ------------------------------------------------------------

class TranslationEntryState(Enum):
    """
    Persistent state of a TranslationEntry.

    ACTIVE
        Entry is currently active on the desktop.

    INACTIVE
        Entry is retained as known translation knowledge but
        is not currently active on the desktop.

    Reconciliation outcomes such as NEW, MOVED, RETURNED and
    CHANGED are intentionally not stored as permanent entry
    states.
    """

    ACTIVE = "active"
    INACTIVE = "inactive"


# ------------------------------------------------------------
# Reconciliation Outcome
# ------------------------------------------------------------

class ReconciliationOutcome(Enum):
    """
    Outcome produced by the future reconciliation process.

    These are transition/results concepts, not persistent
    TranslationEntry states.
    """

    KNOWN = "known"
    MOVED = "moved"
    RETURNED = "returned"
    CHANGED = "changed"
    NEW = "new"


# ------------------------------------------------------------
# Monitor Information
# ------------------------------------------------------------

@dataclass(slots=True)
class MonitorInfo:
    """
    Represents one physical monitor in the Windows
    virtual desktop coordinate system.

    Coordinates are desktop coordinates, not image-local
    coordinates.
    """

    index: int

    left: int
    top: int
    right: int
    bottom: int

    attached: bool = True
    primary: bool = False

    @property
    def width(self) -> int:
        """Return monitor width."""
        return self.right - self.left

    @property
    def height(self) -> int:
        """Return monitor height."""
        return self.bottom - self.top

    @property
    def bounds(self) -> tuple[int, int, int, int]:
        """
        Return monitor bounds.

        Format:
            (left, top, width, height)
        """
        return (
            self.left,
            self.top,
            self.width,
            self.height,
        )


# ------------------------------------------------------------
# Translation Entry
# ------------------------------------------------------------

@dataclass(slots=True)
class TranslationEntry:
    """
    Represents one translated desktop region.

    Entries are retained by TranslationMap even when they
    become inactive. This allows future reconciliation to
    reuse previously established translation knowledge.
    """

    id: int

    # (left, top, width, height)
    bounds: tuple[int, int, int, int]

    original: str
    translation: str

    # Persistent knowledge state.
    state: TranslationEntryState = TranslationEntryState.ACTIVE


# ------------------------------------------------------------
# Translation Map
# ------------------------------------------------------------

class TranslationMap:
    """
    Represents the translated Windows desktop.

    Responsibilities
    ----------------
    - Store translated desktop regions.
    - Retain known translation entries.
    - Track active/inactive entry state.
    - Reposition translated regions after desktop moves.
    - Return visible regions.
    - Store virtual desktop metadata.
    - Store physical monitor layout.
    - Track desktop generations.
    - Notify listeners when translation data changes.
    - Provide atomic reconciliation transactions.

    This class does NOT:
    - Capture the desktop.
    - Perform OCR.
    - Perform Translation.
    - Observe desktop changes.
    - Control the Floating Lens.
    - Implement the reconciliation matching algorithm.
    """

    def __init__(self):
        """
        Initialize an empty TranslationMap.
        """

        #
        # Desktop metadata
        #

        self._desktop_bounds = (
            0,
            0,
            0,
            0,
        )

        self._monitors: list[MonitorInfo] = []

        self._initialized = False

        self._generation = 0

        #
        # Translation entries
        #

        self._entries: list[TranslationEntry] = []

        #
        # Change listeners
        #

        self._change_listeners: list[
            Callable[[], None]
        ] = []

        #
        # Reconciliation transaction state
        #

        self._reconciliation_active = False

    # --------------------------------------------------------
    # Change Notifications
    # --------------------------------------------------------

    def add_change_listener(
        self,
        listener: Callable[[], None],
    ):
        """
        Register a listener for TranslationMap changes.

        Duplicate listeners are ignored.
        """

        if listener in self._change_listeners:
            return

        self._change_listeners.append(
            listener
        )

    def remove_change_listener(
        self,
        listener: Callable[[], None],
    ):
        """
        Remove a previously registered change listener.
        """

        if listener not in self._change_listeners:
            return

        self._change_listeners.remove(
            listener
        )

    def _notify_change(self):
        """
        Notify all registered listeners that the
        TranslationMap has changed.

        Listener failures do not prevent the TranslationMap
        from continuing to operate.
        """

        for listener in self._change_listeners.copy():
            try:
                listener()
            except Exception:
                continue

    # --------------------------------------------------------
    # Reconciliation Transactions
    # --------------------------------------------------------

    def begin_reconciliation(self):
        """
        Begin an atomic reconciliation transaction.

        During a reconciliation transaction, individual
        mutations do not emit change notifications.

        The transaction must be completed with
        commit_reconciliation().
        """

        if self._reconciliation_active:
            raise RuntimeError(
                "A reconciliation transaction is already active."
            )

        self._reconciliation_active = True

    def commit_reconciliation(self):
        """
        Commit the active reconciliation transaction.

        Exactly one change notification is emitted when the
        transaction is committed.

        A reconciliation transaction cannot be committed
        without first calling begin_reconciliation().
        """

        if not self._reconciliation_active:
            raise RuntimeError(
                "No reconciliation transaction is active."
            )

        self._reconciliation_active = False

        self._notify_change()

    def _require_reconciliation(self):
        """
        Ensure a reconciliation-only mutation is being
        performed inside an active transaction.
        """

        if not self._reconciliation_active:
            raise RuntimeError(
                "This operation requires an active "
                "reconciliation transaction."
            )

    # --------------------------------------------------------
    # Reconciliation Entry Mutations
    # --------------------------------------------------------

    def mark_entry_active(
        self,
        entry_id: int,
    ):
        """
        Mark an existing entry ACTIVE.

        Intended for KNOWN and RETURNED reconciliation
        outcomes.

        No notification is emitted until
        commit_reconciliation().
        """

        self._require_reconciliation()

        entry = self._get_entry_by_id(entry_id)

        if entry is None:
            raise KeyError(
                f"Translation entry {entry_id} does not exist."
            )

        entry.state = TranslationEntryState.ACTIVE

    def mark_entry_inactive(
        self,
        entry_id: int,
    ):
        """
        Mark an existing entry INACTIVE.

        This represents the lifecycle transition:

            ACTIVE -> INACTIVE

        No notification is emitted until
        commit_reconciliation().
        """

        self._require_reconciliation()

        entry = self._get_entry_by_id(entry_id)

        if entry is None:
            raise KeyError(
                f"Translation entry {entry_id} does not exist."
            )

        entry.state = TranslationEntryState.INACTIVE

    def update_entry_bounds(
        self,
        entry_id: int,
        bounds,
    ):
        """
        Update the desktop bounds of an existing entry.

        Intended for movement/repositioning where the identity,
        original text and translation remain unchanged.

        No notification is emitted until
        commit_reconciliation().
        """

        self._require_reconciliation()

        if len(bounds) != 4:
            raise ValueError(
                "Entry bounds must contain "
                "(left, top, width, height)."
            )

        entry = self._get_entry_by_id(entry_id)

        if entry is None:
            raise KeyError(
                f"Translation entry {entry_id} does not exist."
            )

        entry.bounds = (
            int(bounds[0]),
            int(bounds[1]),
            int(bounds[2]),
            int(bounds[3]),
        )

    def add_new_entry(
        self,
        bounds,
        original,
        translation,
    ) -> TranslationEntry:
        """
        Add a genuinely new translation entry during
        reconciliation.

        New entries always begin ACTIVE.

        No notification is emitted until
        commit_reconciliation().
        """

        self._require_reconciliation()

        if len(bounds) != 4:
            raise ValueError(
                "Entry bounds must contain "
                "(left, top, width, height)."
            )

        entry = TranslationEntry(
            id=next(_entry_id),
            bounds=(
                int(bounds[0]),
                int(bounds[1]),
                int(bounds[2]),
                int(bounds[3]),
            ),
            original=original,
            translation=translation,
            state=TranslationEntryState.ACTIVE,
        )

        self._entries.append(entry)

        return entry

    def _get_entry_by_id(
        self,
        entry_id: int,
    ) -> TranslationEntry | None:
        """
        Return an entry by ID.

        Internal helper used by reconciliation mutations.
        """

        for entry in self._entries:
            if entry.id == entry_id:
                return entry

        return None

    # --------------------------------------------------------
    # Desktop Metadata
    # --------------------------------------------------------

    def set_desktop_bounds(
        self,
        bounds,
    ):
        """
        Store the Windows virtual desktop bounds.

        Format:
            (left, top, width, height)
        """

        if len(bounds) != 4:
            raise ValueError(
                "Desktop bounds must contain "
                "(left, top, width, height)."
            )

        left, top, width, height = bounds

        if width < 0:
            raise ValueError(
                "Desktop width cannot be negative."
            )

        if height < 0:
            raise ValueError(
                "Desktop height cannot be negative."
            )

        self._desktop_bounds = (
            int(left),
            int(top),
            int(width),
            int(height),
        )

    def get_desktop_bounds(self):
        """
        Return the Windows virtual desktop bounds.
        """

        return self._desktop_bounds

    def set_monitors(
        self,
        monitors,
    ):
        """
        Store the physical monitor layout.

        A copy is stored so external code cannot modify
        the internal monitor list directly.
        """

        self._monitors = list(monitors)

    def get_monitors(self):
        """
        Return the current monitor layout.

        A copy of the monitor list is returned.
        """

        return self._monitors.copy()

    def mark_initialized(self):
        """
        Mark the TranslationMap as initialized.
        """

        self._initialized = True

    def reset(self):
        """
        Reset the TranslationMap.

        Used when constructing a completely new
        desktop model.
        """

        self.clear()

        self._desktop_bounds = (
            0,
            0,
            0,
            0,
        )

        self._monitors.clear()

        self._initialized = False

        self._generation = 0

    def is_initialized(self):
        """
        Return whether the desktop model has been
        initialized.
        """

        return self._initialized

    def next_generation(self):
        """
        Advance to the next desktop generation.
        """

        self._generation += 1

        return self._generation

    def get_generation(self):
        """
        Return the current desktop generation.
        """

        return self._generation

    # --------------------------------------------------------
    # Translation Entries
    # --------------------------------------------------------

    def clear(self):
        """
        Remove every translation entry.

        Clear remains a complete-map reset operation and is
        intentionally separate from reconciliation lifecycle
        handling.
        """

        if not self._entries:
            return

        self._entries.clear()

        if not self._reconciliation_active:
            self._notify_change()

    def add_entry(
        self,
        bounds,
        original,
        translation,
    ):
        """
        Add a translated desktop region.

        This is the existing non-transactional API retained
        for compatibility with the current application.

        Reconciliation code must use add_new_entry().
        """

        entry = TranslationEntry(
            id=next(_entry_id),
            bounds=bounds,
            original=original,
            translation=translation,
            state=TranslationEntryState.ACTIVE,
        )

        self._entries.append(entry)

        if not self._reconciliation_active:
            self._notify_change()

        return entry

    def update_region(
        self,
        bounds,
        original,
        translation,
    ):
        """
        Replace every translated entry intersecting
        the supplied desktop region.

        This is the legacy immediate-update API.

        Reconciliation code should use the explicit transaction
        methods instead.
        """

        self.remove_entries_in_region(
            bounds
        )

        self.add_entry(
            bounds,
            original,
            translation,
        )

    def remove_entries_in_region(
        self,
        bounds,
    ):
        """
        Remove every translated region intersecting
        the supplied desktop region.

        This remains the legacy physical-removal operation.

        Future ControllerLive reconciliation will no longer
        use physical deletion for normal visibility changes;
        it will transition entries to INACTIVE instead.
        """

        left, top, width, height = bounds

        right = left + width
        bottom = top + height

        remaining = []

        for entry in self._entries:

            e_left, e_top, e_width, e_height = (
                entry.bounds
            )

            e_right = e_left + e_width
            e_bottom = e_top + e_height

            intersects = not (
                e_right < left
                or e_left > right
                or e_bottom < top
                or e_top > bottom
            )

            if not intersects:
                remaining.append(entry)

        if len(remaining) == len(self._entries):
            return

        self._entries = remaining

        if not self._reconciliation_active:
            self._notify_change()

    def move_entries_in_region(
        self,
        bounds,
        dx,
        dy,
    ):
        """
        Reposition translated regions contained within the
        supplied source region.

        Native movement is intentionally preserved as a
        separate operation from reconciliation.

        ControllerLive ordering contract:

            Native Move Processing
                    ↓
            TranslationMap movement
                    ↓
            Dirty-region OCR
                    ↓
            Reconciliation
        """

        left, top, width, height = bounds

        right = left + width
        bottom = top + height

        moved = 0

        for entry in self._entries:

            e_left, e_top, e_width, e_height = (
                entry.bounds
            )

            e_right = e_left + e_width
            e_bottom = e_top + e_height

            fully_contained = (
                e_left >= left
                and e_top >= top
                and e_right <= right
                and e_bottom <= bottom
            )

            if not fully_contained:
                continue

            entry.bounds = (
                e_left + int(dx),
                e_top + int(dy),
                e_width,
                e_height,
            )

            moved += 1

        if moved and not self._reconciliation_active:
            self._notify_change()

        return moved

    # --------------------------------------------------------
    # Queries
    # --------------------------------------------------------

    def get_entries(self):
        """
        Return every translated desktop region.

        Both ACTIVE and INACTIVE entries are returned because
        both represent known translation knowledge.
        """

        return self._entries.copy()

    def get_entries_in_region(
        self,
        bounds,
    ):
        """
        Return every ACTIVE translated desktop region
        intersecting the supplied viewport.

        INACTIVE entries remain stored in the map but are not
        considered part of the currently visible desktop.
        """

        left, top, width, height = bounds

        right = left + width
        bottom = top + height

        visible = []

        for entry in self._entries:

            if entry.state != TranslationEntryState.ACTIVE:
                continue

            e_left, e_top, e_width, e_height = (
                entry.bounds
            )

            e_right = e_left + e_width
            e_bottom = e_top + e_height

            intersects = not (
                e_right < left
                or e_left > right
                or e_bottom < top
                or e_top > bottom
            )

            if intersects:
                visible.append(entry)

        return visible

    def entry_count(self):
        """
        Return the total number of known translation regions.

        This includes both ACTIVE and INACTIVE entries.
        """

        return len(self._entries)