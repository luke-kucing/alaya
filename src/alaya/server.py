import logging
import subprocess
from pathlib import Path

from fastmcp import FastMCP

from alaya.backend.config import get_vault_root, ConfigError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

mcp = FastMCP(
    name="alaya",
    instructions=(
        "You are connected to a personal knowledge vault.\n\n"
        "CAPTURE RULES:\n"
        "- When the user shares a thought, observation, or experience, use smart_capture immediately.\n"
        "- NEVER paraphrase, summarize, or reword user input. Capture their exact words verbatim.\n"
        "- NEVER ask 'where should I put this?' -- smart_capture routes automatically.\n"
        "- Only use create_note or append_to_note when the user gives explicit structural instructions "
        "(specific directory, specific title, specific section).\n"
        "- No confirmation needed for capture or append operations. They are always safe.\n\n"
        "DESTRUCTIVE OPERATIONS:\n"
        "- Always confirm before moving, renaming, deleting, or bulk-modifying notes.\n\n"
        "SEARCH:\n"
        "- If search results seem stale or incomplete, call vault_health to check index sync status.\n"
        "- Use search_notes for retrieval. Use smart_capture for input."
    ),
)

# Explicit registration: server -> tools (one direction only).
# vault is resolved once here and closed over in each tool wrapper.
from alaya.tools import read, write, inbox, search, structure, edit, tasks, external, ingest, stats, graph, capture, enrich  # noqa: E402

def _register_all(vault: Path, backend=None, cache=None) -> None:
    # Tools that accept a backend parameter
    read._register(mcp, vault, backend=backend, cache=cache)
    search._register(mcp, vault, backend=backend, cache=cache)
    structure._register(mcp, vault, backend=backend)
    edit._register(mcp, vault, backend=backend)
    graph._register(mcp, vault, backend=backend, cache=cache)
    capture._register(mcp, vault, backend=backend)
    external._register(mcp, vault, backend=backend)

    # Tools that don't need backend
    write._register(mcp, vault)
    inbox._register(mcp, vault)
    tasks._register(mcp, vault)
    ingest._register(mcp, vault)
    stats._register(mcp, vault, cache=cache)
    enrich._register(mcp, vault)


def _instrument_tools(vault: Path, backend=None) -> None:
    """Wrap all registered MCP tools with audit logging."""
    import asyncio
    import time
    from alaya.audit import log_tool_call

    audit_path = backend.config.audit_log_path if backend else None

    tools = asyncio.get_event_loop().run_until_complete(mcp.list_tools())
    for tool in tools:
        original_fn = tool.fn
        tool_name = tool.name

        def _make_wrapper(_orig=original_fn, _name=tool_name):
            def wrapper(*args, **kwargs):
                start = time.perf_counter()
                result = _orig(*args, **kwargs)
                elapsed = (time.perf_counter() - start) * 1000
                log_tool_call(vault, _name, kwargs, str(result)[:200], elapsed, audit_path=audit_path)
                return result
            return wrapper

        tool.fn = _make_wrapper()


def _register_index_listener(vault: Path, watcher_handler=None, cache=None) -> None:
    """Subscribe the index updater to note change events emitted by write tools.

    If watcher_handler is provided, marks indexed paths so the watcher skips them.
    If cache is provided, keeps the metadata cache in sync with write events.
    """
    from alaya.events import NoteEvent, EventType, on_note_change
    from alaya.index.store import get_store, upsert_note, delete_note_from_index, update_metadata
    from alaya.index.embedder import chunk_note, embed_chunks
    from alaya.index import health
    from typing import Never

    store = get_store(vault)

    def _unreachable(x: object) -> Never:
        raise AssertionError(f"Unhandled EventType: {x!r}")

    def _handle(event: NoteEvent) -> None:
        try:
            match event.event_type:
                case EventType.CREATED | EventType.MODIFIED:
                    content = (vault / event.path).read_text()
                    chunks = chunk_note(event.path, content)
                    embeddings = embed_chunks(chunks)
                    upsert_note(event.path, chunks, embeddings, store)
                    if watcher_handler:
                        watcher_handler.mark_indexed(event.path)
                    if cache:
                        cache.invalidate(event.path)
                    health.record_success(event.path)
                    logger.debug("Index updated for %s (%s)", event.path, event.event_type)
                case EventType.DELETED:
                    delete_note_from_index(event.path, store)
                    if watcher_handler:
                        watcher_handler.mark_indexed(event.path)
                    if cache:
                        cache.remove(event.path)
                    health.record_success(event.path)
                    logger.debug("Index entry removed for %s", event.path)
                case EventType.MOVED:
                    update_metadata(
                        event.old_path, event.path,
                        new_title=None, new_tags=None, store=store,
                    )
                    if watcher_handler:
                        watcher_handler.mark_indexed(event.path)
                        if event.old_path:
                            watcher_handler.mark_indexed(event.old_path)
                    if cache:
                        if event.old_path:
                            cache.remove(event.old_path)
                        cache.invalidate(event.path)
                    health.record_success(event.path)
                    logger.debug("Index metadata updated: %s -> %s", event.old_path, event.path)
                case _ as unhandled:
                    _unreachable(unhandled)
        except Exception as e:
            health.record_failure(event.path, str(e))
            logger.warning("Index update failed for %s (%s): %s", event.path, event.event_type, e)

    on_note_change(_handle)


