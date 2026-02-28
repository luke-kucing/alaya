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


def _register_index_listener(vault: Path) -> None:
    """Subscribe the index updater to note change events emitted by write tools."""
    from alaya.events import on_note_change
    from alaya.index.store import get_store, upsert_note, delete_note_from_index, update_metadata
    from alaya.index.embedder import chunk_note, embed_chunks

    store = get_store(vault)

    def _handle(event_type: str, path: str) -> None:
        try:
            if event_type in ("created", "modified"):
                content = (vault / path).read_text()
                chunks = chunk_note(path, content)
                embeddings = embed_chunks(chunks)
                upsert_note(path, chunks, embeddings, store)
                logger.debug("Index updated for %s (%s)", path, event_type)
            elif event_type == "deleted":
                delete_note_from_index(path, store)
                logger.debug("Index entry removed for %s", path)
            elif event_type == "moved":
                # format: "old_path:new_path"
                old_path, _, new_path = path.partition(":")
                update_metadata(old_path, new_path, new_title=None, new_tags=None, store=store)
                logger.debug("Index metadata updated: %s -> %s", old_path, new_path)
        except Exception as e:
            logger.warning("Index update failed for %s (%s): %s", path, event_type, e)

    on_note_change(_handle)


def main() -> None:
    try:
        vault_root = get_vault_root()
    except ConfigError as e:
        logger.error("Configuration error: %s", e)
        raise SystemExit(1)

    logger.info("alaya starting — vault root: %s", vault_root)

    _register_all(vault_root)
    _register_index_listener(vault_root)

    from alaya.index.store import get_store
    from alaya.watcher import start_watcher

    store = get_store(vault_root)
    observer = start_watcher(vault_root, store)
    logger.info("File watcher started")

    try:
        mcp.run()
    finally:
        observer.stop()
        observer.join()
        logger.info("File watcher stopped")


if __name__ == "__main__":
    main()
