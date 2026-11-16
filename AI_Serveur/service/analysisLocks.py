import asyncio
from contextlib import asynccontextmanager


class HashLocks:
    """One lock per file hash, so that one file is analysed once at a time.

    Single instance only: the locks live in this process, which is how the server is run.
    A second instance would need the unique index on the documents (see scripts/init_db.py)
    to catch the same race at insert time.

    A lock exists only while somebody holds it or waits for it, so the table does not grow
    with the number of files analysed. The bookkeeping has no `await` in it, so it cannot
    be interleaved by another request on the event loop.
    """

    def __init__(self) -> None:
        self._entries: dict[str, list] = {}  # key -> [lock, number of holders and waiters]

    @asynccontextmanager
    async def hold(self, key: str):
        entry = self._entries.get(key)
        if entry is None:
            entry = self._entries[key] = [asyncio.Lock(), 0]
        entry[1] += 1
        try:
            async with entry[0]:
                yield
        finally:
            entry[1] -= 1
            if entry[1] == 0:
                del self._entries[key]

    def __len__(self) -> int:
        return len(self._entries)