def _register_health_tool(vault: Path) -> None:
    """Register a vault_health tool that exposes index sync status."""
    from alaya.index import health
    from alaya.index.store import get_store

    store = get_store(vault)

    @mcp.tool()
    def vault_health() -> str:
        """Check index sync status. Call this if search results seem stale or incomplete."""
        status = health.get_status()
        chunks = store.count()
        lines = [f"Indexed chunks: {chunks}"]

        last_ago = status["last_success_ago_seconds"]
        if last_ago is None:
            lines.append("Last successful index: never (no events processed yet)")
        else:
            lines.append(f"Last successful index: {last_ago}s ago")

        failed = status["failed_paths"]
        if failed:
            lines.append(f"\nFailed paths ({len(failed)}):")
            for path, msg in failed.items():
                lines.append(f"  {path}: {msg}")
        else:
            lines.append("No failed paths.")

        return "\n".join(lines)


def _maybe_start_reembed(vault_root, store) -> None:
    """Start background re-embed if the active embedding model differs from the index."""
    import threading
    from alaya.index.store import get_index_model
    from alaya.index.models import get_active_model
    from alaya.index.reindex import reembed_background

    stored = get_index_model(store)
    active = get_active_model().key
    if stored is None or stored == active:
        return

    logger.warning(
        "Embedding model changed: %s -> %s. Starting background re-embed.", stored, active
    )
    t = threading.Thread(
        target=reembed_background,
        args=(vault_root, stored, active, store),
        daemon=True,
        name="alaya-reembed",
    )
    t.start()


def main() -> None:
    try:
        vault_root = get_vault_root()
    except ConfigError as e:
        logger.error("Configuration error: %s", e)
        raise SystemExit(1)

    # Detect backend and verify prerequisites
    from alaya.backend.config import get_backend
    try:
        backend = get_backend(vault_root)
        backend.check_available()
    except (ConfigError, RuntimeError) as e:
        logger.error("Backend error: %s", e)
        raise SystemExit(1)

    logger.info("alaya starting -- vault root: %s (backend: %s)", vault_root, backend.config.vault_type)

    # Build metadata cache for Obsidian backends (pure-Python vault scans)
    from alaya.cache import VaultMetadataCache
    cache = VaultMetadataCache(vault_root, skip_dirs=backend.config.skip_dirs)
    if backend.config.vault_type == "obsidian":
        backend.cache = cache

    _register_all(vault_root, backend=backend, cache=cache)
    _register_health_tool(vault_root)
    _instrument_tools(vault_root, backend=backend)

    from alaya.index.store import get_store, get_index_model
    from alaya.index.models import get_active_model
    from alaya.watcher import start_watcher

    store = get_store(vault_root, data_dir=backend.config.vectors_dir)
    # Force table init now so schema-mismatch reindex starts before serving requests
    store._get_table()
    if store.take_needs_reindex():
        import threading
        from alaya.index.reindex import reindex_all
        logger.warning("Schema mismatch detected -- starting background full reindex")
        threading.Thread(
            target=reindex_all, args=(vault_root, store), daemon=True, name="alaya-schema-reindex"
        ).start()

    observer, handler = start_watcher(vault_root, store, cache=cache)
    _register_index_listener(vault_root, watcher_handler=handler, cache=cache)
    logger.info("File watcher started")

    _maybe_start_reembed(vault_root, store)

    try:
        mcp.run()
    finally:
        observer.stop()
        observer.join()
        handler.stop()
        logger.info("File watcher stopped")


if __name__ == "__main__":
    main()
