import logging

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
# Each tool module exposes _register(mcp) and has no dependency on server.py.
from alaya.tools import read, write, inbox, search, structure, edit, tasks, gitlab, ingest  # noqa: E402

read._register(mcp)
write._register(mcp)
inbox._register(mcp)
search._register(mcp)
structure._register(mcp)
edit._register(mcp)
tasks._register(mcp)
gitlab._register(mcp)
ingest._register(mcp)


def main() -> None:
    try:
        vault_root = get_vault_root()
    except ConfigError as e:
        logger.error("Configuration error: %s", e)
        raise SystemExit(1)

    logger.info("alaya starting — vault root: %s", vault_root)

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
