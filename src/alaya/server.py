import logging
from pathlib import Path

from fastmcp import FastMCP

from alaya.config import get_vault_root, ConfigError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

mcp = FastMCP(
    name="alaya",
    instructions=(
        "You are connected to a zk-managed personal knowledge vault. "
        "Use the available tools to read, write, search, and organize notes. "
        "Always confirm before moving, renaming, deleting, or bulk-modifying notes. "
        "Capture is always safe — no confirmation needed for append or inbox operations."
    ),
)

# Explicit registration: server -> tools (one direction only).
# vault is resolved once here and closed over in each tool wrapper.
from alaya.tools import read, write, inbox, search, structure, edit, tasks, external, ingest  # noqa: E402

def _register_all(vault: Path) -> None:
    read._register(mcp, vault)
    write._register(mcp, vault)
    inbox._register(mcp, vault)
    search._register(mcp, vault)
    structure._register(mcp, vault)
    edit._register(mcp, vault)
    tasks._register(mcp, vault)
    external._register(mcp, vault)
    ingest._register(mcp, vault)


def _register_index_listener(vault: Path, watcher_handler=None) -> None:
    """Subscribe the index updater to note change events emitted by write tools.

    If watcher_handler is provided, marks indexed paths so the watcher skips them.
    """
    from alaya.events import NoteEvent, on_note_change
    from alaya.index.store import get_store, upsert_note, delete_note_from_index, update_metadata
    from alaya.index.embedder import chunk_note, embed_chunks

    store = get_store(vault)

    def _handle(event: NoteEvent) -> None:
        try:
            if event.event_type in ("created", "modified"):
                content = (vault / event.path).read_text()
                chunks = chunk_note(event.path, content)
                embeddings = embed_chunks(chunks)
                upsert_note(event.path, chunks, embeddings, store)
                if watcher_handler:
                    watcher_handler.mark_indexed(event.path)
                logger.debug("Index updated for %s (%s)", event.path, event.event_type)
            elif event.event_type == "deleted":
                delete_note_from_index(event.path, store)
                if watcher_handler:
                    watcher_handler.mark_indexed(event.path)
                logger.debug("Index entry removed for %s", event.path)
            elif event.event_type == "moved":
                update_metadata(
                    event.old_path, event.path,
                    new_title=None, new_tags=None, store=store,
                )
                if watcher_handler:
                    watcher_handler.mark_indexed(event.path)
                    if event.old_path:
                        watcher_handler.mark_indexed(event.old_path)
                logger.debug("Index metadata updated: %s -> %s", event.old_path, event.path)
        except Exception as e:
            logger.warning("Index update failed for %s (%s): %s", event.path, event.event_type, e)

    on_note_change(_handle)


def main() -> None:
    try:
        vault_root = get_vault_root()
    except ConfigError as e:
        logger.error("Configuration error: %s", e)
        raise SystemExit(1)

    logger.info("alaya starting — vault root: %s", vault_root)

    _register_all(vault_root)

    from alaya.index.store import get_store
    from alaya.watcher import start_watcher

    store = get_store(vault_root)
    observer, handler = start_watcher(vault_root, store)
    _register_index_listener(vault_root, watcher_handler=handler)
    logger.info("File watcher started")

    try:
        mcp.run()
    finally:
        observer.stop()
        observer.join()
        handler.stop()
        logger.info("File watcher stopped")


if __name__ == "__main__":
    main()
